// Decide what an agent may do with one inbound email event.
// Library file: pure functions, no network calls. Covers levels 1 to 3 of the agent-inbox skill.
//
//   Level 1  sender allowlist   only listed addresses may instruct the agent
//   Level 2  domain allowlist   any address at a listed domain may instruct the agent
//   Level 3  score threshold    hold mail that mails.ai scored as a likely prompt injection
//
// A listed domain covers its subdomains: "example.com" covers "mail.example.com" but not
// "notexample.com".

/** The fields of a mails.ai event that the policy reads. A webhook body and an SDK event both fit. */
export type InboundEvent = {
  id: string;
  type: string;
  injection_score?: number;
  quarantined?: boolean;
  data: Record<string, unknown>;
};

export type Policy = {
  /** Level 1. Exact addresses that may instruct the agent. */
  allowedSenders: string[];
  /** Level 2. Sender domains that may instruct the agent. */
  allowedDomains: string[];
  /** Sender domains whose mail is ignored, whatever the other settings say. */
  blockedDomains: string[];
  /** Accept mail from anyone. Use only with sandboxed tools (level 4) or human approval (level 5). */
  openToAnySender: boolean;
  /** Hold mail unless `dmarc` is "pass", which proves the From address. An address on an
   *  allowlist is only a claim until then. */
  requireDmarc: boolean;
  /** Level 3. Hold mail scored at or above this. 0.5 also holds mail whose scan failed. */
  maxInjectionScore: number;
};

export type Decision = {
  /** process: the agent may act. hold: keep for a person. ignore: do nothing. */
  action: "process" | "hold" | "ignore";
  reason: string;
};

/** The two lists a mails.ai agent carries, as GET /v1/agents/{id} returns them. */
export type AgentLists = { allowlist_domains?: string[] | null; blocklist_domains?: string[] | null };

export const INBOUND_EVENT_TYPES = [
  "message.received",
  "reply.received",
  "message.received.unauthenticated",
];

export const STRICT_POLICY: Policy = {
  allowedSenders: [],
  allowedDomains: [],
  blockedDomains: [],
  openToAnySender: false,
  requireDmarc: true,
  maxInjectionScore: 0.5,
};

/** True when `domain` is one of `listed` or a subdomain of one. */
export function domainListed(domain: string, listed: string[]): boolean {
  return listed.some((entry) => {
    const d = entry.trim().toLowerCase();
    return d !== "" && (domain === d || domain.endsWith(`.${d}`));
  });
}

/**
 * True when mails.ai proved the From address: `dmarc` is "pass", so the domain of `from.address`
 * publishes DMARC and a DKIM signature from that domain verified. `dkim_pass` is not enough,
 * because anyone can sign mail with a domain of their own, and `envelope_from` is never proof.
 */
export function senderProven(event: InboundEvent): boolean {
  return event.data.dmarc === "pass";
}

/** The sender address in lower case, or null when the event carries none. */
export function senderOf(event: InboundEvent): string | null {
  const from = event.data.from;
  if (typeof from !== "object" || from === null) return null;
  const address = (from as { address?: unknown }).address;
  return typeof address === "string" && address.includes("@") ? address.trim().toLowerCase() : null;
}

export function decide(event: InboundEvent, policy: Policy): Decision {
  if (!INBOUND_EVENT_TYPES.includes(event.type)) {
    return { action: "ignore", reason: `${event.type} is not an inbound email event` };
  }
  const sender = senderOf(event);
  if (!sender) return { action: "hold", reason: "the event has no sender address" };

  const domain = sender.slice(sender.lastIndexOf("@") + 1);
  if (domainListed(domain, policy.blockedDomains)) {
    return { action: "ignore", reason: `${domain} is on the blocklist` };
  }

  // Levels 1 and 2: who may instruct the agent.
  const listed =
    policy.allowedSenders.some((a) => a.trim().toLowerCase() === sender) ||
    domainListed(domain, policy.allowedDomains);
  if (!listed && !policy.openToAnySender) {
    return { action: "ignore", reason: `${sender} is not on the allowlist` };
  }

  // A From address can be forged. Mail that fails these checks only claims to be from the sender.
  if (event.type === "message.received.unauthenticated") {
    return { action: "hold", reason: "the sender's domain signs its mail and no signature from it verified, so the sender address is likely forged" };
  }
  if (policy.requireDmarc && !senderProven(event)) {
    return { action: "hold", reason: "the sender's domain did not pass DMARC, so the sender address is unverified" };
  }

  // Level 3: what mails.ai's prompt-injection scan found.
  if (event.quarantined === true) {
    return { action: "hold", reason: "mails.ai quarantined this message as a likely prompt injection" };
  }
  const score = event.injection_score;
  if (typeof score !== "number") {
    return { action: "hold", reason: "the event has no injection score" };
  }
  if (score >= policy.maxInjectionScore) {
    return { action: "hold", reason: `injection score ${score} is at or above ${policy.maxInjectionScore}` };
  }
  return { action: "process", reason: `sender accepted, injection score ${score}` };
}

const NO_SCAN = ["rules-layer", "scan-unavailable", "not-scanned"];

/**
 * True when the prompt-injection scan really ran on this message.
 * Pass the event from GET /v1/events/{id}, which always carries classifier_model.
 * "scan-unavailable" means the scan failed, "not-scanned" that none was asked for, and
 * "rules-layer" marks older mail that a rule scored without a scan. Every other value,
 * "rules-layer+injection-scan" included, means it ran.
 */
export function wasScanned(eventDetail: { classifier_model?: string }): boolean {
  const model = eventDetail.classifier_model;
  return typeof model === "string" && !NO_SCAN.includes(model);
}

/**
 * Add an agent's own lists to a policy. mails.ai stores allowlist_domains and blocklist_domains
 * on the agent (set them when you create it, in the dashboard or with POST /v1/agents, or later
 * with PATCH /v1/agents/{id}) and applies them to the agent's sends, but it does not filter
 * inbound mail by them. Your handler has to apply them, and this is where.
 * Entries are read as mails.ai reads them: a leading "@" or "*." is ignored.
 */
export function withAgentLists(policy: Policy, agent: AgentLists): Policy {
  const clean = (list: string[] | null | undefined) =>
    (list ?? [])
      .map((domain) => domain.trim().toLowerCase().replace(/^@/, "").replace(/^\*\./, "").replace(/\.$/, ""))
      .filter(Boolean);
  return {
    ...policy,
    allowedDomains: [...policy.allowedDomains, ...clean(agent.allowlist_domains)],
    blockedDomains: [...policy.blockedDomains, ...clean(agent.blocklist_domains)],
  };
}

/** Read a policy from environment variables. Unset variables keep the strict defaults. */
export function policyFromEnv(env: Record<string, string | undefined> = process.env): Policy {
  const list = (value: string | undefined) =>
    (value ?? "").split(",").map((item) => item.trim().toLowerCase()).filter(Boolean);
  const threshold = Number(env.MAX_INJECTION_SCORE);
  return {
    allowedSenders: list(env.ALLOWED_SENDERS),
    allowedDomains: list(env.ALLOWED_DOMAINS),
    blockedDomains: list(env.BLOCKED_DOMAINS),
    openToAnySender: env.OPEN_TO_ANY_SENDER === "1",
    requireDmarc: env.REQUIRE_DMARC !== "0",
    maxInjectionScore: env.MAX_INJECTION_SCORE && Number.isFinite(threshold) ? threshold : STRICT_POLICY.maxInjectionScore,
  };
}
