// The only ways the inbound handler sends mail. Levels 4 and 5 of the agent-inbox skill.
// Library file. If your model calls tools, give it one of these two and nothing else that can send.
//
//   Level 4  replyToSender      a reply that can only reach the person who wrote
//   Level 5  draftForApproval   a draft that a person sends from the dashboard
//
// The two reads at the end are for the handler, not for the model.
import { createClient } from "@mailsai/sdk";
import type { AgentLists } from "./inbox-policy.ts";

// A subject may have 998 characters (POST /v1/drafts), and received mail can carry a longer one.
const MAX_SUBJECT = 998;

let client: ReturnType<typeof createClient> | undefined;
const mails = () => (client ??= createClient()); // reads MAILS_API_KEY on first use

/** The fields of an inbound event these tools read. */
export type InboundEvent = { id: string; data: Record<string, unknown> };

function field(event: InboundEvent, name: string): string {
  const value = event.data[name];
  if (typeof value !== "string" || value === "") throw new Error(`event ${event.id} has no data.${name}`);
  return value;
}

function senderAddress(event: InboundEvent): string {
  const from = event.data.from;
  const address = typeof from === "object" && from !== null ? (from as { address?: unknown }).address : undefined;
  if (typeof address !== "string" || !address.includes("@")) throw new Error(`event ${event.id} has no sender address`);
  return address;
}

/**
 * Level 4. Reply to the person who wrote, in the same thread.
 * mails.ai takes the recipient from the received message, so the model cannot choose who gets the mail.
 * This function takes no cc or bcc on purpose: those would let a hijacked model copy someone in.
 * The Idempotency-Key is built from the event id, so handling the same event twice sends one reply.
 */
export async function replyToSender(event: InboundEvent, text: string): Promise<{ id: string; status: string }> {
  return mails().messages.reply(field(event, "source_message_id"), {
    body_text: text,
    idempotency_key: `reply-${event.id}`,
  });
}

/**
 * Level 5. Write the reply as a draft and stop. Nothing is sent.
 * A person opens the returned URL, reads the draft and presses Send (or deletes it).
 */
export async function draftForApproval(event: InboundEvent, text: string): Promise<{ draftId: string; reviewUrl: string }> {
  const subject = typeof event.data.subject === "string" && event.data.subject !== "" ? event.data.subject : "your message";
  const draft = await mails().drafts.create({
    agent: field(event, "agent_id"),
    to: senderAddress(event),
    subject: (/^re:/i.test(subject) ? subject : `Re: ${subject}`).slice(0, MAX_SUBJECT),
    body_text: text,
    in_reply_to_message_id: field(event, "source_message_id"),
  });
  return { draftId: draft.id, reviewUrl: `https://app.mails.ai/drafts/${draft.id}` };
}

const AGENT_LISTS_TTL_MS = 60_000;
const agentListsCache = new Map<string, { at: number; lists: AgentLists }>();

/** The agent's allowlist_domains and blocklist_domains, read at most once a minute per agent. */
export async function fetchAgentLists(agentId: string): Promise<AgentLists> {
  const cached = agentListsCache.get(agentId);
  if (cached && Date.now() - cached.at < AGENT_LISTS_TTL_MS) return cached.lists;
  const agent = await mails().agents.get(agentId);
  const lists = { allowlist_domains: agent.allowlist_domains ?? [], blocklist_domains: agent.blocklist_domains ?? [] };
  agentListsCache.set(agentId, { at: Date.now(), lists });
  return lists;
}

/**
 * The event as GET /v1/events/{id} returns it, which adds injection_categories.
 * The SDK's event type leaves out these two fields, so this reads them with request().
 */
export async function fetchEventDetail(eventId: string): Promise<{ classifier_model?: string; injection_categories?: string[] }> {
  return mails().request("GET", `/v1/events/${encodeURIComponent(eventId)}`);
}
