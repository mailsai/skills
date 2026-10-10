---
name: email-best-practices
description: Send transactional email through mails.ai that reaches the inbox and stays within the rules. Use when setting up a custom sending domain (SPF, DKIM, DMARC), handling bounces, spam complaints, unsubscribes and suppressed addresses, deciding whether a message is transactional or would be refused as cold outreach, or checking what CAN-SPAM, GDPR and CASL require of email an agent sends.
license: MIT
compatibility: Needs network access to api.mails.ai and a mails.ai API key in MAILS_API_KEY. The examples need Node.js 18+ with tsx, or Python 3.10+.
metadata:
  author: the mails.ai team
  version: "0.1.0"
---

# Email that lands and follows the rules

mails.ai sends transactional email: mail that a person's own action or account calls for,
and replies in a conversation they started. Keep to that, keep your list clean, and
authenticate your domain, and mail reaches the inbox.

## What mails.ai sends and what it refuses

Every send is checked. Mail that serves the recipient's own action passes: receipts, order
and booking updates, password resets, sign-in links and codes, account and security
notices, invoices, and replies to someone who wrote first, sent with
`POST /v1/messages/{id}/reply` to their message. A draft is judged as that reply when its
`in_reply_to_message_id` is their message, it is from the agent that received it, and every
`to` address was on it. An answer sent with `POST /v1/messages` is judged as a first message
to them.

Unsolicited outreach is refused with `422 cold_email_prohibited`: sales pitches,
prospecting, recruiting, fundraising, and newsletters to people who did not ask. A pitch
for something else added to a receipt is refused too. Some checks are fixed rules about
wording, so they can refuse a message that does serve the recipient, and their refusals
cannot be appealed. With a test key the send goes through and carries `classifier_warning`,
so send every template with a test key before going live.

If you believe a refusal is wrong, `POST /v1/messages/appeal` asks for a second review of
that exact content. Details, with examples on both sides:
[references/what-mails-ai-refuses.md](references/what-mails-ai-refuses.md).

## Your own domain

Without setup, an agent's mail goes out from an address under `send.mails.ai`: the agent
`support@acme.mails.ai` sends as `support.acme@send.mails.ai`, and replies come back to it.
mails.ai authenticates that mail. To send from your own domain (paid plans):

1. `POST /v1/domains` with the domain. A subdomain used only for this mail keeps its
   reputation apart from your company's own mailboxes.
2. Create every record in the answer's `dns_records` at your DNS host, exactly as given.
   Follow each record's `instruction`: add to an existing SPF record, never publish a
   second one.
3. mails.ai checks the records every 15 minutes. `POST /v1/domains/{id}/verify` checks at
   once, but each call counts: 20 calls in a row that do not verify mark the domain
   `failed`, and a day without a call starts the count over. When `status` is `verified`,
   create agents on the domain.
4. Publish a DMARC record at `_dmarc.<your domain>` if you have none. Start with `p=none`
   and a report address, and tighten it once reports look clean.

Keep the DKIM record for as long as you send from the domain. mails.ai checks verified
domains every day and stops sending from one whose records are gone (`422
domain_not_verified`).

The full walk-through: [references/dns-authentication.md](references/dns-authentication.md).
The script that registers a domain and reports each record:
[examples/custom-domain.ts](examples/custom-domain.ts),
[examples/custom_domain.py](examples/custom_domain.py).

## Bounces, complaints and suppression

- A hard bounce (the mailbox does not exist) or a spam complaint puts the address on the
  suppression list for every mails.ai sender. An unsubscribe suppresses it for your
  workspace only.
- A live send with a suppressed address in `to`, `cc` or `bcc` is refused as a whole with
  `422 recipient_suppressed`. Remove the address and send again without it.
- If the person asks for your mail again, `POST /v1/suppression/allow` lifts an unsubscribe
  or a complaint for your workspace, never a hard bounce.
- Check an address first with `GET /v1/suppression?address=...`. Webhooks report
  `message.bounced`, `message.complained` and `suppression.added`, and a temporary bounce
  as `message.delayed` to an endpoint that lists it.
- mails.ai checks each agent's rates every 15 minutes. It pauses an agent whose bounces pass
  5% or complaints pass 0.3% of its sends in 30 days (from 20 sends), and resumes it when
  they fall below 3% and 0.2%. Every hour it checks the whole workspace against the same
  rates, over 30 days (from 50 sends) and over the last 24 hours (from 20 sends).
  `GET /v1/reputation?agent_id=<name or id>` shows an agent's counts.

[examples/check-before-send.ts](examples/check-before-send.ts)
([examples/check_before_send.py](examples/check_before_send.py)) checks the address and
the agent's health, sends, and handles each refusal. More:
[references/bounces-and-complaints.md](references/bounces-and-complaints.md).

## One-click unsubscribe

Mail a person subscribed to (a digest, a recurring report, a newsletter they asked for)
needs an Unsubscribe button. Ask for it on the send with `list_unsubscribe: true`:

```bash
curl https://api.mails.ai/v1/messages \
  -H "Authorization: Bearer $MAILS_API_KEY" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: weekly-report-2026-10-05-dana" \
  -d '{"agent": "reports", "to": "dana@example.com", "subject": "Your weekly report", "body_text": "Three bookings this week, one more than last week.", "list_unsubscribe": true}'
```

- The message then carries the `List-Unsubscribe` and `List-Unsubscribe-Post` headers, and
  mail apps show an Unsubscribe button.
- One click suppresses the address for your whole workspace. Later live sends to it, from
  any of your agents, are refused with `422 recipient_suppressed`.
- Leave it off, which is the default, on password resets, sign-in links, receipts and
  anything else the person must keep receiving.
- It needs exactly one `to` address and no `cc` or `bcc`. Otherwise the send is refused with
  `400 invalid_field`.

Replies, forwards, batch items and drafts take the same field. With the SDKs, pass
`list_unsubscribe` to `mails.messages.send(...)` or `client.send(...)`.

## The rules, in short

- **CAN-SPAM (United States):** applies to commercial messages, including business to
  business. Truthful headers and subject, an identified ad, your postal address, and a
  working opt-out honored within 10 business days. Transactional messages are mostly exempt
  but must not mislead.
- **GDPR and the ePrivacy rules (European Union):** you need a lawful basis to process the
  address, and marketing email generally needs prior consent. Existing customers can get
  marketing for similar products if they could object when you collected the address and
  can object in every message. An objection to marketing must be honored.
- **CASL (Canada):** commercial messages need consent, express or implied. Every commercial
  message must identify the sender, give contact details and offer an unsubscribe honored
  within 10 business days.

Large mailbox providers add their own rules: Gmail and Yahoo require SPF or DKIM and a
spam-complaint rate below 0.3% from everyone, and from bulk senders also DMARC and one-click
unsubscribe on marketing and subscribed mail.
Details and sources: [references/compliance.md](references/compliance.md). This is a
summary, not legal advice.

## Files

- [examples/rest.py](examples/rest.py): a standard-library API helper, for code where the
  Python SDK is not installed.
