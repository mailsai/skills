// Receive mails.ai webhooks and answer inbound email safely.
// Run: MAILS_API_KEY=mk_test_... MAILS_WEBHOOK_SECRET=whsec_... ALLOWED_SENDERS=you@example.com npx tsx webhook-server.ts
//
// MAILS_WEBHOOK_SECRET is the signing secret that POST /v1/webhooks returns once.
// PORT defaults to 8787. The policy settings are listed in handle-inbound.ts.
import { createServer, type IncomingMessage } from "node:http";
import { handleInbound } from "./handle-inbound.ts";
import type { InboundEvent } from "./inbox-policy.ts";
import { verifySignature } from "./verify-signature.ts";

const SECRET = process.env.MAILS_WEBHOOK_SECRET ?? "";
const PORT = Number(process.env.PORT ?? 8787);
const MAX_BODY_BYTES = 5_000_000;
const SEEN_TTL_MS = 24 * 60 * 60 * 1000;

// Event ids already handled. In production keep these in a database with a unique index,
// because this Map is empty again after a restart.
const seen = new Map<string, number>();

function firstTime(eventId: string): boolean {
  const now = Date.now();
  for (const [id, at] of seen) if (now - at > SEEN_TTL_MS) seen.delete(id);
  if (seen.has(eventId)) return false;
  seen.set(eventId, now);
  return true;
}

function readRawBody(req: IncomingMessage): Promise<string | null> {
  return new Promise((resolve, reject) => {
    const chunks: Buffer[] = [];
    let size = 0;
    req.on("data", (chunk: Buffer) => {
      size += chunk.length;
      if (size <= MAX_BODY_BYTES) chunks.push(chunk);
    });
    req.on("end", () => resolve(size > MAX_BODY_BYTES ? null : Buffer.concat(chunks).toString("utf8")));
    req.on("error", reject);
  });
}

const server = createServer(async (req, res) => {
  const answer = (status: number, body: string) => {
    res.writeHead(status, { "Content-Type": "text/plain" });
    res.end(body);
  };
  try {
    if (req.method !== "POST" || req.url !== "/webhooks/mails") return answer(404, "not found");
    const rawBody = await readRawBody(req);
    if (rawBody === null) return answer(413, "body too large");

    // 1. Signature first. Nothing in the body is trusted before this passes.
    const header = req.headers["x-mails-signature"];
    if (!verifySignature(rawBody, Array.isArray(header) ? header[0] : header, SECRET)) {
      return answer(401, "bad signature");
    }

    // 2. Parse only after verifying. Take the event id from the signed body, not from a header.
    const event = JSON.parse(rawBody) as InboundEvent;
    if (typeof event.id !== "string" || typeof event.type !== "string" || typeof event.data !== "object" || event.data === null) {
      return answer(400, "not an event");
    }

    // 3. Each event is handled once, however many times it is delivered.
    if (!firstTime(event.id)) return answer(200, "duplicate");

    // 4. Answer before doing the work. mails.ai waits 5 seconds, then counts the attempt as failed.
    //    In production, save the event to a queue or table here and handle it from a worker,
    //    so a crash between the answer and the work does not lose the message.
    answer(200, "ok");
    handleInbound(event)
      .then((outcome) => console.log(`${event.id} ${outcome.action}: ${outcome.detail}`))
      .catch((error: unknown) => {
        seen.delete(event.id); // let a redelivery try again: POST /v1/events/{id}/redeliver
        console.error(`${event.id} failed:`, error);
      });
  } catch (error) {
    console.error("webhook error:", error);
    if (!res.headersSent) answer(500, "error");
  }
});

if (!SECRET) {
  console.error("Set MAILS_WEBHOOK_SECRET to the signing secret of your webhook.");
  process.exit(1);
}
server.listen(PORT, () => console.log(`listening on http://localhost:${PORT}/webhooks/mails`));
