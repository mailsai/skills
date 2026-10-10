// List an agent's conversations, read the newest one, and close it.
// Run: MAILS_API_KEY=mk_test_... npx tsx threads.ts [agent-name]
//
// Closing a thread needs a key with the `manage` scope. Reading needs `read`.
import { createClient, MailsError } from "@mailsai/sdk";

const mails = createClient(); // reads MAILS_API_KEY

async function main(): Promise<void> {
  // Threads come newest first, without trash unless you pass `folder`. `agent_id` takes an
  // agent's name or its agt_ id. Leave it out to list every agent's threads; a key tied to
  // one agent lists only its own.
  const agent = process.argv[2];
  const page = await mails.threads.list({ agent_id: agent, status: "open", limit: 10 });
  if (page.data.length === 0) {
    console.log("no open threads");
    return;
  }
  for (const thread of page.data) {
    console.log(`${thread.id}  ${thread.message_count} messages  ${thread.subject ?? "(no subject)"}`);
  }

  // One thread with every message in it, oldest first, both directions.
  const thread = await mails.threads.get(page.data[0].id);
  for (const message of thread.messages) {
    const who = message.direction === "inbound" ? `from ${message.from}` : `to ${message.to.join(", ")}`;
    console.log(`  ${message.direction} ${who}: ${message.snippet}`);
  }

  try {
    const closed = await mails.threads.update(thread.id, { status: "closed", labels: ["answered"] });
    console.log(`${closed.id} is now ${closed.status}`);
  } catch (error) {
    if (error instanceof MailsError && error.code === "insufficient_scope") {
      console.log("this key cannot change threads: it needs the manage scope");
      return;
    }
    throw error;
  }
}

main().catch((error: unknown) => {
  console.error(error);
  process.exit(1);
});
