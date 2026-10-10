# Python SDK (`mailsai`)

```bash
pip install mailsai
```

Python 3.10 or newer. `Client()` reads `MAILS_API_KEY`, and `MAILS_BASE_URL` when it is
set. Both can also be passed: `Client(api_key=..., base_url=...)`. An empty value counts as
unset.

```python
from mailsai import Client, MailsError

client = Client()
try:
    me = client.me()
    print(me["workspace"]["slug"], me["api_key"]["mode"], me["api_key"]["scopes"])
except MailsError as error:
    print(error.status, error.code, error.message, error.request_id)
```

Every method returns the API's JSON as a dict, except `get_raw_message`, which returns the
email as a `str`, and `download_attachment`, which returns the file's `bytes`.

## Methods

Every operation an API key can call has a method, and the package's README lists them all.
The ones agents use most:

| Method | Endpoint |
|---|---|
| `client.send(to=..., subject=..., body_text=..., idempotency_key=...)` | `POST /v1/messages` |
| `client.batch_send(messages, idempotency_key=...)` | `POST /v1/messages/batch` |
| `client.reply(message_id, body_text=..., idempotency_key=...)` | `POST /v1/messages/{id}/reply` |
| `client.forward(message_id, to=..., idempotency_key=...)` | `POST /v1/messages/{id}/forward` |
| `client.get_message(id)`, `client.list_messages(agent_id=..., thread_id=...)` | `GET /v1/messages/{id}`, `GET /v1/messages` |
| `client.cancel_message(id)`, `client.reschedule_message(id, scheduled_at)` | `POST /v1/messages/{id}/cancel`, `PATCH /v1/messages/{id}` |
| `client.get_raw_message(id)` | `GET /v1/messages/{id}/raw` |
| `client.list_received(...)`, `client.get_received(id)` | `GET /v1/messages/received`, `GET /v1/messages/received/{id}` |
| `client.list_attachments(id)`, `client.download_attachment(id, attachment_id)` | `GET /v1/messages/received/{id}/attachments`, `GET /v1/messages/received/{id}/attachments/{attachment_id}` |
| `client.search(q, ...)` | `GET /v1/search` |
| `client.list_threads(...)`, `client.get_thread(id)`, `client.update_thread(id, status=...)`, `client.delete_thread(id)` | `GET /v1/threads`, `GET /v1/threads/{id}`, `PATCH /v1/threads/{id}`, `DELETE /v1/threads/{id}` |
| `client.list_labels()`, `client.create_label(name, color=...)` | `GET /v1/labels`, `POST /v1/labels` |
| `client.list_events(event_type=..., since=..., limit=..., cursor=...)`, `client.get_event(id)` | `GET /v1/events`, `GET /v1/events/{id}` |
| `client.create_draft(...)`, `client.send_draft(id, idempotency_key=...)` | `POST /v1/drafts`, `POST /v1/drafts/{id}/send` |
| `client.list_agents()`, `client.create_agent(name, domain=...)`, `client.get_agent(id)`, `client.update_agent(id, ...)` | `GET /v1/agents`, `POST /v1/agents`, `GET /v1/agents/{id}`, `PATCH /v1/agents/{id}` |
| `client.verify_agent_forwarding(id)` | `POST /v1/agents/{id}/forwarding/verify` |
| `client.list_webhooks()`, `client.create_webhook(url, event_types=...)` | `GET /v1/webhooks`, `POST /v1/webhooks` |
| `client.list_domains()`, `client.create_domain(domain)`, `client.get_domain(id)`, `client.verify_domain(id)` | `/v1/domains` and the routes under it |
| `client.get_reputation(agent_id=None)` | `GET /v1/reputation` |
| `client.check_suppression(address)` | `GET /v1/suppression?address=` |
| `client.allow_address(address, attestation)` | `POST /v1/suppression/allow` |
| `client.test_inbound(agent, ...)` | `POST /v1/test/inbound`, with a test key |
| `client.usage()` | `GET /v1/billing/usage` |
| `verify_webhook(body, signature, secret)` | checks a webhook signature and its time, which must be within 300 seconds of your clock (`tolerance_sec=` changes that); returns the event dict or `None` |

[../examples/rest.py](../examples/rest.py) calls any endpoint that answers JSON with only
the standard library, for code where the SDK is not installed.

## Things to know

- **Use `body_text`**, the API's own field name. `body=` also works on `send`, `batch_send`,
  `reply` and `forward`.
- **Idempotency keys.** `send`, `batch_send`, `reply`, `forward` and `send_draft` take
  `idempotency_key`. A repeat with the same key within 24 hours returns the first response
  instead of sending again; a repeat that changes the body answers
  `400 invalid_idempotency_key` and sends nothing. Build the key from what makes the message
  unique, such as the event a reply answers: `idempotency_key=f"reply-{event['id']}"`. Given
  none, the SDK makes up a random key for that call, which protects its own retries of it but
  not a repeat you make later. No other call sends a key: no other route reads one.
- **Retries.** The SDK retries a 429 on any call, and a 5xx or a network error on a `GET` and
  on those five sends. Any other write is sent once, because sending it again could act twice
  (a second webhook, a second API key). It tries up to 3 more times, waiting `Retry-After`
  when the API sends one and otherwise 0.5 s, 1 s, 2 s. It waits at most 60 seconds before a
  retry, and `Client(max_retry_wait=...)` can lower that. Then it raises `MailsError`. After a
  network error its `code` is `transport_error`, and the request may or may not have been
  processed.
- **Long limits.** The API sends `Retry-After` only for a wait of a minute or less. So when a
  limit resets later, such as a daily or monthly cap, the call raises `RateLimitError` at
  once, with a message that says when to try again; see
  [errors-and-retries.md](errors-and-retries.md). Its `resets_at` is when the limit resets, or
  `None` when waiting cannot help, and `retry_after_seconds` is how many seconds away that is.
  `RateLimitError` is a `MailsError`.
- **`verify_webhook` needs the body as text.** Decode the raw bytes as UTF-8 first, and do
  not re-serialize the JSON.
- **Long-running listeners.** `stream_events()` and `Agent.start_listening()` reconnect
  after the server closes the stream (about every 50 seconds) or the network drops, and
  carry on from where the stream was. An event the server sends again is not handed to
  `on_event` a second time, and one that was written late arrives after newer ones instead
  of being skipped. Before the first event, they carry on after the newest event there was
  when they started, so nothing is missed in between. To carry on after a restart, save what
  `on_position` gives `stream_events()` and pass it as `since`. An event handled before the
  restart can come again then, so keep the ids you handled if that matters. You can also
  pass `stream_events(since=...)` the id of the last event you handled (`evt_…`), not a
  time as on `list_events`: a time sorts before every id, so the whole history is sent
  again. An event id starts after that event, so an event written late while you were away
  is missed. `stream_events(on_error=...)` hears each failure; a `401` or `403` ends the
  stream, and without `on_error` it raises `MailsError`. `Agent.start_listening()` prints
  each failure to stderr instead, and returns when a `401` or `403` ends the stream. It
  looks its agent up by name or `agt_` id first, and returns at once when that fails, for
  example because no agent has the name or two do (`409 agent_name_conflict`, so use the
  id). Webhooks are still simpler for an agent that runs for hours.
