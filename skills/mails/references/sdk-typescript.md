# TypeScript SDK (`@mailsai/sdk`)

```bash
npm install @mailsai/sdk
```

Node.js 18 or newer. `createClient()` reads `MAILS_API_KEY`, and `MAILS_BASE_URL` when it is
set. Both can also be passed: `createClient({ apiKey, baseUrl })`. An empty value counts as
unset.

```ts
import { createClient, MailsError } from "@mailsai/sdk";

const mails = createClient();

try {
  const me = await mails.me();
  console.log(me.workspace?.slug, me.api_key.mode, me.api_key.scopes);
} catch (error) {
  if (error instanceof MailsError) console.error(error.status, error.code, error.message, error.requestId);
  else throw error;
}
```

## Calls

Every operation an API key can call has a method, and the package's README lists them all.
The ones agents use most:

| Call | Endpoint |
|---|---|
| `mails.send({ to, subject, body_text, idempotency_key, ... })` | `POST /v1/messages` |
| `mails.messages.batch([...], { idempotency_key })` | `POST /v1/messages/batch` |
| `mails.messages.reply(id, { body_text, idempotency_key })` | `POST /v1/messages/{id}/reply` |
| `mails.messages.forward(id, { to, idempotency_key })` | `POST /v1/messages/{id}/forward` |
| `mails.messages.get(id)`, `mails.messages.list({ agent_id, thread_id })` | `GET /v1/messages/{id}`, `GET /v1/messages` |
| `mails.messages.cancel(id)`, `mails.messages.reschedule(id, at)` | `POST /v1/messages/{id}/cancel`, `PATCH /v1/messages/{id}` |
| `mails.messages.raw(id)` | `GET /v1/messages/{id}/raw`, the email as text |
| `mails.received.list(...)`, `mails.received.get(id)` | `GET /v1/messages/received`, `GET /v1/messages/received/{id}` |
| `mails.received.wait({ from, to, has, since, timeout })`, the newest match as soon as it arrives, with its codes and links | `GET /v1/messages/received/wait` |
| `mails.received.attachments.list(id)`, `mails.received.attachments.download(id, attachment_id)` | `GET /v1/messages/received/{id}/attachments`, `GET /v1/messages/received/{id}/attachments/{attachment_id}`; `download` returns the file's bytes as a `Uint8Array` |
| `mails.search({ q })` | `GET /v1/search` |
| `mails.threads.list(...)`, `.get(id)`, `.update(id, { status, labels })`, `.remove(id)` | `GET /v1/threads`, `GET /v1/threads/{id}`, `PATCH /v1/threads/{id}`, `DELETE /v1/threads/{id}` |
| `mails.labels.list()`, `.create({ name, color })` | `GET /v1/labels`, `POST /v1/labels` |
| `mails.drafts.create(...)`, `.send(id, { idempotency_key })`, `.list()`, `.get(id)`, `.update(id, ...)`, `.remove(id)` | `/v1/drafts` and the routes under it |
| `mails.events.list({ event_type, agent_id, since, limit, cursor })`, `.get(id)`, `.redeliver(id)` | `GET /v1/events`, `GET /v1/events/{id}`, `POST /v1/events/{id}/redeliver` |
| `mails.agents.create(name, { domain })`, `.list()`, `.get(id)`, `.update(id, ...)`, `.archive(id)` | `/v1/agents` and `/v1/agents/{id}` |
| `mails.agents.verifyForwarding(id)` | `POST /v1/agents/{id}/forwarding/verify` |
| `mails.webhooks.create({ url, event_types })`, `.list()`, `.update(...)`, `.test(id)`, `.remove(id)` | `/v1/webhooks` and the routes under it |
| `mails.webhooks.verify(rawBody, signatureHeader, secret)` | checks a webhook signature and its time, which must be within 300 seconds of your clock (a fourth argument, in seconds, changes that); returns the event or `null` |
| `mails.domains.list()`, `.create(domain)`, `.get(id)`, `.verify(id)` | `/v1/domains` and the routes under it |
| `mails.reputation.get(agent?)` | `GET /v1/reputation` |
| `mails.suppression.check(address)`, `.allow(address, attestation)`, `.list()`, `.revoke(id)` | `GET /v1/suppression?address=`, `POST /v1/suppression/allow`, `GET /v1/suppression`, `DELETE /v1/suppression/allow/{id}` |
| `mails.billing.usage()` | `GET /v1/billing/usage` |
| `mails.request(method, path, body?, headers?)` | any endpoint that answers JSON, for example `mails.request("GET", "/v1/domains")` |

## Things to know

- **Use `body_text`**, the API's own field name, on every call. `send`, `messages.batch` and
  `messages.reply` also take `body` as a shorthand for it; `messages.forward` does not.
- **Idempotency keys.** `send`, `messages.reply`, `messages.forward` and `drafts.send` take
  `idempotency_key`, and `messages.batch` takes it in its second argument. The SDK makes up
  no key of its own. No other call sends a key: no other route reads one, so a key added to
  another request with `mails.request` only makes the SDK repeat that request after a 5xx.
  A repeat with the same key within 24 hours returns the first response instead of sending
  again; a repeat that changes the body answers `400 invalid_idempotency_key` and sends
  nothing. Build the key from what makes the message unique, such as the event a reply
  answers:

```ts
import { createClient } from "@mailsai/sdk";

const mails = createClient();
const receivedId = "rcv_01JZXA2B4C6D8E0F2G4H6J8K0M"; // data.source_message_id of the event
const eventId = "evt_01JZXA2B4C6D8E0F2G4H6J8K0N";

const reply = await mails.messages.reply(receivedId, {
  body_text: "Thanks, your refund is on its way.",
  idempotency_key: `reply-${eventId}`,
});
console.log(reply.id, reply.thread_id);
```

- **Retries.** The SDK retries a 429 and, for a `GET` or a request with an
  `Idempotency-Key`, a 5xx: up to 3 retries, waiting `Retry-After` when the API sends it,
  otherwise 0.5 s, 1 s, 2 s. It waits at most 60 seconds before a retry, and
  `createClient({ maxRetryWaitSeconds })` can lower that. It does not retry a network error
  (a failed `fetch`): the call throws `fetch`'s own error, not a `MailsError`. Retry that
  yourself with the same idempotency key.
- **Long limits.** The API sends `Retry-After` only for a wait of a minute or less. So when a
  limit resets later, such as a daily or monthly cap, the call throws `RateLimitError` at
  once, with a message that says when to try again; see
  [errors-and-retries.md](errors-and-retries.md). Its `resetsAt` is when the limit resets, or
  `null` when waiting cannot help, and `retryAfterSeconds` is how many seconds away that is.
  `RateLimitError` is a `MailsError`, so a `catch` for `MailsError` catches it too.
- **Fields the types leave out.** A received message also carries `injection_score` and
  `quarantined`, and an event carries `classifier_model` (and, from `events.get`,
  `injection_categories`). Read them with `request<YourType>()`.
- **Files.** `mails.received.attachments.download(id, attachment_id)` returns a file's bytes,
  and `mails.messages.raw(id)` the whole email as text; see [receiving.md](receiving.md).
- **Streams reconnect.** `events.stream()`, `agent.onReply()` and `agent.onMessage()` open
  the stream again after the server closes it (about every 50 seconds) or the network
  drops, and carry on from where the stream was. An event the server sends again is not
  handed to `onEvent` a second time, and one that was written late arrives after newer ones
  instead of being skipped. Before the first event, they carry on after the newest event
  there was when they started, so nothing is missed in between. To carry on after a
  restart, save what `onPosition` gives you and pass it as `since`. An event handled before
  the restart can come again then, so keep the ids you handled if that matters. You can
  also pass `since`, the id of the last event you handled (`evt_…`), not a time as on
  `events.list`: a time sorts before every id, so the whole history is sent again. An event
  id starts after that event, so an event written late while you were away is missed.
  `onError` hears each failure and the stream keeps going; a `401` or `403` ends it, and
  without `onError` that last error is written to `console.error`. Stop it with the
  `AbortController` they return. `agent.onReply()` and `agent.onMessage()` look their agent
  up by name or `agt_` id at the first event. When that fails, for example because no agent
  has the name or two do (`409 agent_name_conflict`, so use the id), they hand over nothing:
  `onError` hears why, or without it `console.error` says so once. Webhooks are still
  simpler for a listener that runs for hours.
