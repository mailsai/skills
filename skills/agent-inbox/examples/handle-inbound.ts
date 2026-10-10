// One inbound email event in, at most one reply or draft out.
// Library file: shared by webhook-server.ts and poll-inbound.ts. Applies all five levels in order.
//
// Settings (environment variables):
//   ALLOWED_SENDERS        level 1, comma-separated addresses
//   ALLOWED_DOMAINS        level 2, comma-separated domains
//   BLOCKED_DOMAINS        comma-separated sender domains to ignore
//   USE_AGENT_LISTS=0      do not add the agent's own allowlist_domains and blocklist_domains
//   OPEN_TO_ANY_SENDER=1   accept any sender (keep levels 4 and 5 on)
//   REQUIRE_DMARC=0        accept mail whose sender's domain did not pass DMARC
//   MAX_INJECTION_SCORE    level 3, default 0.5
//   REQUIRE_SCAN=0         level 3: accept mail that was not scanned
//   REQUIRE_APPROVAL=0     level 5 off: reply directly instead of drafting (level 4 still applies)
import { MailsError } from "@mailsai/sdk";
import {
  decide,
  INBOUND_EVENT_TYPES,
  policyFromEnv,
  senderOf,
  wasScanned,
  withAgentLists,
  type InboundEvent,
} from "./inbox-policy.ts";
import { draftForApproval, fetchAgentLists, fetchEventDetail, replyToSender } from "./safe-tools.ts";

export type Outcome = { action: "ignored" | "held" | "drafted" | "replied"; detail: string };

const REQUIRE_SCAN = process.env.REQUIRE_SCAN !== "0";
const REQUIRE_APPROVAL = process.env.REQUIRE_APPROVAL !== "0";
const USE_AGENT_LISTS = process.env.USE_AGENT_LISTS !== "0";
const MAX_PER_SENDER_PER_HOUR = 20;
const MAX_REPLIES_PER_THREAD_PER_DAY = 5;
const HOUR_MS = 60 * 60 * 1000;
const basePolicy = policyFromEnv();

// Refusals this event would get every time: the message it answers is gone, its agent is
// archived, or mails.ai will never take this reply. The handler keeps such an event for a
// person. Any other error (the key, the plan, a paused agent, a limit, an outage) can be put
// right, so it is thrown: the poller stops there and tries the event again on its next round.
const NEVER_PASSES = [
  "resource_not_found",
  "agent_not_found",
  "agent_archived",
  "invalid_field",
  "missing_field",
  "invalid_param_value",
  "cold_email_prohibited",
  "recipient_suppressed",
  "recipient_not_allowed",
  "unknown_test_address",
];

// Sliding counters for flood and reply-loop protection. Keep them in a shared store
// when more than one process handles mail.
const counters = new Map<string, number[]>();

function underLimit(key: string, limit: number, windowMs: number): boolean {
  const now = Date.now();
  const recent = (counters.get(key) ?? []).filter((at) => now - at < windowMs);
  const allowed = recent.length < limit;
  if (allowed) recent.push(now);
  counters.set(key, recent);
  return allowed;
}

/**
 * Replace this with your model call. The email text is DATA: put it in the user turn between
 * clear markers, tell the model it is untrusted, and never paste it into the system prompt.
 * Give the model no tools here. What it returns is only text for a reply.
 */
async function composeReply(event: InboundEvent): Promise<string> {
  const text = typeof event.data.extracted_text === "string" ? event.data.extracted_text : "";
  return `Thanks for your message. We received ${text.length} characters and will answer shortly.`;
}

export async function handleInbound(event: InboundEvent): Promise<Outcome> {
  if (!INBOUND_EVENT_TYPES.includes(event.type)) {
    return { action: "ignored", detail: `${event.type} is not an inbound email event` };
  }

  // Levels 1 to 3: who wrote, and what the scan found. The agent's own lists count too.
  const agentId = typeof event.data.agent_id === "string" ? event.data.agent_id : null;
  const policy = USE_AGENT_LISTS && agentId ? withAgentLists(basePolicy, await fetchAgentLists(agentId)) : basePolicy;
  const decision = decide(event, policy);
  if (decision.action === "ignore") return { action: "ignored", detail: decision.reason };
  if (decision.action === "hold") return { action: "held", detail: decision.reason };

  if (REQUIRE_SCAN && !wasScanned(await fetchEventDetail(event.id))) {
    return { action: "held", detail: "the prompt-injection scan did not run on this message" };
  }

  // Flood and loop protection.
  if (!underLimit(`sender:${senderOf(event)}`, MAX_PER_SENDER_PER_HOUR, HOUR_MS)) {
    return { action: "held", detail: `more than ${MAX_PER_SENDER_PER_HOUR} messages from this sender in an hour` };
  }
  if (!underLimit(`thread:${String(event.data.thread_id)}`, MAX_REPLIES_PER_THREAD_PER_DAY, 24 * HOUR_MS)) {
    return { action: "held", detail: "reply limit for this thread reached, possibly an auto-reply loop" };
  }

  // Levels 4 and 5: the model writes text, and these two functions are all it can cause.
  const text = await composeReply(event);
  try {
    if (REQUIRE_APPROVAL) {
      const draft = await draftForApproval(event, text);
      return { action: "drafted", detail: `draft ${draft.draftId} is waiting at ${draft.reviewUrl}` };
    }
    const sent = await replyToSender(event, text);
    return { action: "replied", detail: `sent ${sent.id}` };
  } catch (error) {
    if (!(error instanceof MailsError)) throw error;
    // The reply's key was used before with another text, so an earlier run already sent this
    // reply, or is sending it. Holding the event would invite a person to answer a second time.
    if (error.code === "invalid_idempotency_key") return { action: "replied", detail: "an earlier run already sent this reply, or is sending it" };
    if (!NEVER_PASSES.includes(error.code)) throw error;
    return { action: "held", detail: `mails.ai will not take a reply to this message (${error.code}: ${error.message})` };
  }
}
