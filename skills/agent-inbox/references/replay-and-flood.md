# Repeats, replays, floods and loops

## Repeats: handle each event once

The same event can reach you more than once: a retry after your server answered late, a
redelivery someone asked for, two endpoints with the same URL, or a poll that overlaps the
last one.

- Keep the ids of handled events in a table with a unique index on the id. Insert the id
  before acting; if the insert fails, it is a repeat. Answer 200 to a repeat so mails.ai
  stops retrying.
- Build every send's `Idempotency-Key` from the event id (`reply-<event id>`). Then even a
  repeat that slips through sends one reply. Within 24 hours mails.ai answers a repeated key
  with the first response when the body is the same, with `400 invalid_idempotency_key`
  when it differs (a model seldom writes the same reply twice), and with
  `409 duplicate_resource` while the first request is still running. The example handler
  counts that `400` as replied, because the first request sent the reply or is sending it.
- The webhook examples keep the ids in memory, which a restart empties. That is fine for
  trying them out, not for production. The polling examples save their position and the
  last 500 handled ids to a file after every event. Each poll starts 10 minutes before that
  position, so those ids also stop a poll that reads an event again from handling it twice.
  Keep more ids if more than 500 events can arrive in 10 minutes.

## Replays: refuse old and copied requests

- Refuse a signature whose timestamp is more than 300 seconds from your clock. A request
  captured and sent again later then fails.
- Inside those 300 seconds, the event-id check above stops a copied request.
- Keep the server's clock in sync (NTP), or valid deliveries fail the window.
- Never act on a request that failed the signature check, even partly. Log it and answer
  401.

## Floods: cap what one sender can cause

Anyone who knows the agent's address can send it mail, quickly and in bulk.

- Cap messages per sender per hour (the examples hold the 21st message in an hour from one
  sender) and per agent per hour. Held mail waits for a person; it is not lost.
- Answer the webhook quickly whatever happens, and do the expensive work (the model call)
  from a queue with a fixed number of workers. A flood then grows the queue instead of
  your bill.
- Spend nothing on mail you will ignore: run the cheap checks (signature, sender lists,
  score) before the model call.
- mails.ai also limits how fast one workspace takes in mail. Past that rate it keeps only
  who sent the mail, to whom and when (at most 20 records a workspace each hour), and past
  the plan's monthly limit for received mail it stores new mail without a scan. Both raise
  `message.received.over_limit`, which carries no subject or body.

## Loops: two machines answering each other

An agent that replies to an auto-responder ("I am out of office"), or to another agent, can
loop forever.

- Cap replies per thread per day (the examples hold the sixth reply in a thread within 24
  hours).
- Do not reply to bounce and no-reply senders, for example addresses that start with
  `mailer-daemon@`, `postmaster@` or `no-reply@`.
- Do not reply to the agent's own address or to another agent in the same workspace unless
  that is the point.
- With approval on (level 5), a loop stops at the first draft, because a person must send
  each reply.
