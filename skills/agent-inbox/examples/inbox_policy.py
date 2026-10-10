"""Decide what an agent may do with one inbound email event.

Library file: pure functions, no network calls. Covers levels 1 to 3 of the agent-inbox skill.

  Level 1  sender allowlist   only listed addresses may instruct the agent
  Level 2  domain allowlist   any address at a listed domain may instruct the agent
  Level 3  score threshold    hold mail that mails.ai scored as a likely prompt injection

A listed domain covers its subdomains: "example.com" covers "mail.example.com" but not
"notexample.com".
"""
from __future__ import annotations

import dataclasses
import math
import os
from dataclasses import dataclass, field
from typing import Any, List, Mapping, Optional

INBOUND_EVENT_TYPES = [
    "message.received",
    "reply.received",
    "message.received.unauthenticated",
]


@dataclass
class Policy:
    # Level 1. Exact addresses that may instruct the agent.
    allowed_senders: List[str] = field(default_factory=list)
    # Level 2. Sender domains that may instruct the agent.
    allowed_domains: List[str] = field(default_factory=list)
    # Sender domains whose mail is ignored, whatever the other settings say.
    blocked_domains: List[str] = field(default_factory=list)
    # Accept mail from anyone. Use only with sandboxed tools (level 4) or human approval (level 5).
    open_to_any_sender: bool = False
    # Hold mail unless `dmarc` is "pass", which proves the From address. An address on an
    # allowlist is only a claim until then.
    require_dmarc: bool = True
    # Level 3. Hold mail scored at or above this. 0.5 also holds mail whose scan failed.
    max_injection_score: float = 0.5


@dataclass
class Decision:
    # process: the agent may act. hold: keep for a person. ignore: do nothing.
    action: str
    reason: str


def domain_listed(domain: str, listed: List[str]) -> bool:
    """True when `domain` is one of `listed` or a subdomain of one."""
    for entry in listed:
        d = entry.strip().lower()
        if d and (domain == d or domain.endswith("." + d)):
            return True
    return False


def sender_proven(event: Mapping[str, Any]) -> bool:
    """True when mails.ai proved the From address.

    `dmarc` is "pass": the domain of `from.address` publishes DMARC and a DKIM signature from
    that domain verified. `dkim_pass` is not enough, because anyone can sign mail with a domain
    of their own, and `envelope_from` is never proof.
    """
    return (event.get("data") or {}).get("dmarc") == "pass"


def sender_of(event: Mapping[str, Any]) -> Optional[str]:
    """The sender address in lower case, or None when the event carries none."""
    sender = (event.get("data") or {}).get("from")
    address = sender.get("address") if isinstance(sender, dict) else None
    if isinstance(address, str) and "@" in address:
        return address.strip().lower()
    return None


def decide(event: Mapping[str, Any], policy: Policy) -> Decision:
    event_type = event.get("type")
    if event_type not in INBOUND_EVENT_TYPES:
        return Decision("ignore", f"{event_type} is not an inbound email event")
    sender = sender_of(event)
    if sender is None:
        return Decision("hold", "the event has no sender address")

    domain = sender.rsplit("@", 1)[1]
    if domain_listed(domain, policy.blocked_domains):
        return Decision("ignore", f"{domain} is on the blocklist")

    # Levels 1 and 2: who may instruct the agent.
    listed = any(a.strip().lower() == sender for a in policy.allowed_senders) or domain_listed(
        domain, policy.allowed_domains
    )
    if not listed and not policy.open_to_any_sender:
        return Decision("ignore", f"{sender} is not on the allowlist")

    # A From address can be forged. Mail that fails these checks only claims to be from the sender.
    if event_type == "message.received.unauthenticated":
        return Decision(
            "hold", "the sender's domain signs its mail and no signature from it verified, so the sender address is likely forged"
        )
    if policy.require_dmarc and not sender_proven(event):
        return Decision("hold", "the sender's domain did not pass DMARC, so the sender address is unverified")

    # Level 3: what mails.ai's prompt-injection scan found.
    if event.get("quarantined") is True:
        return Decision("hold", "mails.ai quarantined this message as a likely prompt injection")
    score = event.get("injection_score")
    if isinstance(score, bool) or not isinstance(score, (int, float)):
        return Decision("hold", "the event has no injection score")
    if score >= policy.max_injection_score:
        return Decision("hold", f"injection score {score} is at or above {policy.max_injection_score}")
    return Decision("process", f"sender accepted, injection score {score}")


def was_scanned(event_detail: Mapping[str, Any]) -> bool:
    """True when the prompt-injection scan really ran on this message.

    Pass the event from GET /v1/events/{id}, which always carries classifier_model.
    "scan-unavailable" means the scan failed, "not-scanned" that none was asked for, and
    "rules-layer" marks older mail that a rule scored without a scan. Every other value,
    "rules-layer+injection-scan" included, means it ran.
    """
    model = event_detail.get("classifier_model")
    return isinstance(model, str) and model not in ("rules-layer", "scan-unavailable", "not-scanned")


def with_agent_lists(policy: Policy, agent: Mapping[str, Any]) -> Policy:
    """Add an agent's own lists to a policy.

    mails.ai stores allowlist_domains and blocklist_domains on the agent (set them when you create
    it, in the dashboard or with POST /v1/agents, or later with PATCH /v1/agents/{id}) and applies
    them to the agent's sends, but it does not filter inbound mail by them. Your handler has to
    apply them, and this is where. Entries are read as mails.ai reads them: a leading "@" or "*."
    is ignored. `agent` is the object GET /v1/agents/{id} returns.
    """

    def clean(name: str) -> List[str]:
        entries = [d for d in agent.get(name) or [] if isinstance(d, str)]
        domains = (d.strip().lower().removeprefix("@").removeprefix("*.").removesuffix(".") for d in entries)
        return [d for d in domains if d]

    return dataclasses.replace(
        policy,
        allowed_domains=policy.allowed_domains + clean("allowlist_domains"),
        blocked_domains=policy.blocked_domains + clean("blocklist_domains"),
    )


def policy_from_env(env: Optional[Mapping[str, str]] = None) -> Policy:
    """Read a policy from environment variables. Unset variables keep the strict defaults."""
    env = os.environ if env is None else env

    def items(name: str) -> List[str]:
        return [item.strip().lower() for item in env.get(name, "").split(",") if item.strip()]

    # A threshold that is not a number, "nan" and "inf" included, keeps the strict default:
    # no score is ever at or above either of those two, so they would hold nothing.
    try:
        threshold = float(env.get("MAX_INJECTION_SCORE", ""))
    except ValueError:
        threshold = math.nan
    if not math.isfinite(threshold):
        threshold = Policy().max_injection_score
    return Policy(
        allowed_senders=items("ALLOWED_SENDERS"),
        allowed_domains=items("ALLOWED_DOMAINS"),
        blocked_domains=items("BLOCKED_DOMAINS"),
        open_to_any_sender=env.get("OPEN_TO_ANY_SENDER") == "1",
        require_dmarc=env.get("REQUIRE_DMARC") != "0",
        max_injection_score=threshold,
    )
