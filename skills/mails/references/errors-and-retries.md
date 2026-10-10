# Errors and retries

Every error answers with JSON: `error.code` (stable, branch on it), `error.type`,
`error.message` (for people, may change), `error.param` (the field at fault, or null) and
`error.request_id`. When fields of the request fail the operation's schema, `error.errors`
lists every bad field, each with its own `code`, `message` and `param`. A refusal for any
other reason has no `errors`.

## When to retry

- **429:** the error also carries `error.resets_at`, when the request can succeed, and
  `error.retry_after_seconds`, how long that is. A `Retry-After` header comes only when that
  is 60 seconds or less: wait it out, then retry. A longer wait, such as an hourly, daily or
  monthly cap, sends no header: retry at `resets_at`, or stop and tell a person. `resets_at`
  is `null` when waiting cannot help, because the request alone is over the limit.
  `monthly_limit_exceeded` and `free_tier_exceeded` last until the next calendar month (UTC),
  which is their `resets_at`, or a plan change.
- **500, 502, 503:** retry with backoff (1 s, 2 s, 4 s, up to about 30 s; give up after 5
  tries). A `503` with `Retry-After`, such as `upstream_unavailable` (60 seconds), asks for
  that wait instead. Its `error.retry_after_seconds` says the same, and is all a batch item
  has. When the answer to a retried send carries `Idempotent-Replay: true`, stop: the mail
  went out before the error, and the key will only answer with that error again.
- **409 `duplicate_resource` on a send with an `Idempotency-Key`:** the first request with
  that key is still running. Wait a second and retry with the same key. On
  `POST /v1/drafts/{id}/send` the same 409 also comes, with or without a key, while the draft
  is being sent by another request or at its scheduled time. Read the draft with
  `GET /v1/drafts/{id}` instead: once that send ends, the draft is `sent` or `failed`, and
  sending it again answers `400 invalid_field`. The exception is a send that the email
  service would not take for now, or that an error at mails.ai stopped. The draft is then as
  it was, and sending it again works; a scheduled one is also tried again on its own, and
  only a third failed attempt makes it `failed`.
- **No answer at all** (timeout, dropped connection): the request may have been processed.
  Retry only a `GET`, or a send that carries an `Idempotency-Key`. Only the five sending
  routes read the key (`POST /v1/messages`, `POST /v1/messages/batch`,
  `POST /v1/messages/{id}/reply`, `POST /v1/messages/{id}/forward` and
  `POST /v1/drafts/{id}/send`). Any other write acts again when it is repeated, with a key
  or without, and a repeat of a send without a key can send the message twice.
- **Any other 4xx:** do not retry. Fix the request.

Always retry with the same `Idempotency-Key` and the same body. A different body under a
used key answers `400 invalid_idempotency_key`. A repeat of a finished request within 24
hours returns the first response with the header `Idempotent-Replay: true`. A request that
failed is finished only if the mail had gone out (the retry gets that error back) or a
scheduled send had been stored (the retry gets the scheduled message, `201`, and raises its
`message.scheduled` event if the failed request had not). Otherwise the error frees the key,
and the retry runs the request again.

The SDKs retry on their own, up to 3 times: a 429, and a 5xx on a `GET` or on a request
with an `Idempotency-Key`. In Python those are the five sends only, and the Python SDK makes
one up for a send, batch, reply, forward or draft send that has none. A 429, or a 5xx that
gives a `Retry-After`, is retried after that wait when it is a minute or less, and any other
5xx after 0.5 s, 1 s, 2 s. When no
answer comes at all, the Python SDK retries a `GET` or one of the five sends the same way and
then raises a `MailsError` whose `code` is `transport_error`; the TypeScript SDK does not
retry, and the call throws the error `fetch` gave. A limit that
resets later, or that waiting cannot lift, is not retried: the call fails at once with a
`RateLimitError` that carries the reset time (`resetsAt` in TypeScript, `resets_at` in Python,
null when waiting cannot help) and how many seconds that is (`retryAfterSeconds`,
`retry_after_seconds`), and a send cap's message says when to try again. The `mails` CLI waits
out a limit of 30 seconds or less; otherwise it fails at once, with a hint that says when to
try again or that waiting will not help. It treats a 5xx's `Retry-After` the same way:
`upstream_unavailable` asks for 60 seconds, so the CLI fails at once and says
`Try again in 60 seconds.` The MCP tools wait out a limit of 5 seconds or less;
otherwise the tool's error says when the limit resets, or that waiting will not lift it.
They wait out a 5xx's `Retry-After` of 5 seconds or less too, and answer a longer one, such
as the 60 seconds of `upstream_unavailable`, with the API's error. Check
`GET /v1/billing/usage` before a large run.

## Retrying in Python without the SDK

[../examples/rest.py](../examples/rest.py) does not retry. This wrapper adds the rules
above:

```python
import time

from rest import ApiError, call

# The only requests that read Idempotency-Key. Any other write acts again when it is repeated.
SENDS = ("/v1/messages", "/v1/messages/batch")
SEND_ENDINGS = ("/reply", "/forward", "/send")


def call_with_retries(method, path, body=None, idempotency_key=None, attempts=5):
    keyed_send = (
        method == "POST"
        and idempotency_key is not None
        and (path in SENDS or path.endswith(SEND_ENDINGS))
    )
    safe_to_repeat = method == "GET" or keyed_send
    for attempt in range(attempts):
        last = attempt == attempts - 1
        try:
            return call(method, path, body, idempotency_key)
        except ApiError as error:
            retryable = (
                # Retry-After comes only with a wait of 60 seconds or less. A 429 without it
                # lasts longer or never lifts: raise, and its message says when to try again.
                (error.status == 429 and error.retry_after is not None)
                # A replayed error means the mail went out: the key will only answer it again.
                or (error.status >= 500 and safe_to_repeat and not error.replayed)
                or (error.status == 409 and keyed_send)
            )
            if last or not retryable:
                raise
            time.sleep(error.retry_after or min(30, 2**attempt))
        except OSError:
            # No answer at all: a timeout, or a connection that was refused or dropped.
            if last or not safe_to_repeat:
                raise
            time.sleep(min(30, 2**attempt))


usage = call_with_retries("GET", "/v1/billing/usage")
print(usage)
```

## Branching on codes in TypeScript

```ts
import { createClient, MailsError } from "@mailsai/sdk";

const mails = createClient();

try {
  const sent = await mails.send({
    to: "reply@test.mails.ai",
    subject: "Your receipt for order 1042",
    body_text: "Thanks for your order.",
    idempotency_key: "receipt-1042",
  });
  console.log("sent", sent.id);
} catch (error) {
  if (!(error instanceof MailsError)) throw error;
  if (error.code === "recipient_suppressed") console.log("skip this address:", error.message);
  else if (error.code === "cold_email_prohibited") console.log("not allowed:", error.message);
  else if (error.status === 429 || error.status >= 500) console.log("try again later:", error.code);
  else throw error;
}
```

## Codes

| Code | Status | Meaning and what to do |
|---|---|---|
| `missing_field`, `invalid_field`, `invalid_param_value` | 400, 422 | A field is missing or wrong. `error.param` names the field when one field of the body or query is at fault, and is `null` otherwise, for example for a body that is not JSON or for a message or draft in a state the request cannot change. Fix the request. A thread `folder` that cannot be set is a `422` |
| `invalid_idempotency_key` | 400 | The key was already used with a different body. Use a new key for a new message |
| `test_mode_required` | 400, 403 | Only test mode may do this: `POST /v1/test/inbound` (400), or a reply to test mail, whose people are whatever addresses a test gave (403). Test mode is a `mk_test_` key, or a signed-in dashboard session that sends the header `X-Mails-Mode: test`. That header does not change an API key's mode. Use a test key |
| `missing_authorization` | 401 | No `Authorization: Bearer` header |
| `invalid_api_key`, `revoked_api_key`, `expired_api_key` | 401 | The key is wrong or no longer valid. Get a new one |
| `invalid_access_token` | 401 | A sign-in token is wrong, expired or revoked. The app renews it; if that fails, sign in again |
| `payment_required`, `subscription_canceled` | 402 | The workspace is paused or its subscription was canceled. Contact support or renew |
| `plan_limit_exceeded` | 402 | A send's `from` names an agent that does not exist, and the plan has no room to create it. Pass `agent` with an existing one, or change the plan (`error.upgrade_url`) |
| `resource_cap_exceeded` | 402, 409 | The plan's cap on agents, API keys, webhooks or open drafts (402, with `error.upgrade_url`), or the 200 labels a workspace may have (409). Delete one first |
| `feature_not_enabled` | 400, 402 | The plan does not include this, for example custom domains (402), or the feature is not switched on (400) |
| `insufficient_scope` | 403 | The key lacks the scope (`send`, `read` or `manage`; a send or a draft that would create an agent needs `manage`), or it is tied to one agent and the request names another agent, creates an agent, changes webhooks, labels, API keys, billing, domains or its own agent's allowlist, blocklist or send limits, sends an event to the webhooks again, reads the workspace's usage or log, lists or changes the send-anyway list, or lists or revokes connected apps. A key also cannot make a key wider than itself. Use a key that can |
| `connected_app_not_allowed` | 403 | An app someone connected by signing in asked to create an API key or a webhook, change where a webhook sends or an agent's allowlist, blocklist or send limits, rotate a webhook's signing secret, open billing, list or revoke the workspace's connected apps (`GET /v1/oauth/grants`, `DELETE /v1/oauth/grants/{id}`), or delete a thread for good (`DELETE /v1/threads/{id}?permanent=true`; it can still move the thread to trash). Do it with an API key, or in the dashboard or with the `mails` CLI if your role allows it |
| `live_mode_required` | 403 | A test key asked to move a thread that holds live mail to trash or to delete it, to reschedule or cancel a message a live key scheduled, to change, send or delete a draft a live key made, to send a forwarding test (`POST /v1/agents/{id}/forwarding/verify`), to revoke a live key, or to change, pause or archive an agent that has a live key tied to it, live mail (sent, scheduled or received) or a draft a live key made. A signed-in dashboard session that sends the header `X-Mails-Mode: test` gets it too. Do it with a live key or from the dashboard |
| `workspace_not_approved` | 403 | The workspace is waiting for approval to send. Contact support |
| `agent_suspended` | 403 | mails.ai paused this agent, for abuse or for its own or the workspace's bounce or complaint rate. The API cannot resume it. A pause for a rate can end by itself once the rate has fallen: mails.ai checks an agent's own rate every 15 minutes and the workspace's every hour (the `email-best-practices` skill says when it lifts); for abuse, or a pause that stays, contact support |
| `resource_not_found`, `agent_not_found` | 404 | No such id in this workspace, or one a key tied to another agent cannot see. Mail deleted for good, and files that are no longer kept, answer this too |
| `agent_archived` | 404, 409 | The agent is archived, so a reply, a forward, a batch item, a draft send or a forwarding test for it answers 404. So does a new send or draft whose `agent` names it. Archiving cannot be undone, so changing its status answers 409 |
| `method_not_allowed` | 405 | The path exists but not with this method |
| `body_too_large` | 413 | The request is too large, for example a `raw_base64` email over 3 MB on `POST /v1/test/inbound` |
| `billing_state_inconsistent` | 409 | `POST /v1/billing/portal` on a workspace that is on a paid plan with no subscription on record. Contact support, and do not subscribe again: that would bill the workspace twice |
| `duplicate_resource` | 400, 409 | It exists already: a taken agent name or address, or a domain that was already added, answers 400, and a taken label name 409. The rest are 409: a request with the same `Idempotency-Key` is still running, or a draft or scheduled message started sending while you were changing, canceling or deleting it. So is sending a draft that is already being sent, and changing an agent that changed meanwhile. Read it again. A thread you delete for good while one of its messages is being sent answers it too: try again once the message has gone out |
| `agent_name_conflict` | 409 | The name you gave for an agent fits more than one agent, and the message names each one's id. Pass the id. Sends, batch items, new drafts and appeals use the oldest of them instead. A key tied to one agent never gets it: to that key, a name its own agent does not have means the oldest agent with it, and the answer is the `404 agent_not_found` or `403 insufficient_scope` it gets for any other agent |
| `cold_email_prohibited` | 422 | The message looks like unsolicited outreach. mails.ai does not send it. See the `email-best-practices` skill |
| `recipient_suppressed` | 422 | A recipient in `to`, `cc` or `bcc` bounced, complained or unsubscribed before. The whole send is refused, and `error.param` names the field. Remove the address. Test keys skip this check. It also answers, with `param` `to`, when the email service refused every recipient as undeliverable; nothing was sent. When it refuses only some, the send goes to the others and its answer lists the refused ones in `refused_recipients` |
| `unknown_test_address` | 422 | A recipient at `test.mails.ai`, or at a subdomain of it, is not `reply@test.mails.ai`, the one test address. Nothing is sent, and `error.param` names the field it was in |
| `recipient_not_allowed` | 422 | A recipient in `to`, `cc` or `bcc` is outside the sending agent's `allowlist_domains` or on its `blocklist_domains`, with a test key too. The whole send is refused; the message names the address and the list. Remove the address or change the agent's lists |
| `agent_paused` | 422 | The agent is paused. Resume it with `PATCH /v1/agents/{id}`, unless mails.ai paused it. Creating an agent, with `POST /v1/agents` or with a send whose `from` names a new one, answers it too while any of the workspace's agents, archived ones included, carries a pause mails.ai set for abuse or for the workspace's bounce or complaint rate |
| `domain_not_verified` | 400, 422 | The custom domain is not verified, or its verification lapsed. Verify it with `POST /v1/domains/{id}/verify` |
| `rate_limit_exceeded` | 429 | Too many requests (sends: 100 per 10 seconds per API key). Wait `Retry-After`. Use `POST /v1/messages/batch` for bulk. With `param` `attachments`: more than 60 files fetched by `path` in a minute by one workspace, test keys included; send the bytes as `content_base64` instead |
| `hourly_limit_exceeded`, `daily_limit_exceeded` | 429 | The plan's cap on recipients in any hour or any 24 hours, or the sending agent's own `hourly_send_limit` or `daily_send_limit`. Only live sends count. A send counts once per address in `to`, `cc` and `bcc`. See "When to retry" |
| `new_workspace_fanout_exceeded` | 429 | The workspace reached its limit of different recipients (`to`, `cc` and `bcc` together) in 24 hours. The message states the limit, which is lowest for a new workspace and grows as it ages. A send only to addresses the workspace already wrote to in live sends of those 24 hours still goes |
| `monthly_limit_exceeded`, `free_tier_exceeded` | 429 | The plan's monthly cap on recipients, counted like the hourly and daily caps. It starts again with the next calendar month (UTC), at `error.resets_at`; change the plan to send sooner |
| `internal_error` | 500 | Retry with backoff. Quote `request_id` if it persists. From `POST /v1/drafts/{id}/send`, an answer that says the email was sent means the mail went out and only recording it failed: the draft is `sent`, its `error_message` says so, and the mail must not be sent again. One that says the draft was not sent leaves the draft as it was: send it again. A scheduled send that an error at mails.ai stopped is tried again on a later run, up to 3 attempts in all; if the last fails too, its `message.failed` or `draft.failed` event says `internal_error: not sent; an internal error stopped it (request req_…). It was tried 3 times.` |
| `upstream_error` | 502, 503 | 502: the email service did not confirm it took a send, so it is recorded as not sent, and the message gives a request id to quote to support. The key is freed, so a retry with the same `Idempotency-Key` sends it: retry with backoff. A draft whose send got this 502 is `failed` and cannot be sent again, so create a new draft, and a scheduled send that gets it fails at once. 503: a check that comes first, such as the forwarding test's limit, could not run, and nothing was done; retry after `Retry-After` |
| `upstream_unavailable` | 503 | The email service is not taking more mail right now, and nothing was sent. Send it again after `Retry-After` (60 seconds), with the same `Idempotency-Key`. A batch item that got it says the wait in `error.retry_after_seconds`, and a batch that stored no message and sent no mail frees its key too. A draft stays as it was. A scheduled send is tried again on a later run, up to 3 attempts in all |
| `service_unavailable` | 503 | Retry with backoff |

Keys can also carry the `draft` scope, so `insufficient_scope` may name it.
