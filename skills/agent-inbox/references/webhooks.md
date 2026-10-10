# Webhooks

## Create an endpoint

Use a key with the `manage` scope that is not tied to an agent:

```bash
curl https://api.mails.ai/v1/webhooks \
  -H "Authorization: Bearer $MAILS_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com/webhooks/mails", "event_types": ["message.received", "reply.received", "message.received.unauthenticated"]}'
```

- The URL must be `https`, and its host must resolve to public addresses only: a host that
  does not resolve, or resolves to a private or loopback address, is refused
  (`400 invalid_param_value`). Creating the endpoint sends it nothing, so check that it
  answers with `POST /v1/webhooks/{id}/test`.
- `event_types` defaults to `["*"]`, every type except `thread.created`, `thread.updated`,
  `thread.deleted` and `message.delayed`: an endpoint gets those only when it lists them.
  List only what the handler needs. An empty list is refused (`422 invalid_param_value`).
- The answer contains `signing_secret` (`whsec_...`). It is shown only once. Store it as a
  secret, for example in `MAILS_WEBHOOK_SECRET`.
- `GET /v1/webhooks` lists endpoints and `GET /v1/webhooks/{id}` reads one.
  `PATCH /v1/webhooks/{id}` changes `url`, `event_types`, `description` or `active`.
  `DELETE /v1/webhooks/{id}` removes one.
- `"active": false` pauses an endpoint. Events raised while it is paused are not sent to it,
  then or when it resumes, and a retry that falls due meanwhile is not made. Once it is back
  on, `POST /v1/events/{id}/redeliver` sends an event again.
- A key tied to one agent can read endpoints but not create, change, test or delete them,
  or send an event to them again (redeliver or replay), because an endpoint can receive
  every agent's mail.

## A delivery

mails.ai sends a `POST` with the event as JSON (fields: [event-fields.md](event-fields.md))
and these headers:

| Header | Value |
|---|---|
| `X-Mails-Signature` | `t=<unix seconds>,v1=<hex HMAC-SHA256>` |
| `X-Mails-Event-Id` | the event id |
| `X-Mails-Event-Type` | the event type |
| `Content-Type` | `application/json` |

The signature covers the body, not the other headers. Read the event id and type from the
verified body.

## Checking the signature

1. Read the raw request body as bytes, before any JSON parsing. A parsed and re-serialized
   body has different bytes, and the check fails.
2. Split the header on `,` and each part on the first `=`, ignoring spaces around them. Take
   `t` and every `v1`.
3. Refuse when `t` is more than 300 seconds before or after your clock.
4. Compute HMAC-SHA256 with the whole secret, `whsec_` included, as the key, over the text
   `<t>.<raw body>`. Compare it with each `v1` in constant time. The delivery is genuine
   when any of them matches.
5. Refuse with 401 when anything fails. Parse the body only after the check passes.

[../examples/verify-signature.ts](../examples/verify-signature.ts) and
[../examples/verify_signature.py](../examples/verify_signature.py) do exactly this with the
standard library. In Python:

```python no-run
from verify_signature import verify_signature

raw_body = b'{"id":"evt_01JZXA2B4C6D8E0F2G4H6J8K0N","type":"webhook.test"}'
header = "t=1782322328,v1=0000000000000000000000000000000000000000000000000000000000000000"
# now_seconds stands in for the clock, so the 300-second window passes; a handler leaves it out.
print(verify_signature(raw_body, header, "whsec_example", now_seconds=1782322328))  # False: the digest is wrong
```

## Answer within 5 seconds

- Any 2xx counts as delivered. mails.ai waits 5 seconds for an answer.
- After a failure it tries again about 30 seconds later, then about 2 minutes after that.
  Each attempt is signed again with a new timestamp. After the third failure it stops.
- So answer 200 first, then do the work, ideally from a queue or table. A crash after the
  answer must not lose the event.
- `GET /v1/webhooks/{id}/deliveries` lists the attempts and their status codes.
  `POST /v1/events/{id}/redeliver` sends an event again to every matching endpoint, and
  `POST /v1/webhook-deliveries/{id}/replay` repeats one delivery, to that delivery's
  endpoint only.

## Testing

- `POST /v1/webhooks/{id}/test` sends a `webhook.test` event once, without retries, and its
  answer says how your endpoint answered (`ok`, `http_status`). Handlers should verify it
  and then ignore it, as the examples do.
- With a test key, `POST /v1/test/inbound` makes real inbound events, including hostile
  ones. See [injection-score.md](injection-score.md).

With the `mails` command line, `mails webhooks listen --forward-to http://localhost:8787/webhooks/mails`
receives your events and forwards each one, signed, to a server on your machine, so you can
test without a public URL. Run it with the same `MAILS_WEBHOOK_SECRET` as the handler.
Without one it signs with a secret it makes for the session and prints. Without `--events`
it forwards what a `*` endpoint is sent, so not `thread.created`, `thread.updated`,
`thread.deleted` or `message.delayed`. Pass `--events` with the types your endpoint lists to
forward exactly those.

## Changing the secret

`POST /v1/webhooks/{id}/rotate-secret` makes a new signing secret and returns it once, as
`signing_secret`. The old secret keeps signing for 24 hours, until
`previous_secret_expires_at`.

1. Rotate, and store the new secret.
2. Give the handler the new secret within those 24 hours. Until then each delivery carries
   two `v1` values, one per secret, so a handler that checks every `v1`, as the examples
   do, passes with either secret.

Rotating again within the 24 hours retires the older of the two secrets at once. Rotating
needs the `manage` scope and a key that is not tied to an agent, and an app someone
connected by signing in cannot do it. `GET /v1/webhooks/{id}` shows `secret_rotated_at`
and, while the old secret still signs, `previous_secret_expires_at`.
