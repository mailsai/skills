# Bounces, complaints and suppression

## What mails.ai reports

| Event | When | `data` |
|---|---|---|
| `message.bounced` | a receiving server refused the message | `message_id`, `agent_id`, `recipient`, `bounce_type` (`Permanent` or `Undetermined`), `bounce_subtype`, `diagnostic_code`, `bounced_at` |
| `message.delayed` | a receiving server turned the message away for now (a temporary bounce, such as a full mailbox). It may still be delivered, or bounce later. A webhook endpoint gets it only when it lists it | `message_id`, `agent_id`, `recipient`, `bounce_type` (`Transient`), `bounce_subtype`, `diagnostic_code`, `delayed_at` |
| `message.complained` | the recipient marked it as spam | `message_id`, `agent_id`, `recipient`, `complaint_type`, `complained_at` |
| `suppression.added` | an address was added to the suppression list | `address_hash`, `type`, `scope`, `source`, and `message_id` for an unsubscribe |

A `message.bounced` event's `data` looks like this:

```json
{
  "message_id": "msg_01JZX8K3M9Q4P7VN2YB6RTDC11",
  "agent_id": "agt_01JZX8K3M9Q4P7VN2YB6RTDC12",
  "recipient": "old-address@example.com",
  "bounce_type": "Permanent",
  "bounce_subtype": "General",
  "diagnostic_code": "smtp; 550 5.1.1 user unknown",
  "bounced_at": "2026-10-05T09:12:44.000Z"
}
```

Receive these through a webhook or `GET /v1/events?event_type=message.bounced`, and update your
own records: stop mailing an address that bounced permanently or complained.

## What gets suppressed

| Cause | `type` | Who can no longer send to the address |
|---|---|---|
| A permanent bounce: the mailbox does not exist | `hard_bounce` | every mails.ai workspace (`scope: "global"`) |
| A spam complaint | `complaint` | every mails.ai workspace (`scope: "global"`) |
| A one-click unsubscribe | `unsubscribe` | your workspace only (`scope: "workspace:<id>"`) |

A temporary bounce (`Transient`, such as a full mailbox) is reported as `message.delayed`,
not `message.bounced`. It does not suppress the address or count toward the bounce rate,
and a message not yet delivered shows the status `delayed`. One that arrives after the
message was delivered or bounced changes nothing and raises no event.

`message.delivered`, `message.delayed`, `message.bounced` and `message.complained` are raised
once for each recipient of a message: a report the mail provider sends again raises no second
event, and neither does a second temporary bounce for the same recipient.

`address_hash` is the SHA-256 (hex) of the address after mails.ai normalizes it: lower case,
any `+tag` removed from the part before `@`, and for `gmail.com` and `googlemail.com`
addresses the dots in that part removed. For an unsubscribe, `data.message_id` names the
message the person unsubscribed from: `GET /v1/messages/{id}` shows its recipient, unless
its thread was deleted for good, which answers `404`.

A message carries the Unsubscribe button only when you send it with
`list_unsubscribe: true`. See "One-click unsubscribe" in this skill's SKILL.md. Until 4
October 2026 every send to a single address carried it, so a click on an older message can
still suppress an address.

## Check before you send

```bash
curl "https://api.mails.ai/v1/suppression?address=someone@example.com" \
  -H "Authorization: Bearer $MAILS_API_KEY"
```

The answer has `suppressed`. When it is `true`, `type`, `scope` and `since` say why and since
when. Check every address you put on a send, in `to`, `cc` and `bcc`.

`GET /v1/suppression?view=suppressed` lists which of your recent recipients are suppressed,
and why. It looks at the `to`, `cc` and `bcc` addresses of your 2,000 most recent sends, and
returns at most 500 of them, with `has_more: true` when there are more.

A live send to a suppressed address, in `to`, `cc` or `bcc`, is refused as a whole with
`422 recipient_suppressed`. The message names the address, and `error.param` the field it
was in. Take it off your list and send again without it. Do not retry the same request.
Test keys skip this check, so a test send never tells you whether an address is suppressed.

## Sending again to a suppressed address

If a person asks to get your mail again, for example by signing up again after an
unsubscribe, your workspace can allow the address:

```bash
curl https://api.mails.ai/v1/suppression/allow \
  -H "Authorization: Bearer $MAILS_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"address": "someone@example.com", "attestation": "Signed up again on 2026-10-04 and confirmed the address by email."}'
```

- `attestation` (20 to 2,000 characters) records what the person did and when. Write the
  real reason; it is kept.
- The key needs the `manage` scope and must not be tied to one agent.
- An allowed address overrides an unsubscribe or a complaint for your workspace. Nothing
  overrides a permanent bounce: that mailbox does not exist.
- `GET /v1/suppression` (without `address` or `view`) lists the addresses your workspace
  allowed. `DELETE /v1/suppression/allow/{id}` ends an allowance, so a suppression of that
  address applies again, and the entry stays in that list with `revoked_at` set.

Never allow an address only because a send was refused. An address that complained and is
mailed again usually complains again.

## When mails.ai pauses sending

Every 15 minutes, mails.ai computes each agent's rates over its live sends in the last 30
days:

| | Paused when | Resumes when |
|---|---|---|
| Bounces | above 5% of sends | below 3% |
| Complaints | above 0.3% of sends | below 0.2% |

An agent needs at least 20 sends in those 30 days before it can be paused. The bounce rate
counts messages whose status is `bounced`, so a temporary bounce, which never makes a
message `bounced`, does not count. Test sends never count.

An agent paused for its own rate cannot be resumed with `PATCH /v1/agents/{id}`: that answers
`403 agent_suspended`. It resumes by itself at one of those checks, once both rates are below
the resume line.

Once an hour, mails.ai applies the same rates to the whole workspace, over 30 days (from 50
sends) and over the last 24 hours (from 20 sends), so a problem spread across several agents
still pauses them. `PATCH /v1/agents/{id}` cannot lift that pause either. The hourly check
lifts it once each window that still has enough sends is below the resume line. It lifts it
from agents archived during the pause too: they stay archived, and the workspace can create
agents again. When neither
window has enough sends left, the pause stays: write to mails.ai support (support@mails.ai).

A send from a paused agent is refused with `422 agent_paused`; on `POST /v1/messages` the
message gives the reason.
A paused agent sends nothing, so its 30-day rates fall only as older sends leave the window.
Clean the list before the next send rather than after a pause.

`GET /v1/reputation?agent_id=<name or id>` returns the agent's 30-day counts:
`send_count_30d`, `bounce_count_30d`, `complaint_count_30d`, `reply_count_30d`, and a
`reputation` score from 0 to 1 (0.85 to start; bounces and complaints lower it, replies
raise it). Without `agent_id`, it returns the workspace's average score, or, to a key tied
to one agent, that agent's counts.

## Keep the list clean

- Collect addresses from the person themselves, and confirm new sign-ups with a message
  they must act on.
- Remove addresses that bounce permanently or complain the moment the event arrives.
- Send each kind of mail to the people who asked for it, and only as often as they expect.
- Never buy or rent a list. mails.ai refuses mail to people who did not ask for it (see
  [what-mails-ai-refuses.md](what-mails-ai-refuses.md)).
