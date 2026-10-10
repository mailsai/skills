// Send one email with an attachment, tags and metadata, then read the message back.
// Run: MAILS_API_KEY=mk_test_... npx tsx send-with-attachment.ts
import { randomUUID } from "node:crypto";
import { createClient } from "@mailsai/sdk";

const mails = createClient(); // reads MAILS_API_KEY

async function main(): Promise<void> {
  const invoice = "Invoice 221\nTotal due: 48.00 USD\n";

  const sent = await mails.send({
    to: "reply@test.mails.ai",
    subject: "Invoice 221",
    body_text: "Your invoice is attached.",
    body_html: "<p>Your invoice is attached.</p>",
    // Up to 10 files. Base64 content travels inside the request, so together the files can
    // come to about 3 MB. A larger file goes by an https `path` instead, up to 25 MB in all.
    attachments: [
      {
        filename: "invoice-221.txt",
        content_base64: Buffer.from(invoice, "utf8").toString("base64"),
        content_type: "text/plain",
      },
    ],
    // Tags and metadata come back on the message, so you can find it later.
    tags: [{ name: "kind", value: "invoice" }],
    metadata: { invoice_id: "221" },
    idempotency_key: `invoice-221-${randomUUID()}`,
  });
  console.log(`sent ${sent.id}, status ${sent.status}`);

  const stored = await mails.messages.get(sent.id);
  console.log(`stored with tags ${JSON.stringify(stored.tags)}`);
}

main().catch((error: unknown) => {
  console.error(error);
  process.exit(1);
});
