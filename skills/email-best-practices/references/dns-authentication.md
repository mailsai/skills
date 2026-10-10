# Sending from your own domain

Without any setup, an agent's address is on your workspace's mails.ai subdomain
(`support@acme.mails.ai`). Its mail goes out from an address under `send.mails.ai`, such as
`support.acme@send.mails.ai`, with the agent's name (`support`) as the display name. Its
Reply-To is the agent's `receiving_address` unless the send sets `reply_to`, so replies come
back to the agent. On `POST /v1/messages`, a display name you write in `from`
(`"Acme Support <support@acme.mails.ai>"`) takes the place of the agent's name. The send
response's `from` still shows `support@acme.mails.ai`.

To send as `billing@example.com` instead, register the domain, publish the DNS records
mails.ai gives you, and create agents on it.

## Before you start

- Custom domains need a paid plan and a key with the `manage` scope that is not tied to one
  agent. On a plan without custom domains the API answers `402 feature_not_enabled`. If
  custom domains are not switched on for the service at all, it answers
  `400 feature_not_enabled`.
- You need access to the DNS records of the domain.
- A subdomain used only for this mail keeps its reputation apart from your company's own
  mailboxes, and you never touch the records those mailboxes depend on.

## 1. Register the domain

```bash
curl https://api.mails.ai/v1/domains \
  -H "Authorization: Bearer $MAILS_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"domain": "example.com"}'
```

The answer (`201`) has the domain's `id` (`dom_...`), `status: "pending"` and the records to
create in `dns_records`. A domain can belong to one workspace only, and domains under
mails.ai cannot be registered.

## 2. Create the records

Each entry in `dns_records` has:

| Field | Meaning |
|---|---|
| `type` | `CNAME` or `TXT` today. The API's schema also allows `MX` |
| `host` | the full name to create, such as `selector._domainkey.example.com`. Many DNS hosts add your domain on their own; then enter only the part before it |
| `value` | what the record must contain |
| `purpose` | what it is for: `dkim`, `spf`, `dmarc`, `return_path`, `tracking` or `ownership` |
| `required` | only required records decide verification |
| `verified` | whether mails.ai found the record at its last check |
| `instruction` | how to add it, when there is something to watch for. Follow it |
| `merge_token` | for SPF: the part to add to a record you already have |

Which records you get depends on how mails.ai sends for your domain, so create exactly the
ones the answer lists.

**SPF.** A domain may publish only one SPF record; with two, SPF fails for all of your mail.
If you already have one, do not add another: put the `merge_token` (for example
`ip4:192.0.2.10`) into your existing record before its `~all` or `-all`. mails.ai accepts
the merged record.

**DKIM.** This is the record that matters most. mails.ai signs your mail with it, and that
signature is what lets your mail pass DMARC. Keep it for as long as you send from the
domain.

**DMARC.** Only one DMARC record may exist at `_dmarc.<your domain>`. If you already have
one, keep it and follow the record's `instruction` instead of adding a second.

## 3. Wait for verification

mails.ai checks an unverified domain every 15 minutes, for as long as it stays unverified,
and marks it verified as soon as every required record is found. Most DNS changes are
visible within minutes.

- `GET /v1/domains/{id}` shows the state: each record's `verified`, and `fail_reason`
  naming the records still missing.
- `POST /v1/domains/{id}/verify` checks at once. Each call counts. After 20 calls in a row
  on a domain that still does not verify, its status becomes `failed`; a day without a call
  starts the count over. mails.ai keeps checking a `failed` domain too, less
  often the longer it fails (from every 10 minutes to once a day), and marks it verified as
  soon as the records are found. Do not call it in a loop.

| `status` | Meaning |
|---|---|
| `pending` | added, and not verified yet. mails.ai's own checks leave a domain `pending` until they can verify it |
| `verifying` | a check you asked for (`POST /v1/domains/{id}/verify`) did not verify the domain: a required record is missing, or the sending service has not confirmed the domain yet. A verified domain also becomes `verifying` when the daily re-check finds a required record gone |
| `verified` | every required record is in place. Agents on the domain can send |
| `failed` | 20 checks requested in a row without success. Fix the records, then call verify once, or wait for mails.ai's next check |

To look a record up yourself:

```bash
dig +short TXT _dmarc.example.com
dig +short CNAME selector._domainkey.example.com
```

## 4. Send from the domain

Create an agent on the verified domain. Its address is `<name>@<domain>`:

```bash
curl https://api.mails.ai/v1/agents \
  -H "Authorization: Bearer $MAILS_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"name": "billing", "domain": "example.com"}'
```

An agent can be created only on a domain that is verified, or the API answers `400
domain_not_verified`. Sends from the agent then carry your domain in From.

To send as that agent, pass its `agt_` id in `agent`, or leave `agent` out and name the
address in `from`:

- On a verified domain, `"from": "billing@example.com"` means the agent at exactly that
  address. If it does not exist yet, mails.ai creates it on your domain when the key may
  create agents (the `manage` scope) and the plan has room, and answers
  `403 insufficient_scope` or `402 plan_limit_exceeded` when it may not or there is no room.
- `"agent": "billing"` means the oldest agent with that name. If an agent called `billing`
  already existed at your mails.ai address, the name still means that one. To a key tied to
  one agent, a name it shares with others means its own agent.
- On a domain that is not verified, `"from": "billing@example.com"` still picks the agent
  whose address is exactly that one, when there is one, and its sends answer
  `422 domain_not_verified` until the domain verifies again. When no agent has that address,
  the name alone (`billing`) picks one, which can be one at your mails.ai address; if none
  has the name either, mails.ai creates `billing` at your mails.ai address when the plan has
  room. The response's `from` says which address sent.

Replies still reach the agent: each send's Reply-To is the agent's `receiving_address` on
mails.ai, such as `billing.example_com@in.mails.ai` for `billing@example.com`.

Mail that people write directly to `billing@example.com` goes wherever your domain's MX
records point, not to mails.ai.

To have the agent receive that mail too, without touching your MX records, use forwarding:
create the agent with `"address": "billing@example.com"` and `"forwarding": true` (or turn
`forwarding` on with `PATCH /v1/agents/{id}`), have the mail service that hosts
`billing@example.com` forward it to the agent's `forwarding_address`, then call
`POST /v1/agents/{id}/forwarding/verify`. It sends one test email to `billing@example.com`,
and the agent's `forwarding_status` becomes `verified` when the test comes back through the
forward, or `failing` if it has not arrived 15 minutes later.

The call needs the `manage` scope and a live key, and answers at once with the agent: read
`GET /v1/agents/{id}` until `forwarding_status` changes. The status is `not_verified` until a
first test arrives, and `null` while forwarding is off. A later test leaves it `verified`
while that test is on its way, so compare `forwarding_verified_at` with
`forwarding_test_sent_at` to see that it arrived. Calling again while a test is on its way
sends nothing more, and an agent gets at most 10 tests an hour. The test never appears as a
message or an event.

## Keep it working

- mails.ai re-checks verified domains once a day. If a required record is gone, the domain
  goes back to `verifying`, and sends from its agents fail with `422 domain_not_verified`
  until the record is back and the domain verifies again. A draft sent from one of them
  answers the same and stays as it was, so you can send it once the domain verifies. The
  error's `message` gives the domain's status and what is missing. The same happens if you
  remove the domain: its agents
  stop sending, rather than sending from a mails.ai address you did not choose.
- Before you change DNS providers or rotate records, copy every record from
  `GET /v1/domains/{id}` to the new provider first.

## DMARC, step by step

DMARC tells mailbox providers what to do with mail that claims your domain but fails
authentication, and where to send reports.

1. Start with a policy that only reports:
   `_dmarc.example.com TXT "v=DMARC1; p=none; rua=mailto:dmarc-reports@example.com"`.
2. Read the reports for a few weeks. Every service that sends as your domain (mails.ai, your
   mailboxes, your billing system) should pass with DKIM or SPF aligned to your domain.
3. Fix the ones that fail, then move to `p=quarantine`, and later `p=reject`.

Gmail requires a DMARC record (`p=none` is enough) from anyone who sends more than 5,000
messages a day to Gmail accounts, and Yahoo requires one from bulk senders. Both also want
the From domain aligned with the SPF or the DKIM domain. See [compliance.md](compliance.md).
