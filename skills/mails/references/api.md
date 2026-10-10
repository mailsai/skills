# mails.ai REST API

Base URL `https://api.mails.ai`. Every path below also works with an `/api` prefix, for
example `/api/v1/me`. The full machine-readable description is at
`https://api.mails.ai/api/v1/openapi.json`.

## Authentication and keys

Send the key as a bearer token on every request:

```bash
curl https://api.mails.ai/v1/me -H "Authorization: Bearer $MAILS_API_KEY"
```

`GET /v1/me` answers with the key's mode, scopes and workspace. Call it first when you need
to know whether a key is a test key (`api_key.mode` is `test` or `live`).

| Key | What it does |
|---|---|
| `mk_test_...` | Runs the API: validation, stored messages, events, webhooks. Sends no email and bills nothing. A send that a live key would refuse as cold outreach succeeds and carries `classifier_warning`. A few requests need a live key: [testing.md](testing.md) names them. |
| `mk_live_...` | Sends real mail. |

A key has one or more scopes. Create keys with only what the code needs.

| Scope | Allows |
|---|---|
| `send` | `POST /v1/messages`, `POST /v1/messages/batch`, `POST /v1/messages/{id}/reply`, `POST /v1/messages/{id}/forward`, `POST /v1/drafts`, `POST /v1/drafts/{id}/send`, `POST /v1/test/inbound`, `POST /v1/messages/appeal` |
| `read` | every `GET` but `GET /v1/oauth/grants`: messages, received mail and its attachments, threads, drafts, events, the live stream, search, labels, metrics, agents, suppression, reputation, usage |
| `manage` | creating, changing and archiving agents, and testing an agent's forwarding; creating and revoking keys; creating, changing, testing and deleting webhooks, rotating their secrets and replaying deliveries; labels and domains; the send-anyway list (`POST /v1/suppression/allow`, `DELETE /v1/suppression/allow/{id}`); the billing portal; `PATCH` and `DELETE /v1/threads/{id}`; `PATCH` and `DELETE /v1/drafts/{id}`; cancelling and rescheduling messages; redelivering events; listing and revoking connected apps (`GET /v1/oauth/grants`, `DELETE /v1/oauth/grants/{id}`) |

A fourth scope, `draft`, creates, changes, lists and deletes drafts and cannot send anything.
Sending a draft still needs `send`. So does scheduling one: without `send`, a key can neither
give a draft a `send_at` nor change a scheduled draft, except to unschedule it with
`"send_at": null`. Rescheduling a message (`PATCH /v1/messages/{id}`), or scheduling one
again after its agent was paused, needs `send` as well as `manage`, and a live key for a live
message.

A scheduled message answers to the key that scheduled it, and rescheduling does not change
that. A scheduled draft answers to the key that last set its `send_at`. Once that key is
revoked or deleted, or the app that scheduled the mail is disconnected, the mail is not sent:
its `message.failed` event (in `data.reason`) or `draft.failed` event (in `data.error`) says
`scheduling_key_revoked`.

A scheduled send that an error at mails.ai stopped, or that the email service would not take
for now, is tried again on a later run (they run every minute), up to 3 attempts in all. It
fails only if the last attempt fails too, and its reason then ends `It was tried 3 times.` A
refusal, or an email service that did not confirm it took the mail, fails it at once. A new
`scheduled_at` or `send_at` starts the count again.

A key can also be bound to one agent: give the agent's `agt_` id as `agent_id` when you
create it with `POST /v1/api-keys` (a name there answers `404 agent_not_found`). A bound key
can only send as that agent. Without `agent`, a `from` that names any other agent answers
`403 insufficient_scope`, and no agent is created.

A bound key also reads only that agent's mail. Lists and search leave other agents' mail
out, and naming another agent in `agent_id` answers `403 insufficient_scope`. Another
agent's messages, threads, drafts, events and attachments answer `404`, as if they did not
exist, and so does any other agent on `GET /v1/agents/{id}`. `GET /v1/agents` lists only
the key's own agent, and `GET /v1/api-keys` only the keys tied to it. Webhooks and labels
belong to the whole workspace: a bound key can read them, but
creating, changing, testing or deleting them answers `403 insufficient_scope`, and so does
sending an event to the endpoints again (`POST /v1/events/{id}/redeliver` or
`POST /v1/webhook-deliveries/{id}/replay`), even one about its own agent. Connected apps
belong to the whole workspace too, and a bound key cannot list or revoke them: that answers
`403 insufficient_scope` as well.

A bound key cannot create agents, change its own agent's `allowlist_domains`, `blocklist_domains`
or send limits, revoke API keys, open billing, read the workspace's usage
(`GET /v1/billing/usage`; `GET /v1/metrics` counts its own agent's mail) or its log
(`GET /v1/logs`), list or change the send-anyway list (`GET /v1/suppression` without `address`
or `view`, and the routes under `/v1/suppression/allow`), or add, verify or
remove a domain (`403 insufficient_scope`). Changing or archiving another agent answers `404`, and so
does replying to or forwarding another agent's mail.

No key makes a key that reaches further than itself (`403 insufficient_scope`): a bound key
makes only keys bound to its agent, and no key can give a new key a scope it lacks, make a
live key if it is a test key, or make one that outlives its own `expires_at`.

## Conventions

- JSON in and out. Timestamps are UTC strings such as `2026-06-24T17:32:08.421Z`.
- Ids carry a prefix: `msg_` sent message, `rcv_` received message, `thrd_` thread,
  `evt_` event, `agt_` agent, `dft_` draft, `whe_` webhook, `whd_` webhook delivery,
  `dom_` domain, `key_` API key, `oag_` connected app.
- Where a request takes an agent, a name (`support`) and an `agt_` id both work, except
  `agent_id` on `POST /v1/api-keys`, which takes the id only.
- Lists take `limit` (1 to 100, default 25) and `cursor`, and answer
  `{"data": [...], "has_more": true, "next_cursor": "..."}`. Pass `next_cursor` back as
  `cursor` until `has_more` is false. `GET /v1/labels`, `GET /v1/domains` and
  `GET /v1/messages/received/{id}/attachments` answer everything at once and ignore both.
  `GET /v1/suppression` with `view=suppressed` ignores both too, and answers at most 500
  entries, with `has_more: true` when more are suppressed than that.
- Every response has an `X-Request-Id` header. Quote it when you report a problem.
- Errors look like this. Branch on `code`, never on `message`.

```json
{
  "error": {
    "type": "invalid_request_error",
    "code": "missing_field",
    "message": "Required",
    "param": "subject",
    "request_id": "req_01JZXD7R9T1V3X5Z7B9D1F3H5K"
  }
}
```

Most validation errors also list every bad field in `error.errors`. Read it when it is
there: a few, such as a `limit` out of range, have only `param`. A plan limit (402) adds
`upgrade_url`. The codes and what to do about each are in
[errors-and-retries.md](errors-and-retries.md).

## Send

```bash
curl https://api.mails.ai/v1/messages \
  -H "Authorization: Bearer $MAILS_API_KEY" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: order-1042-shipped" \
  -d '{"to": "reply@test.mails.ai", "subject": "Order 1042 has shipped", "body_text": "Your order is on its way.", "tags": [{"name": "kind", "value": "shipping"}], "metadata": {"order_id": "1042"}}'
```

Fields of `POST /v1/messages`:

| Field | Notes |
|---|---|
| `to` | one address, or a list of up to 50 |
| `cc`, `bcc` | lists of up to 50 |
| `subject` | required, up to 998 characters |
| `body_text`, `body_html` | at least one. `text` and `html` are accepted as other names for them |
| `agent` | the agent's name or `agt_` id. Leave it out when the workspace has one agent |
| `from` | another way to pick the agent by name: `billing`, `billing@example.com` and `Billing <billing@example.com>` all mean the agent called `billing`. An agent that does not exist yet is created if the key may create agents (the `manage` scope) and the plan has room; without `manage` the send answers `403 insufficient_scope`. An address at a custom domain you verified means the agent at exactly that address. Beside `agent` it picks nothing: `agent` decides the sender |
| `reply_to` | a reply-to address |
| `in_reply_to_message_id` | the id (`msg_` or `rcv_`) of the message this one answers. The send joins that message's thread when the same agent sent or received it, and starts a new thread otherwise |
| `references` | Message-IDs for the email's `References` header. They do not choose the thread |
| `attachments` | up to 10 of `{filename, content_base64, content_type}`, 25 MB in total after decoding. Files given as `content_base64` travel inside the request, so together they can come to about 3 MB: give a larger one by `path`. Instead of `content_base64`, `path` names an https URL that mails.ai downloads when it sends (`content_type` then optional); a file it cannot fetch refuses the send (`400 invalid_field`, `param` `attachments.0.path`), and a workspace may have 60 files fetched a minute (`429 rate_limit_exceeded`). `content_id` shows the file inside the HTML where it says `cid:<content_id>`; with no `html` it is sent as an ordinary attachment |
| `tags` | up to 10 of `{name, value}`; names use letters, digits, `_` and `-` |
| `metadata` | string keys (up to 64 characters) and string values (up to 500) |
| `scheduled_at` | a future time schedules the send. A scheduled send cannot carry `attachments` (`400 invalid_field`); a time in the past sends at once |
| `list_unsubscribe` | `true` adds one-click unsubscribe headers. Needs exactly one `to` and no `cc` or `bcc`. Off by default; the `email-best-practices` skill says when to use it |

The response (201) has `id`, `agent_id`, `from` (the agent's address), `thread_id`, `to`,
`subject`, `status`, `test_mode`, `created_at`, and on a test key the `classifier_warning`
described above. `status` is `sent`, `scheduled` for a future send, or `delivered` when
delivery to every recipient was confirmed as the send returned, as for a live send to
`reply@test.mails.ai` alone.

When the email service took the message for some recipients and refused others, the send
still counts as sent and `refused_recipients` lists the refused addresses: the message went
to everyone else. Sending it again with the same `Idempotency-Key` gives this answer back
and sends nothing, so check those addresses and send them a new message. The field is there
only when someone was refused, on this answer and on the batch, reply, forward and draft
send answers, `GET /v1/messages`, `GET /v1/messages/{id}` and the `message.sent` event.

`POST /v1/messages/batch` takes a list of up to 100 messages, each with the fields above
except `attachments`; `agent` and `from` pick each message's sender the same way. It answers
201 with one result per message in `data`: the sent message, or the `error` a single send
would get, so a message a send limit refused carries `resets_at` and `retry_after_seconds`,
and one the email service would not take for now `retry_after_seconds`. A repeat with the same
`Idempotency-Key` returns that whole answer again and sends nothing, so send the messages that
were refused in a new batch with a new key. The exception is a batch in which no message was
stored and no mail went out: its key is freed, so the same batch sent again with the same key
sends it.

## Read what was sent and received

| Request | Answer |
|---|---|
| `GET /v1/messages` | sent messages, newest first. Filters: `agent_id`, `thread_id`, `q` |
| `GET /v1/messages/{id}` | one sent message, with its delivery `status` |
| `GET /v1/messages/received` | received messages, newest first. Filters: `agent_id`, `thread_id`, `q` |
| `GET /v1/messages/received/{id}` | one received message, with `body_text`, `body_html` (only when the injection scan read it), the SPF, DKIM and DMARC results, `auth_failed` (`true` when the sender is likely forged) and `attachments` |
| `GET /v1/messages/{id}/raw` | the email as an `.eml` file. A sent message's is rebuilt from what mails.ai stored: one body (the HTML when there is one), without its files or Bcc. For received mail see [receiving.md](receiving.md) |
| `GET /v1/threads` | conversations, most recent activity first, without trash unless you pass `folder`. Filters: `agent_id`, `status`, `folder`, `read`, `label`, `mode`, `q`. A key lists its own mode's threads unless `mode` (`live`, `test`, `all`) says otherwise |
| `GET /v1/threads/{id}` | one conversation with every message, oldest first |
| `GET /v1/events` | events, newest first. Filters: `event_type`, `agent_id`, `since` |
| `GET /v1/events/{id}` | one event, including the scan details `injection_categories` and `classifier_model` |
| `GET /v1/search` | words in sent and received mail, newest first |

`q` on a list keeps the items whose subject or addresses contain it, ignoring case. On
`GET /v1/messages` and `GET /v1/messages/received` the `body_text` counts too, but not
`body_html`. Word search, folders, labels, attachments, the inbox summary and metrics are in
[receiving.md](receiving.md).

Received messages carry `injection_score` and `quarantined`, in the list and one at a time.

```bash
curl "https://api.mails.ai/v1/events?event_type=reply.received&limit=25" \
  -H "Authorization: Bearer $MAILS_API_KEY"
```

## Reply and forward

```bash
curl https://api.mails.ai/v1/messages/rcv_01JZXA2B4C6D8E0F2G4H6J8K0M/reply \
  -H "Authorization: Bearer $MAILS_API_KEY" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: reply-evt_01JZXA2B4C6D8E0F2G4H6J8K0N" \
  -d '{"body_text": "Thanks, your refund is on its way."}'
```

Reply to a sent message (`msg_` id) and it goes to that message's `to` addresses again.
`reply_all` copies its Cc too, after any `cc` you pass. Other fields: `body_html`, `cc`, `bcc`,
`reply_all`, `tags`, `scheduled_at`, `list_unsubscribe`.

Reply to a received message (`rcv_` id) and mails.ai addresses the reply to its Reply-To,
or to its `from` address (the From header) when it set none, and threads it. `reply_all`
also copies everyone else the message was sent or copied to, after any `cc` you pass, and
never the agent's own addresses.

`POST /v1/messages/{id}/forward` forwards a message to new recipients: `to`, and optionally
`cc`, `bcc`, `subject`, and `body_text` or `body_html` for a note above the original. A forward
of a received message sends that message's files with it, up to 10 files and 25 MB. A file
that cannot go is named in the body after `Not attached:`, and so is every file of a sent
message, because mails.ai keeps only their names.

## Agents

| Request | Use |
|---|---|
| `GET /v1/agents` | list agents, without archived ones unless `status` is `all` or `archived` (`active` and `paused` filter too) |
| `POST /v1/agents` | create one: `name` (lower-case letters, digits, `.`, `_`, `-`, up to 32), and `domain` to put it on a custom domain you verified, or `address` for the whole address there. `forwarding: true` turns forwarding on for an address on your own domain. On your mails.ai subdomain the agent sends and receives as `<name>.<workspace>`, which may have at most 64 characters: a longer one answers `400 invalid_param_value`, which says how long a name may be |
| `GET /v1/agents/{id}` | one agent, including `unread_count`, and `allowlist_domains` and `blocklist_domains` when they are set |
| `GET /v1/agents/{id}/inbox` | how many threads and unread threads it has, per folder, and per label among its threads in `inbox` |
| `PATCH /v1/agents/{id}` | pause or resume (`status`); set `allowlist_domains`, `blocklist_domains`, `hourly_send_limit` and `daily_send_limit`; turn `forwarding` on or off |
| `POST /v1/agents/{id}/forwarding/verify` | send a forwarding test; the `email-best-practices` skill shows the steps |
| `DELETE /v1/agents/{id}` | archive the agent, for good: an archived agent's status cannot change (`409 agent_archived`) |

How many agents a workspace may have depends on the plan. Creating one past the limit
answers `402 resource_cap_exceeded`.

`/v1/agents/{id}` and its inbox, the `agent` field and the `agent_id` filters take an
agent's name as well as its `agt_` id. Names are not unique. A key tied to one agent means
its own agent by its name, and a live agent wins over an archived one. When the name still
fits more than one agent, `POST /v1/messages`, the batch route, `POST /v1/drafts` and
`POST /v1/messages/appeal` use the oldest of them, and the other routes change nothing and
answer `409 agent_name_conflict`, naming each agent's id. A key tied to one agent never gets
that 409, which would name other agents to it. To that key, a name its own agent does not
have means the oldest agent with it, which it may not use: `/v1/agents/{id}` and its inbox
answer `404 agent_not_found`, and the `agent` field and the `agent_id` filters answer
`403 insufficient_scope`.

mails.ai applies an agent's settings to every send from it: new messages, batch items,
replies, forwards, drafts when they are sent, and scheduled mail when it goes out.

- A recipient in `to`, `cc` or `bcc` outside `allowlist_domains`, or inside
  `blocklist_domains`, refuses the whole send with `422 recipient_not_allowed`, test keys
  included. The message names the address and the list. A listed domain covers its
  subdomains, and case does not matter. `reply@test.mails.ai` is always allowed, whatever
  the lists say.
- A live send past `hourly_send_limit` or `daily_send_limit` is refused with
  `429 hourly_limit_exceeded` or `429 daily_limit_exceeded`, whose message names the limit.
  Both limits count recipients. A send counts once per address in `to`, `cc` and `bcc`, as
  it does against the plan's caps.
  Test sends are neither counted nor refused.

mails.ai does not filter incoming mail by the domain lists. The `agent-inbox` skill shows
how to apply them to incoming mail yourself.

## Everything else

`GET /v1/reputation`, `GET /v1/suppression`, `POST /v1/suppression/allow` and custom domains
(`POST /v1/domains` and the routes under it) are covered by the `email-best-practices`
skill. Webhooks (`POST /v1/webhooks` and the routes under it) are covered by the
`agent-inbox` skill. Drafts are in [receiving.md](receiving.md). Usage and the plan's caps:
`GET /v1/billing/usage`. Apps connected by signing in, and listing and revoking them with
`GET /v1/oauth/grants` and `DELETE /v1/oauth/grants/{id}`, are in [mcp.md](mcp.md).
