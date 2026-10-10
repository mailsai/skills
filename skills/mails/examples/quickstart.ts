// Send an email as an agent, wait for the reply, and answer it in the same thread.
// Run: MAILS_API_KEY=mk_test_... npx tsx quickstart.ts
//
// Uses reply@test.mails.ai, the address that answers by itself. No real person gets mail.
import { randomUUID } from "node:crypto";
import { createClient, MailsError, type TypedEvent } from "@mailsai/sdk";

const mails = createClient(); // reads MAILS_API_KEY

/** Poll the event list until the reply to `sentId` shows up. */
async function waitForReply(sentId: string, since: string): Promise<TypedEvent> {
  for (let attempt = 0; attempt < 30; attempt++) {
    const page = await mails.events.list({ event_type: "reply.received", since, limit: 25 });
    const reply = page.data.find((event) => event.data.thread_root_message_id === sentId);
    if (reply) return reply;
    await new Promise((resolve) => setTimeout(resolve, 2000));
  }
  throw new Error("no reply after 60 seconds");
}

async function main(): Promise<void> {
  // 1. Check the key, and see whether it is a test key or a live key.
  const me = await mails.me();
  console.log(`workspace ${me.workspace?.slug}, ${me.api_key.mode} key`);

  // 2. Send. With no `agent`, the workspace's only agent sends, or one is created if the
  //    key holds `manage` (a key made in the dashboard does).
  //    (A workspace with several agents must pass `agent: "<name>"`.)
  //    One idempotency key per message, so a retry of this call can never send it twice.
  const sent = await mails.send({
    to: "reply@test.mails.ai",
    subject: "Order 1042 has shipped",
    body_text: "Your order is on its way. Reply to this email if anything looks wrong.",
    idempotency_key: `order-1042-shipped-${randomUUID()}`,
  });
  console.log(`sent ${sent.id} as ${sent.from}, thread ${sent.thread_id}`);

  // 3. Wait for the reply. `since` takes the timestamp of the send, exactly as the API returned it.
  const reply = await waitForReply(sent.id, sent.created_at);
  console.log(`reply from ${JSON.stringify(reply.data.from)}: ${String(reply.data.extracted_text)}`);
  console.log(`injection score ${reply.injection_score}, quarantined ${reply.quarantined}`);

  // 4. Answer in the same thread. Only with a test key, where it is free: with a live key the
  //    answer would count as one more send on your usage.
  if (me.api_key.mode === "test" && typeof reply.data.source_message_id === "string") {
    const answer = await mails.messages.reply(reply.data.source_message_id, {
      body_text: "Thanks, noted. Nothing else is needed.",
    });
    console.log(`answered with ${answer.id} in thread ${answer.thread_id}`);
  }
}

main().catch((error: unknown) => {
  if (error instanceof MailsError) {
    console.error(`${error.status} ${error.code}: ${error.message} (request ${error.requestId})`);
  } else {
    console.error(error);
  }
  process.exit(1);
});
