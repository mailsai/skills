# Receiving mail

## Where mail arrives

- Every send carries the agent's `receiving_address` as its Reply-To, so replies come back
  to the agent without any setup. If you set `reply_to` on a send, replies go to that
  address instead and the agent never sees them.
- People and services can write to the agent first at its `receiving_address`, which
  `GET /v1/agents/{id}` returns. It is `<agent>.<workspace>@in.mails.ai`, for example
  `support.acme@in.mails.ai` for the agent `support` in the workspace `acme`, and
  `<agent>@in.mails.ai` when the agent's name is the same as the workspace's. For an agent
  on your own domain it is the name and the whole domain with its dots written as
  underscores: `billing.example_com@in.mails.ai` for `billing@example.com`. Where that would
  pass 64 characters before the `@`, the domain is cut short and ends in `_` and 10
  characters of a hash, so read the address from the API rather than building it.

- Mail to any plus address of the `receiving_address` reaches the agent too: add `+` and
  anything before the `@`, such as `support.acme+github@in.mails.ai`. So one agent can give
  each service, or each test run, an address of its own, and each received message says
  which address it came to in `delivered_to`. A workspace may receive mail at 20 different
  plus addresses a day on Free, 1,000 on Pro and 10,000 on Scale. Past that, mail to a new
  one keeps only a record (`over_limit: "plus_address_limit"`) and raises
  `message.received.over_limit`; the addresses already used that day keep working. The tag
  goes at the end, just before the `@`: one written inside the address is refused when it could
  be meant for another agent. The part before the `@` holds at most 64 characters, so a long
  receiving address leaves less room for a tag. A sign-in code, or a verify, sign-in or
  password-reset link, from a service such as Google, Microsoft, Apple, a payment app or a bank
  never reaches a plus address: such mail keeps only a record (`over_limit: "held_code"`), and
  no wait finds it. Sign up for those services at the agent's own address.

- The agent's `email` (`support@acme.mails.ai`) names it in the API. Recipients see its mail
  come from an address under `send.mails.ai`, such as `support.acme@send.mails.ai`, with
  `support` as the display name and the `receiving_address` as Reply-To. Mail sent to
  `support@acme.mails.ai` is not received.

- An agent at an address on your verified domain (`support@example.com`) can also get the
  mail people send to that address, with no MX change: create it with `"forwarding": true`,
  forward the address from your existing mail service to the agent's `forwarding_address`
  (the same as its `receiving_address`), and `POST /v1/agents/{id}/forwarding/verify` sends
  one test through the forward and sets `forwarding_status` to `verified` when it arrives.
  Forwarded mail is received like any other, with the agent's own address as the recipient.

## What arrives

Each received email is stored (`rcv_` id), joins a thread, gets an injection score, and
becomes one event:

| Event | When |
|---|---|
| `reply.received` | it replies to a message the agent sent. `data.thread_root_message_id` is that message's `msg_` id |
| `message.received` | any other mail |
| `message.received.unauthenticated` | the From domain's DMARC policy is `quarantine` or `reject`, and no DKIM signature from that domain verified, so the sender is likely forged. This comes first: such a reply is this event |
| `message.received.over_limit` | the mail arrived while the workspace was over a limit. It gets no injection score, and this event, with no subject or body, takes the place of the other three (see below) |

A DKIM signature that could not be checked counts as unknown, not as failed, and real mail
from a domain without such a policy never gets this event (mail made with
`POST /v1/test/inbound` follows its request, as [testing.md](testing.md) says). Nor does
forwarded mail whose forwarding service vouched for the sender: `data.trusted_forwarder` then
names that service. `data.from` is the first mailbox of the email's From header, or the
envelope sender when that header holds no address, and `data.envelope_from` the envelope
sender, where bounces go. Trust `data.from.address` only when `data.dmarc` is `pass`, as the
agent-inbox skill shows.

Mail that scores as near-certain prompt injection still arrives, with `quarantined: true`
on its event. Check it before acting on the mail; the `agent-inbox` skill shows how.

Over the plan's monthly limit for received mail, or while the subscription is inactive,
new mail is stored but not scanned: its `parse_status` is `quota_skipped`. It still joins a
thread, and its event is `message.received.over_limit`, which says who sent it and which
limit it was over (`over_limit`) but carries no subject or body. Past the plan's hourly or
daily rate, mails.ai keeps only who sent the mail, to whom and when (at most 20 records a
workspace each hour) and raises the same event.

Received mail also files its thread, and two thread events say so: `thread.created` when
the mail starts a conversation, and `thread.updated` when a reply brings a thread back from
trash or sent to the inbox. Both are in `GET /v1/events` and the live stream. A webhook gets
them only when it names them. `thread.created` gives the subject only of mail the injection
scan read and did not quarantine; otherwise its `subject` is `null`. Mail made with
`POST /v1/test/inbound` follows the same rule, so a test can see both.

## Sign-up codes and links

An agent that signs up for a service, signs in to one or resets a password gets a code or a
link by email. A received message carries them already picked out, by fixed rules with no AI
involved: `codes`, each a `value` with the likeliest first, and `links`, each a `url` and a
`kind` (`verify`, `sign_in`, `reset_password`, `unsubscribe` or `other`) with the action links
first. `GET /v1/messages/received` and `GET /v1/messages/received/{id}` return both.

`GET /v1/messages/received/wait` answers as soon as the mail arrives, so the agent needs no
polling loop or webhook for it:

```bash
curl "https://api.mails.ai/v1/messages/received/wait?from=github.com&has=code&timeout=50" \
  -H "Authorization: Bearer $MAILS_API_KEY"
```

- `from` is an address or a domain, and a domain includes its subdomains: `github.com` takes
  `mail.github.com`, never `github.com.evil.example`. It matches the From header, so check
  that the message's `dmarc` is `pass` before you trust who sent it.
- `has=code` waits for a message with a code, and `has=link` for one with a `verify`,
  `sign_in` or `reset_password` link.
- `to` takes only mail sent to that address, such as the plus address the agent gave this
  service (`to=support.acme%2Bgithub%40in.mails.ai`: write the `+` as `%2B`). The SDKs build
  one with `plusAddress()` (TypeScript) and `plus_address()` (Python), and encode it.
  When the newest mail sent to `to` came past the plan's plus addresses a day, only a record
  of it was kept, so the call answers 402 `plan_limit_exceeded` at once instead of waiting.
- `since` is when the agent asked the service to send, so an older code never answers.
  Without it the call looks back 5 minutes.
- `timeout` is 0 to 50 seconds (default 30). Nothing in time is not an error: `message` is
  `null` and `timed_out` is `true`.
- Mail judged forged (`auth_failed`) and quarantined mail never match.
- The MCP tool is `mails_wait_for_email`, the CLI command `mails receiving wait`, and the SDK
  methods `received.wait()` (TypeScript) and `wait_for_received()` (Python). The `from`, `to`
  and `since` filters work on `GET /v1/messages/received` too.

## Getting events

### Webhooks

Create an endpoint with a key that has the `manage` scope and is not tied to an agent:

```bash
curl https://api.mails.ai/v1/webhooks \
  -H "Authorization: Bearer $MAILS_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com/mails/webhook", "event_types": ["reply.received", "message.received", "message.received.unauthenticated"]}'
```

- The URL must be `https` and reachable from the internet. `event_types` defaults to
  `["*"]`, every event except `thread.created`, `thread.updated`, `thread.deleted` and
  `message.delayed`: an endpoint gets those only when it lists them. An unknown type is
  refused, and so is an empty list (`422 invalid_param_value`).
- The answer includes `signing_secret` (`whsec_...`). It is shown once. Store it.
- Each delivery is a `POST` with the event as JSON and the headers `X-Mails-Signature`,
  `X-Mails-Event-Id` and `X-Mails-Event-Type`. Verify the signature before anything else,
  as the `agent-inbox` skill shows.
- Answer with any 2xx within 5 seconds. Otherwise mails.ai tries twice more, about 30
  seconds and then 2 minutes later. After the third failure it stops.
- A delivery can arrive more than once. Use the event `id` to skip repeats.
- `GET /v1/webhooks/{id}/deliveries` lists the attempts. `POST /v1/events/{id}/redeliver`
  sends an event again, and `POST /v1/webhooks/{id}/test` sends a `webhook.test` event.
- `POST /v1/webhooks/{id}/rotate-secret` replaces the signing secret. The old one keeps
  signing for 24 hours, so no delivery fails while you switch; the `agent-inbox` skill
  shows how.

### Polling

`GET /v1/events?event_type=message.received&since=2026-01-31T12:00:00.000Z&limit=100`
returns events newest first.

- `since` is a time written like `2026-01-31T12:00:00Z`, or `2026-01-31T21:00:00+09:00`
  with an offset. A time with no offset is UTC, and a date such as `2026-01-31` means
  midnight UTC. Anything else answers `400 invalid_param_value`.
- `since` includes events created at exactly that time. Keep the ids you handled and skip
  them.
- `created_at` is set as an event is written, and the event can be read only once that write
  is finished, so it can turn up after newer ones. Start each poll 10 minutes before the
  newest `created_at` you handled, as the `agent-inbox` pollers do: the ids you keep skip
  what comes back.
- Follow `next_cursor` while `has_more` is true, or you miss older events in a busy period.
- Ask for each inbound type, or leave out `event_type` and filter, so you do not miss
  `message.received.unauthenticated`.

The `agent-inbox` skill has a complete poller that saves its position.

### Live stream

`GET /v1/events/stream` sends events as server-sent events, oldest first. The connection
closes after about 50 seconds. `event_types` takes a comma-separated list. For an agent
that runs for hours, webhooks or polling are simpler.

The stream also says where it is: an `id:` line with no data, such as
`id: evt_01JZXA2B4C6D8E0F2G4H6J8K2P~48213`, when it opens and after each batch of events.
That is its position. Reconnect with `since` (or the `Last-Event-ID` header) set to the
last position you read. An `EventSource` client does that by itself when its address has no
`since`, which would win over the header.

Handle each event `id` once. Delivery is at least once, so an event can arrive a second
time after a reconnect. Events arrive in id order, except one that was written late: it
arrives after newer ones instead of being skipped. One that turns up more than ten minutes
late is not sent. `since` also takes a plain event id and then starts after that id, but
only a position still gets you an event that was written late.

Without `since` or `Last-Event-ID`, the stream starts at the newest event and does not
replay older ones. A listener that restarts must pass the position it saved, or it misses
what arrived while it was down.

The SDK streams reconnect for you. After the server closes the stream or the network drops,
they open it again from the stream's last position, waiting 1 second and then twice as
long after each failed attempt, up to 30 seconds. While they run they do not hand you the
same event twice. They hand you each position too (`onPosition` in TypeScript,
`on_position` in Python): save it, and pass it as `since` when your program starts again.
Opened without `since`, they first read the newest event's id
(`GET /v1/events?limit=1`) and start from it, so a reconnect before the first event misses
nothing either. A `401` or `403` ends the stream, because retrying cannot fix the key.
`onError` in TypeScript and `on_error` in Python hear each failure.

## Reading a received message

`GET /v1/messages/received/{id}` returns the whole message: `from`, `envelope_from`, `to`,
`subject`, `body_text`, `body_html`, `extracted_text` (the new text without the quoted
history), `has_attachment`, `attachments`, `thread_id`, `in_reply_to_message_id`,
`received_at`, and the authentication results.

`spf_pass` and `dkim_pass` are each `true`, `false`, or absent when unknown. SPF is never
checked on real mail, so its `spf_pass` is absent; test mail carries what its request said.
`dkim`, `dkim_domain`, `dmarc` and `auth_failed` are as on the message's event: trust
`from.address` only when `dmarc` is `pass`. Mail received before these fields were added has
`dkim` and `dmarc` `unknown`, and its `envelope_from` can be null. Mail kept over a limit may
not have been checked: then it reads `unknown` too, with `auth_failed: false`.

- `body_html` is there only when the injection scan read the message. Mail whose scan
  failed has `body_text` alone.
- `body_text` may be cut at 100,000 characters, and cut text ends with a line that says so.
  The raw email holds the whole message when mails.ai kept it.
- `GET /v1/messages/{id}/raw` returns the email as an `.eml` file: the original bytes,
  attachments included, when mails.ai kept them (up to 25 MiB, within the plan's daily
  allowance), otherwise one rebuilt from the stored fields. `raw_omitted` on the message
  says why the original was not kept.

Received messages, in the list and one at a time, also carry `injection_score` and
`quarantined`. Both are `null` for a message that was never classified.

## Attachments

Received messages carry `has_attachment` and `attachments`: each file's `id` (`att_...`),
`filename`, `content_type`, `size`, `content_id` and `inline` (`true` for an image shown
inside the HTML).

- `GET /v1/messages/received/{id}/attachments` lists them. Files that cannot be downloaded
  are under `omitted`, each with a `reason`: `too_many` for a file past the first 100,
  otherwise the reason the raw email was not kept. `raw_omitted` says why the raw email was not
  kept: over 25 MiB, or over 3 MB and not sent in parts (`too_large`), past the plan's
  daily allowance (`budget`), stored while the workspace was over a limit (`over_quota`),
  or not available (`unavailable`).
- `GET /v1/messages/received/{id}/attachments/{attachment_id}` downloads one. It is always
  a download (`Content-Disposition: attachment`) with a safe `Content-Type`; `?inline=1`
  shows PNG, JPEG, GIF, WebP, AVIF and BMP images instead. The `ETag` is the file's
  SHA-256.
- The SDKs download them: `client.download_attachment(id, attachment_id)` returns the
  file's `bytes` in Python, and `mails.received.attachments.download(id, attachment_id)` a
  `Uint8Array` in TypeScript. `rest.py` reads JSON answers only, so without the SDK download
  with your own HTTP client:

```bash
curl -fsS -o invoice.pdf \
  https://api.mails.ai/v1/messages/received/rcv_01JZXA2B4C6D8E0F2G4H6J8K0M/attachments/att_01JZXA2B4C6D8E0F2G4H6J8K0R \
  -H "Authorization: Bearer $MAILS_API_KEY"
```

The `mails` command line downloads them too:
`mails receiving attachment rcv_01JZXA2B4C6D8E0F2G4H6J8K0M att_01JZXA2B4C6D8E0F2G4H6J8K0R --output invoice.pdf`,
and `mails emails raw rcv_01JZXA2B4C6D8E0F2G4H6J8K0M --output message.eml` saves the whole email.

mails.ai never scans attachments or the raw email for prompt injection. Do not hand their
contents to a model as if they had been checked.

## Replying

`POST /v1/messages/{id}/reply` with the `rcv_` id (`data.source_message_id` on the event).
Send an `Idempotency-Key` built from the event id, such as `reply-evt_...`, so handling the
same event twice within 24 hours sends one reply. mails.ai keeps a key for 24 hours.

mails.ai sends the reply to the message's Reply-To, or to its `from` address when it set
none (never to `envelope_from`), sets the threading headers and adds the reply to the thread.
With `reply_all` it also copies the message's other recipients, never the agent itself.
Mail kept over the monthly limit or while the subscription is inactive keeps its Reply-To and
other recipients. A record kept past the hourly or daily rate, or the plan's plus addresses a day, has neither: a reply to it goes
to its `from` address, and `reply_all` adds no one.

A live key cannot reply to test mail, such as mail from `POST /v1/test/inbound`: it answers
`403 test_mode_required`, because the sender is whatever address the test gave. A test key's
reply to it is a test send, and so is a reply from a signed-in dashboard session that sends the
header `X-Mails-Mode: test`. That header does not change an API key's mode: a live key that
sends it gets the same 403.

## Threads

- `GET /v1/threads` lists conversations, most recent activity first. Filters: `agent_id`,
  `status`, `folder`, `read` (`true` or `false`) and `label` (a name or a `lbl_` id).
  Without `folder` the list leaves out trash; `folder=all` includes it.
  A key lists the threads of its own mode, as the inbox's unread counts count them: a live
  key, threads that hold live mail; a test key, threads of test mail only. `mode` (`live`,
  `test` or `all`) picks another, and each thread's `test_mode` says which it is.
- `GET /v1/threads/{id}` returns every message, sent and received, oldest first.
- `PATCH /v1/threads/{id}` sets `read`, `folder`, `status` (`open`, `closed`, `archived`)
  and the thread's labels: `labels` (up to 50 names) or `label_ids`. It needs the `manage`
  scope. A request that changes something emits one `thread.updated`, whose `changes` lists
  the fields it changed; one that changes nothing emits none.
- `DELETE /v1/threads/{id}` (the `manage` scope) moves a thread to trash. Sent again for a
  thread already there, it changes nothing, so a retry never destroys mail.
- `DELETE /v1/threads/{id}?permanent=true` deletes a thread for good, from any folder: its
  messages' text, attachments and raw email, and the events and webhook deliveries that
  copied them. Reading any of them then answers `404`, and `thread.deleted` is emitted. It
  cannot be undone. While one of its messages is being sent, it deletes nothing and answers
  `409 duplicate_resource`: try again once the message has gone out.
- An app someone connected by signing in can move a thread to trash but not delete it for
  good: `?permanent=true` answers it `403 connected_app_not_allowed`. Delete for good with an
  API key that has `manage`, or as an owner or admin in the dashboard or with the `mails` CLI.
- A test key cannot move a thread that holds live mail to trash or delete it
  (`403 live_mode_required`). It can change everything else.
- Test mail never joins a thread that holds live mail. It starts a thread of its own, even
  when it answers a live message.

### Folders and read state

Each thread has `read` and one `folder`:

| `folder` | |
|---|---|
| `inbox` | where received mail starts a thread |
| `sent` | a thread that holds only mail the agent sent. Its first reply moves it to `inbox`. A thread cannot be moved here (`422 invalid_param_value`) |
| `archive` | the same as `status: "archived"`: setting either sets both, and moving the thread elsewhere reopens it. New mail leaves the thread here |
| `spam` | the thread stays there when new mail arrives |
| `trash` | new mail moves the thread back to `inbox`. Otherwise mails.ai deletes it for good 30 days after it reached trash |

Received mail marks its thread unread (`read: false`), whatever the folder.

## Drafts

A draft is a message that waits for a person or for a time.

- `POST /v1/drafts` takes `agent`, `to`, `subject`, `body_text` and, for a reply,
  `in_reply_to_message_id` (the `rcv_` id). Its send is judged as a reply to that message,
  as `POST /v1/messages/{id}/reply` is, when the draft is from the agent the message came to
  and every `to` address was on the message. Otherwise it is judged as a first message: see
  the `email-best-practices` skill.
- A person reads, edits and sends it at `https://app.mails.ai/drafts/<draft id>`, or your
  code sends it with `POST /v1/drafts/{id}/send`.
- A future `send_at` schedules it, whichever call sets it, and raises `draft.scheduled`.
  `GET /v1/drafts` lists drafts, and `PATCH /v1/drafts/{id}` changes one until it starts
  sending; after that a change is refused. A change, or a new `send_at` on
  `POST /v1/drafts/{id}/send`, that arrives as the draft starts sending answers
  `409 duplicate_resource`: read the draft again. So does `DELETE /v1/drafts/{id}` on a
  draft that is being sent, and `POST /v1/drafts/{id}/send` on one that is already being sent.
- A send that fails once the draft has started sending, before the mail has gone out, leaves
  the draft as it was, with no `draft.failed`, when the email service is only not taking more
  mail right now (`503 upstream_unavailable`, with `Retry-After: 60`) or an error at mails.ai
  stopped it (`500 internal_error`, which says the draft is as it was). Send it again then.
- Any other failure before the mail has gone out makes the draft `failed`, with a
  `draft.failed` event: `502 upstream_error` when the email service did not confirm it took
  the mail, `422 recipient_suppressed` when it refused every recipient, or a refusal such as
  `domain_not_verified`. The draft's `error_message` and the event's `data.error` are that
  code and the answer's message, such as `upstream_error: The email service did not confirm
  it took this message, …`. A `failed` draft cannot be sent, and can be changed only when it
  failed for its agent, as the point on paused and archived agents says. Otherwise create a
  new draft.
- A draft the email service took for some recipients and refused for others is `sent`, and
  the send's answer names the refused ones in `refused_recipients`.
- A send that fails after the mail has gone out answers `500 internal_error`, whose message
  says the send ran but recording it did not finish. The draft is then `sent`, its
  `error_message` reads `sent; recording it failed (request req_…)`, and no `draft.failed`
  event is raised. A scheduled draft whose mail went out ends the same way when recording
  it fails. Do not send it again: read it with `GET /v1/drafts/{id}`. A retry with the same
  `Idempotency-Key` gets the same answer back, and one without it answers
  `400 invalid_field`.
- A scheduled draft that an error at mails.ai stopped, or that the email service would not
  take for now, is tried again on a later run (they run every minute), up to 3 attempts in
  all. If the last one fails too, the draft becomes `failed`, and its `draft.failed` error
  ends `It was tried 3 times.` Any other failure fails it at once. A new `send_at` starts the
  count again.
- A scheduled draft whose agent was paused or archived by its time is not sent. It becomes
  `failed`, and `draft.failed` carries the error a send from that agent gets
  (`agent_paused: …`, `agent_archived: …`) in `data.error`. Once a paused agent is resumed,
  `PATCH /v1/drafts/{id}` with a new `send_at` schedules it again; any other change makes it
  a draft again. Archiving cannot be undone.
- A draft is checked when it is sent, as any send is. Content that looks like cold outreach
  is refused then (`422 cold_email_prohibited`). A scheduled draft with such content
  becomes `failed`, with `cold_email_prohibited: …` in its `draft.failed` event's
  `data.error`. With a test key the draft goes through, and `POST /v1/drafts/{id}/send`
  answers with `classifier_warning`, as any test send does.

A key with the `draft` scope creates, changes, lists and deletes drafts but cannot send
them; sending a draft needs `send`, and so does giving it a `send_at`. Changing a scheduled
draft needs `send` too, except to unschedule it with `"send_at": null`. Give that key to code
that prepares mail for a person to approve.

## Labels

A label is a name with a color, shared by the whole workspace. A thread's `labels` are
names: a name that matches a label also brings its id (in `label_ids`), and any other name
works without one. The color is on the label, and on the labels of
`GET /v1/agents/{id}/inbox`, not on the thread.

- `GET /v1/labels` lists labels, and `POST /v1/labels` makes one, for example
  `{"name": "billing", "color": "blue"}`. `color` is one of `gray` (the default), `red`,
  `orange`, `amber`, `yellow`, `green`, `teal`, `cyan`, `blue`, `indigo`, `purple` and
  `pink`.
- Names are unique, ignoring case. A workspace can have 200 labels; past that, creating one
  answers `409 resource_cap_exceeded`.
- `PATCH /v1/labels/{id}` renames or recolors a label, and every thread that carries it
  gets the new name. `DELETE /v1/labels/{id}` removes it from every thread.
- Creating, changing and deleting labels needs the `manage` scope and a key that is not
  tied to an agent.

## Search

`GET /v1/search?q=invoice` searches the subject, text and addresses of sent and received
mail, newest first. Each hit has `type` (`received` or `sent`), `id`, `thread_id`,
`agent_id`, `subject`, `from`, `to`, `date`, `has_attachment`, `folder`, `labels` and a
`snippet` of the text around the match.

- Every word in `q` must appear, as a whole word or, from three letters on, as the start of
  one. `q` takes up to 16 words and 200 characters.
- Filters: `agent_id`, `from` and `to` (part of an address), `after` and `before` (a date
  such as `2026-10-04`, or a time), `has_attachment`, `folder`, `label` and `type`. Without
  `folder`, search leaves trash out.
- A test key searches test mail and a live key live mail. A key tied to one agent searches
  that agent's mail only.
- A search that runs longer than 5 seconds is stopped with `400 invalid_param_value`: add a
  word or a filter. A workspace can search 120 times a minute, then gets
  `429 rate_limit_exceeded` with `Retry-After`.

`q` on `GET /v1/threads`, `GET /v1/messages` and `GET /v1/messages/received` is simpler: it
keeps the items whose subject or addresses (and, for messages, text) contain it anywhere,
ignoring case.

## Inbox summary and metrics

- `GET /v1/agents/{id}/inbox` sums up one agent's mail: `unread_count` (unread threads in
  `inbox`), `threads` and `unread` for each folder, every label on its inbox threads with
  the same two counts, and `last_message_at`. Agents carry `unread_count` too. The unread
  counts follow the key's mode: a test key counts threads of test mail, a live key threads
  that hold live mail, and the dashboard counts both.

- `GET /v1/metrics` counts `sent`, `delivered`, `bounced`, `complained`, `received` and
  `replies` per day (the last 30 days unless `from` and `to` say otherwise) or per hour
  (`interval=hour`, the last 48 hours). One call covers up to 366 days or 744 hours, and
  `agent_id` narrows it to one agent. A test key counts test mail and a live key live mail.
