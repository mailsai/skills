// Check an address and your sending health before you send, and handle each refusal.
// Run: MAILS_API_KEY=mk_test_... npx tsx check-before-send.ts someone@example.com [agent-name]
import { randomUUID } from "node:crypto";
import { createClient, MailsError } from "@mailsai/sdk";

const mails = createClient(); // reads MAILS_API_KEY

async function main(): Promise<void> {
  const recipient = process.argv[2] ?? "reply@test.mails.ai";

  // 1. Is the address suppressed? A hard bounce, a spam complaint or an unsubscribe puts it there.
  const suppression = await mails.suppression.check(recipient);
  if (suppression.suppressed) {
    console.log(`not sending: ${recipient} is suppressed (${suppression.type}, since ${suppression.since})`);
    return;
  }

  // 2. How healthy is the sending? An agent is paused above 5% bounces or 0.3% complaints.
  //    With an agent name you get that agent's 30-day counts. Without one, the workspace score.
  const agent = process.argv[3];
  const health = await mails.reputation.get(agent);
  const sends = health.send_count_30d ?? 0;
  if (sends > 0) {
    const bounceRate = (health.bounce_count_30d ?? 0) / sends;
    const complaintRate = (health.complaint_count_30d ?? 0) / sends;
    console.log(`30 days: ${sends} sends, ${(bounceRate * 100).toFixed(2)}% bounced, ${(complaintRate * 100).toFixed(2)}% complaints`);
  } else {
    console.log(`reputation ${health.reputation} (0 to 1)`);
  }

  // 3. Send, and handle the refusals that a retry will not fix.
  try {
    const sent = await mails.send({
      agent,
      to: recipient,
      subject: "Your receipt for order 1042",
      body_text: "Thanks for your order. Your receipt is below.\n\nOrder 1042: 48.00 USD",
      idempotency_key: `receipt-1042-${randomUUID()}`,
    });
    if (sent.classifier_warning) {
      // Test keys only: this exact message would be refused on a live key.
      console.log(`would be refused on a live key: ${sent.classifier_warning.reason}`);
    } else {
      console.log(`sent ${sent.id}`);
    }
  } catch (error) {
    if (!(error instanceof MailsError)) throw error;
    switch (error.code) {
      case "recipient_suppressed":
        console.log("refused: the address is suppressed. Do not retry.");
        break;
      case "cold_email_prohibited":
        console.log("refused: the message reads as cold outreach. Rewrite it or appeal. Do not retry as is.");
        break;
      case "agent_paused":
        console.log("refused: the agent is paused, usually for bounces or complaints. Fix the list first.");
        break;
      default:
        throw error;
    }
  }
}

main().catch((error: unknown) => {
  console.error(error);
  process.exit(1);
});
