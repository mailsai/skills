# Choosing the levels

## By what the agent can do

| The agent | Levels | Settings for the examples |
|---|---|---|
| answers its owner and a few known people | 1, 3, 4 | `ALLOWED_SENDERS=you@example.com REQUIRE_APPROVAL=0` |
| answers the people at a few organizations | 2, 3, 4 | `ALLOWED_DOMAINS=customer.example,partner.example REQUIRE_APPROVAL=0` |
| answers anyone who writes, for example a public support address | 3, 4, 5 | `OPEN_TO_ANY_SENDER=1` (approval stays on) |
| can spend money, change records or write to people who did not write first | all five | approval on, and every tool that changes something waits for a person |

## Settings

The examples read these environment variables. Unset means the strict default, except for
`USE_AGENT_LISTS`.

| Variable | Default | Level | Effect |
|---|---|---|---|
| `ALLOWED_SENDERS` | empty | 1 | comma-separated addresses that may instruct the agent |
| `ALLOWED_DOMAINS` | empty | 2 | comma-separated domains, subdomains included |
| `BLOCKED_DOMAINS` | empty | 1, 2 | domains whose mail is ignored, even when also allowed |
| `USE_AGENT_LISTS` | on | 2 | adds the agent's own `allowlist_domains` to the allowed domains and its `blocklist_domains` to the blocked ones, so mail from the agent's allowlist may instruct it; `0` turns it off |
| `OPEN_TO_ANY_SENDER` | off | 1, 2 | `1` accepts any sender except at a blocked domain; the DMARC and score checks still apply. Use only with approval on |
| `REQUIRE_DMARC` | on | 1, 2 | holds mail unless `dmarc` is `pass`, the one result that proves the From address; `0` turns it off |
| `MAX_INJECTION_SCORE` | 0.5 | 3 | holds mail scored at or above this. A value that is not a number keeps 0.5 |
| `REQUIRE_SCAN` | on | 3 | holds mail scored without a scan; `0` turns it off |
| `REQUIRE_APPROVAL` | on | 5 | drafts every reply for a person; `0` replies directly |

With no allowlist, in these settings or on the agent, and `OPEN_TO_ANY_SENDER` unset, the
agent ignores all mail. That is the intended starting point.

With approval on, run the handler with a key that has only the `read` and `draft` scopes. It
can save drafts and cannot send anything, so level 5 holds even if the handler is hijacked.

## What each level cannot stop

- **Levels 1 and 2** trust the From address. A forged address is caught only when the mail
  fails authentication, and a real account that was broken into passes. Keep level 3 on.
- **Level 3** is a score. A new kind of attack can score low, mail whose scan failed has no
  scan behind its score (`REQUIRE_SCAN` holds that), and attachments are never scanned.
  Keep level 4 or 5 on.
- **Level 4** limits where a reply goes, not what it says. A hijacked model can still put
  anything it knows into the reply. Never give the model secrets, other customers' data or
  internal notes it does not need for this one sender.
- **Level 5** depends on the reviewer. Show the original email next to the draft, and make
  "delete" as easy as "send".

## Who enforces what

| Protection | mails.ai | Your handler |
|---|---|---|
| Injection scan | scores each message's body, except mail kept over a limit, and marks the worst as quarantined | decides what to hold |
| Agent allowlist and blocklist | refuses sends from the agent outside them | applies them to incoming mail |
| The model cannot pick who gets a reply | `POST /v1/messages/{id}/reply` sends it to the email's Reply-To, or to its sender when it set none | offers the model no other way to send |
| Human approval | keeps drafts until a person sends them | creates drafts instead of sending |
| Webhook signature | signs every delivery | verifies it before reading anything |
| Repeats and floods | sends each delivery a limited number of times | dedupes by event id and caps per sender and thread |

mails.ai also refuses live sends past the agent's `hourly_send_limit` or `daily_send_limit`,
its caps on recipients an hour and a day.
Your handler's own lists stay useful: they decide which incoming mail the agent acts on at
all.
