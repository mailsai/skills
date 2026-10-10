# The rules for email, in plain words

This is a summary to help you build mail that follows the rules. It is not legal advice.
Laws change and differ by country; for a decision that matters, ask a lawyer.

Two kinds of mail matter here:

- **Transactional mail** serves something the person already did or has: a receipt, a
  password reset, a shipping update, an account notice. This is what mails.ai sends.
- **Commercial (marketing) mail** promotes a product or service. Most of the rules below are
  about this kind. mails.ai cannot tell whether a person asked for a message, so it judges
  each one by its content: it refuses a promotion of anything other than the person's own
  order, booking or account, even when the person signed up for your mail. It passes an
  offer about those, such as an add-on to their booking, and a digest they subscribed to
  that only delivers what they signed up for (see
  [what-mails-ai-refuses.md](what-mails-ai-refuses.md)). Where mail you send does promote
  something, the rules below still apply to it.

## United States: CAN-SPAM

Applies to commercial email, including business-to-business email. A message is commercial
when its primary purpose is to advertise or promote a product or service. Every commercial
message must:

1. Use accurate From, To and Reply-To and routing information that identifies who sent it.
2. Use a subject line that matches the content.
3. Say clearly that it is an advertisement.
4. Include a valid postal address: a street address, a registered post office box, or a
   registered private mailbox.
5. Explain how to opt out of future marketing email.
6. Honor an opt-out within 10 business days, keep the opt-out working for at least 30 days
   after sending, ask for nothing more than the email address, and never sell or pass on the
   address afterwards.

You stay responsible for mail others send for you.

Transactional or relationship messages are exempt from most of this, but their routing
information must still be accurate. They are, narrowly: completing or confirming a
transaction the person agreed to; warranty, recall, safety or security information about
something they bought; changes to their account, subscription or membership, or regular
account statements; employment information; and delivering what they bought.

A message that mixes both is judged by its primary purpose. If the subject line suggests an
ad, or the transactional part does not come first, the message counts as commercial.

Each email in violation can cost up to $53,088.

Source: the Federal Trade Commission, "CAN-SPAM Act: A Compliance Guide for Business".

## European Union: GDPR and the ePrivacy rules

**GDPR** applies to organizations in the EU, and to organizations elsewhere that offer goods
or services to people in the EU or monitor their behavior there (Article 3). An email
address is personal data. For every use of it you need a lawful basis (Article 6), such as
the person's consent or a contract with them.

- Consent must be something you can prove, and withdrawing it must be as easy as giving it
  (Article 7).
- A person can object at any time to their data being used for direct marketing, and then
  you must stop. You must tell them about this right, clearly and separately, no later than
  your first message (Article 21).
- Breaking these rules can cost up to 20 million euros or 4% of worldwide annual turnover,
  whichever is higher (Article 83).

**ePrivacy** (Directive 2002/58/EC, Article 13) covers marketing email specifically:

- Marketing email needs the person's prior consent.
- One exception: if you got the address from a customer while selling them something, you
  may email them about your own similar products or services, as long as you offered a free,
  easy way to refuse when you collected the address and offer it again in every message.
- Marketing email must never hide who sent it, and must give a valid address where the
  person can ask you to stop.

Each EU country puts the ePrivacy rules into its own law, so details vary.

## Canada: CASL

Applies to commercial electronic messages. A message is commercial if encouraging a commercial
activity is its purpose or one of its purposes (section 1). Every commercial message needs:

- **Consent**, express or implied (section 6(1)). Implied consent includes an existing
  business relationship: a purchase in the last two years, or an inquiry or application in
  the last six months (section 10).
- **Identification and contact details** of the sender, valid for at least 60 days after
  sending (section 6(2) and 6(3)).
- **An unsubscribe mechanism** that costs nothing, stays valid for at least 60 days, and is
  honored within 10 business days (section 11).

Messages that only provide a requested quote, complete a transaction the person agreed to,
give warranty, recall or safety information, report facts about their account or
subscription, or deliver what they bought do not need consent (section 6(6)). They still need
the identification, contact details and unsubscribe mechanism above.

Penalties reach $10,000,000 per violation for a business (section 20).

Source: the Canadian Anti-Spam Legislation, S.C. 2010, c. 23.

## Gmail and Yahoo

Large mailbox providers set their own requirements on top of the law.

**Everyone who sends to Gmail or Yahoo** must:

- authenticate with SPF or DKIM;
- keep the spam-complaint rate below 0.3%;
- send from servers with valid forward and reverse DNS, over TLS for Gmail;
- follow the email format standards (RFC 5322).

**Gmail, above 5,000 messages a day to Gmail accounts, and Yahoo's bulk senders** must also:

- authenticate with both SPF and DKIM, and publish a DMARC policy (`p=none` is enough);
- align the From domain with the SPF or DKIM domain;
- give marketing and subscribed mail one-click unsubscribe (the `List-Unsubscribe` and
  `List-Unsubscribe-Post` headers) and a visible unsubscribe link, and honor unsubscribes
  within two days.

Gmail does not require one-click unsubscribe on transactional mail such as password resets
and booking confirmations. Both providers ask for DKIM keys of at least 1024 bits, and Gmail
warns against `Re:` and `Fwd:` subjects on messages that are not replies or forwards.

Sources: Google, "Email sender guidelines" and "Email sender guidelines FAQ"; Yahoo, "Sender
Requirements & Recommendations".

## What this means for an agent that sends through mails.ai

- Send mail that serves the person's own action or account, and keep any promotion out of it.
- Send mail a person subscribed to with `list_unsubscribe: true`, so it carries one-click
  unsubscribe (see "One-click unsubscribe" in this skill). After a click, mails.ai refuses
  your workspace's later live sends to that address. Stop mailing it from your other
  systems too.
- Put an unsubscribe link in the text only of mail the person subscribed to. On other mail,
  mails.ai reads list wording such as "unsubscribe" or "manage your preferences" as a strong
  sign of bulk mail, which it refuses.
- Keep a record of how and when each person agreed to receive what you send.
- Put your postal address and a way to reach you in anything promotional.
- Treat bounces, complaints and unsubscribes as final for that address (see
  [bounces-and-complaints.md](bounces-and-complaints.md)).
