# Inbound event fields

Webhooks, `GET /v1/events` and the live stream all deliver the same envelope. This is a
`message.received` event:

```json inbound-event
{
  "id": "evt_01JZXA2B4C6D8E0F2G4H6J8K0N",
  "type": "message.received",
  "workspace_id": "wsk_01JZ8A1B2C3D4E5F6G7H8J9K0M",
  "created_at": "2026-06-24T17:32:08.421Z",
  "test_mode": false,
  "classifier_model": "injection-scan-only",
  "agent_id": "agt_01JZ9F8H7KQ2M3N4P5R6S7T8U9",
  "thread_id": "thrd_01JZXA2B4C6D8E0F2G4H6J8K0P",
  "source_message_id": "rcv_01JZXA2B4C6D8E0F2G4H6J8K0M",
  "intent": "unclassified",
  "urgency": 0.5,
  "injection_score": 0.03,
  "sender_reputation": 0.7,
  "entities": {},
  "quarantined": false,
  "data": {
    "agent_id": "agt_01JZ9F8H7KQ2M3N4P5R6S7T8U9",
    "agent_email": "support@acme.mails.ai",
    "thread_id": "thrd_01JZXA2B4C6D8E0F2G4H6J8K0P",
    "source_message_id": "rcv_01JZXA2B4C6D8E0F2G4H6J8K0M",
    "in_reply_to_message_id": null,
    "thread_root_message_id": null,
    "is_thread_reply": false,
    "from": { "address": "dana@example.com", "name": null },
    "envelope_from": "dana@example.com",
    "subject": "Where is my order?",
    "received_at": "2026-06-24T17:32:08.421Z",
    "intent": "unclassified",
    "entities": {},
    "urgency": 0.5,
    "injection_score": 0.03,
    "injection_categories": [],
    "quarantined": false,
    "sender_reputation": 0.7,
    "spf_pass": null,
    "dkim_pass": true,
    "spf": "unknown",
    "dkim": "pass",
    "dkim_domain": "example.com",
    "dmarc": "pass",
    "arc": "none",
    "trusted_forwarder": null,
    "auth_failed": false,
    "body_text_excerpt": "Hi, order 1042 has not arrived yet. Can you check?",
    "extracted_text": "Hi, order 1042 has not arrived yet. Can you check?",
    "extracted_html": null,
    "raw_url": "/api/v1/messages/rcv_01JZXA2B4C6D8E0F2G4H6J8K0M/raw",
    "has_attachment": false,
    "attachments": []
  }
}
```

## Top level

| Field | Meaning |
|---|---|
| `id` | the event id. Use it to skip repeats and to build idempotency keys |
| `type` | `message.received`, `reply.received` or `message.received.unauthenticated` for mail. Mail that arrives over a limit is `message.received.over_limit` instead, and its `data` has only `agent_id`, `agent_email`, `thread_id`, `source_message_id`, `from.address`, `envelope_from`, `received_at`, `over_limit` (`quota_exceeded`, `subscription_inactive`, `rate_limited`, `plus_address_limit` or `held_code`) and `content_kept` (`false` when only the record was kept) |
| `created_at` | when the event was made, UTC. Use it as `since` when polling |
| `test_mode` | `true` for events from a test key, and for the automatic reply from `reply@test.mails.ai` to a test-key send |
| `injection_score` | 0 to 1: how likely the text is a prompt injection |
| `quarantined` | `true` when `injection_score` is 0.95 or more. The mail is still delivered |
| `intent`, `entities`, `urgency` | filled in when the agent has `classify_inbound` on. Three kinds of mail are never classified, whatever the setting: mail from a likely forged sender, a reply included (`intent` is `unknown`), any other reply to one of the agent's messages (`intent` is `general_reply`), and other mail under 80 characters from a `gmail.com`, `outlook.com`, `hotmail.com` or `yahoo.com` address (`unknown` too). Without `classify_inbound`, the rest has `unclassified` |
| `sender_reputation` | 0 to 1, a rough trust signal from the kind of mail, not from the sender's history. Mail from a likely forged sender gets 0.3, a reply included. Any other reply to one of the agent's messages gets 0.85. Other mail gets 0.5 when it is under 80 characters and from one of the four mailbox providers above, and otherwise 0.7, or the model's own estimate when the agent has `classify_inbound` on. The 0.85 and the 0.7 become 0.3 when `injection_score` is over 0.5. Mail whose scan failed gets 0.5, except mail from a likely forged sender, which keeps 0.3 |
| `classifier_model` | how the score was made. `scan-unavailable`: the scan failed. `not-scanned`: no scan was made. `rules-layer`: older mail that a fixed rule scored without a scan. Any other value, `rules-layer+injection-scan` included: the scan ran |

## `data`

| Field | Meaning |
|---|---|
| `agent_id`, `agent_email` | the agent the mail reached |
| `source_message_id` | the received message (`rcv_` id). Reply to this id |
| `thread_id` | the conversation |
| `thread_root_message_id`, `is_thread_reply` | for a reply to one of the agent's messages, that message's `msg_` id, and `true`. Otherwise `null` and `false` |
| `in_reply_to_message_id` | the email's In-Reply-To header, or `null` without one. It is that same `msg_` id when the header is a Message-ID mails.ai wrote, and otherwise the header as it arrived, so match a reply to your send by `thread_root_message_id` |
| `from` | `address` and `name` of the first mailbox in the email's From header. Only a claim until `dmarc` is `pass`: see Authentication below |
| `envelope_from` | the envelope sender (SMTP MAIL FROM), where bounces go. A sending service often sets it to its own bounce address. Replies go to the Reply-To or `from`, never here |
| `subject`, `received_at` | as received. The injection scan reads the subject too |
| `injection_categories` | what the scan found, from `instruction_override`, `role_hijack`, `token_injection`, `data_exfil`, `jailbreak` and `tool_invocation`; `scan_unavailable` when the scan failed, and `auth_fail` as below |
| `body_text_excerpt` | the first 500 characters of the text |
| `extracted_text`, `extracted_html` | the new text, without the quoted history. `extracted_html` is the HTML part treated the same way, and `null` when the email had no HTML part, when nothing was left once the quoted history was stripped, or when the injection scan did not read it |
| `raw_url` | the email as an `.eml` file, read with your API key: the original bytes, attachments included, when mails.ai kept them (up to 25 MiB), otherwise one rebuilt from what it stored. Nothing in its attachments was scanned, so do not hand it to a model |
| `has_attachment`, `attachments` | `has_attachment` is `true` when the sender attached files, whether or not mails.ai kept them; images embedded in the HTML do not count. `attachments` lists the files mails.ai kept, embedded images included (`inline: true`), each with its `id`, `filename`, `content_type`, `size`, `content_id` and `inline`. Files it did not keep are named in `attachments_omitted` on `GET /v1/messages/received/{id}`. The `mails` skill shows how to download one |

### Authentication

mails.ai checks the DKIM signatures and the From domain's DMARC policy itself, from the email
as it arrived. It never believes a result written into the email's headers, with one
exception: the DMARC result that a known forwarding service records in an ARC set that
verifies (see `trusted_forwarder`).

| Field | Meaning |
|---|---|
| `dkim` | `pass` when a DKIM signature verified, whichever domain signed it. Otherwise `unknown` when a signature could not be checked, `fail` when none verified, and `none` for an unsigned email |
| `dkim_domain` | the domain of a signature that verified and is aligned with the From header's domain, or `null`. Aligned means the same domain or, unless that domain's DMARC record asks for strict alignment (`adkim=s`), one under the same registered domain, such as `mail.example.com` for `example.com` |
| `dmarc` | `none` when no DMARC record covers the From header's domain (a domain's record also covers its subdomains). Otherwise `pass` when `dkim_domain` is set, and `unknown` when it is not |
| `spf` | `unknown` on real mail: it reaches mails.ai through Cloudflare, so mails.ai never sees the server that sent it. A test event carries the `spf` its request gave, which is `pass` unless it said otherwise |
| `spf_pass`, `dkim_pass` | `true` for `pass`, `false` for `fail`, otherwise `null` |
| `arc` | the email's ARC chain (the record each forwarding service adds) as mails.ai verified it: `pass`, `fail`, `none` when it has none, or `unknown` |
| `trusted_forwarder` | for forwarded mail, the service whose ARC record mails.ai took the word of: `google_workspace`, `microsoft_365`, `fastmail` or `zoho`, and only when that record verified and says the From header's domain passed DMARC when the mail reached that service. Otherwise `null` |
| `auth_failed` | `true` when the From header's domain has a DMARC policy of `quarantine` or `reject` and no signature from that domain verified. Such a domain signs its mail, so the sender is likely forged: the event is then `message.received.unauthenticated`, and `injection_categories` has `auth_fail`, a reply to one of the agent's own messages included. It stays `false` when a signature could not be checked, and when `trusted_forwarder` is set (a forward that changed the email breaks its signature) |

`from.address` is the From header's first mailbox, read the way DKIM and DMARC read it, so
`dkim_domain`, `dmarc` and `auth_failed` are about its domain (the text after its last `@`).
Anyone can write any address there: trust it only when `dmarc` is `pass`, which means a DMARC
record covers its domain and a signature aligned with that domain verified (`dkim_domain`).
`dkim_pass` alone is not enough, because anyone can sign mail with a domain of their own, and
`envelope_from` is never proof. When no raw email reached mails.ai, `from` is read from the
From header its mail server passed on (the envelope sender only when there was none), and
`dmarc` is `unknown`.

## Only on `GET /v1/events/{id}`

| Field | Meaning |
|---|---|
| `injection_categories` | the same list, at the top level |

The text of the message is on `GET /v1/messages/received/{id}` (`body_text`, cut at 100,000
characters, and `body_html` when the injection scan read the message).
