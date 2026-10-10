# What mails.ai sends and what it refuses

mails.ai is for transactional email: messages that a person's own action or account calls
for. Every send is judged by its content. The judge reads the subject, the text body and the
HTML body, not only the first lines.

## Passes

- Receipts and invoices.
- Order, shipping, booking and appointment updates.
- Password resets, verification codes, sign-in links and two-factor codes.
- Account and security notices: a new sign-in, a changed setting, a plan that renews.
- A welcome or confirm-your-email message for an account the person just created.
- Replies to a message the recipient sent, sent with `POST /v1/messages/{id}/reply` on the
  message the agent received, or as a draft whose `in_reply_to_message_id` is that message.
  The draft must be from the agent that received the message, and every `to` address must
  have been on it: its sender, its Reply-To, To or Cc. The same text sent with
  `POST /v1/messages` is judged as a first message to that person.
- An offer about the recipient's own order, booking or account, such as an add-on to their
  booking or a referral discount on their next order.
- A recurring digest the person signed up for (a daily report, a price alert), when it only
  delivers that content.

A short, plain message with none of the signs below, such as "test" or a note confirming a
meeting both people arranged, is not refused for being short.

## Refused: `422 cold_email_prohibited`

- Sales and partnership pitches, prospecting, recruiting and fundraising to people who did
  not ask.
- Newsletters and marketing to people who did not sign up for them.
- A pitch for something else attached to a transactional message, anywhere in it: after a
  receipt, in a P.S., in a footer, in a quoted block or in the HTML.
- A first-contact pitch dressed as a reply (`Re:`) or a forward (`Fwd:`), or one that says
  "as requested" when nothing was requested.
- A message that invents an account or pending activity the recipient never had ("verify
  now or your account will be closed").
- List mechanics ("unsubscribe", "manage your preferences", "you are receiving this
  because", "reply STOP") on mail that is not a digest the person subscribed to.

Some content is refused outright, whoever the recipient is: prohibited content, text that
tells the reviewer how to classify the message, and links that threaten the recipient with
losing an account.

Fixed rules run before the judge and look at the wording alone, so ordinary mail can match
them: a little sales-style wording can be enough, even in a booking confirmation, unless
it is a reply sent with `POST /v1/messages/{id}/reply` to a message the agent received, a
draft that answers one as above, or mail to yourself. A refusal by a fixed rule cannot be
appealed (`not_appealable`), so check each template with a test key before you go live (see
below).

The error's `message` names the verdict (`reason`) and its confidence. On `POST /v1/messages`,
sending the same refused content again within an hour is refused at once, without a new
review, and the message then says it repeats an earlier refusal and counts the attempts:
change the message or appeal.

## Test keys warn instead

With a `mk_test_` key, a send that a live key would refuse succeeds (nothing is delivered)
and its answer carries `classifier_warning`, with `code`, `message`, `score` and `reason`.
Send your real templates with a test key before you go live, and rewrite any that draw a
warning.

## Mail to yourself

When every recipient is one of the workspace's own addresses (a member's sign-in email, or
an agent's sending or receiving address), the cold-outreach judgment is skipped, so a first
"hello" to yourself is not refused as cold outreach. The outright refusals above still apply,
list mechanics such as an unsubscribe link still go to the judge, and the limits below apply
as to any send.

## Appeals

If a refusal is wrong, ask for a second review of the exact content. Send the same
`subject` and `body_text` (or `body_html`) that the refused send used, and `agent` when the
workspace has several:

```bash
curl https://api.mails.ai/v1/messages/appeal \
  -H "Authorization: Bearer $MAILS_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"subject": "Your booking for Friday", "body_text": "Your table for two is booked for Friday at 19:00. Reply to this email to change it."}'
```

The answer's `outcome` is one of:

- `overturned`: the identical message is allowed for 24 hours. Send it again unchanged.
- `upheld`: the refusal stands. Remove the pitch and check the new version with a test key.
- `not_appealable`: the content broke a fixed rule, and no review exists.
- `not_blocked`: the content is not refused. Send it.

Appealing the same content again within 24 hours returns the stored outcome, with
`replayed: true`. Only `overturned`, `upheld` and `not_appealable` are stored: content that
came back `not_blocked` is judged afresh on each appeal. Each workspace may appeal 10 times in
24 hours, counting stored outcomes only; after that the answer is `429 rate_limit_exceeded`.
The dashboard has the same review as a button.

## Other limits on sending

- `403 workspace_not_approved`: a new workspace cannot send with a live key until mails.ai
  approves it. Test keys work meanwhile.
- `429 new_workspace_fanout_exceeded`: a workspace can reach only so many different addresses
  (to, cc and bcc together) in 24 hours. The error states the number. It is lowest for a new
  workspace and grows as the workspace ages. A send whose recipients were all mailed in live
  sends of the last 24 hours never counts against it.
- `429 hourly_limit_exceeded`, `daily_limit_exceeded`, and `monthly_limit_exceeded`
  (`free_tier_exceeded` on the free plan): your plan's caps. `GET /v1/billing/usage` shows
  them under `caps`. The first two also come from the sending agent's own
  `hourly_send_limit` or `daily_send_limit`, which `caps` does not show.
