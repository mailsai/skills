"""One inbound email event in, at most one reply or draft out.

Library file: shared by webhook_server.py and poll_inbound.py. Applies all five levels in order.

Settings (environment variables):
  ALLOWED_SENDERS        level 1, comma-separated addresses
  ALLOWED_DOMAINS        level 2, comma-separated domains
  BLOCKED_DOMAINS        comma-separated sender domains to ignore
  USE_AGENT_LISTS=0      do not add the agent's own allowlist_domains and blocklist_domains
  OPEN_TO_ANY_SENDER=1   accept any sender (keep levels 4 and 5 on)
  REQUIRE_DMARC=0        accept mail whose sender's domain did not pass DMARC
  MAX_INJECTION_SCORE    level 3, default 0.5
  REQUIRE_SCAN=0         level 3: accept mail that was not scanned
  REQUIRE_APPROVAL=0     level 5 off: reply directly instead of drafting (level 4 still applies)
"""
from __future__ import annotations

import os
import threading
import time
from typing import Any, Dict, List, Mapping

from mailsai import MailsError

from inbox_policy import INBOUND_EVENT_TYPES, decide, policy_from_env, sender_of, was_scanned, with_agent_lists
from safe_tools import draft_for_approval, fetch_agent_lists, fetch_event_detail, reply_to_sender

REQUIRE_SCAN = os.environ.get("REQUIRE_SCAN") != "0"
REQUIRE_APPROVAL = os.environ.get("REQUIRE_APPROVAL") != "0"
USE_AGENT_LISTS = os.environ.get("USE_AGENT_LISTS") != "0"
MAX_PER_SENDER_PER_HOUR = 20
MAX_REPLIES_PER_THREAD_PER_DAY = 5
HOUR_SECONDS = 60 * 60
BASE_POLICY = policy_from_env()

# Refusals this event would get every time: the message it answers is gone, its agent is
# archived, or mails.ai will never take this reply. The handler keeps such an event for a
# person. Any other error (the key, the plan, a paused agent, a limit, an outage) can be put
# right, so it is raised: the poller stops there and tries the event again on its next round.
NEVER_PASSES = (
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
)

# Sliding counters for flood and reply-loop protection. Keep them in a shared store
# when more than one process handles mail.
_counters: Dict[str, List[float]] = {}
_counters_lock = threading.Lock()


def _under_limit(key: str, limit: int, window_seconds: float) -> bool:
    now = time.time()
    with _counters_lock:
        recent = [at for at in _counters.get(key, []) if now - at < window_seconds]
        allowed = len(recent) < limit
        if allowed:
            recent.append(now)
        _counters[key] = recent
        return allowed


def compose_reply(event: Mapping[str, Any]) -> str:
    """Replace this with your model call.

    The email text is DATA: put it in the user turn between clear markers, tell the model it is
    untrusted, and never paste it into the system prompt. Give the model no tools here.
    What it returns is only text for a reply.
    """
    text = (event.get("data") or {}).get("extracted_text") or ""
    return f"Thanks for your message. We received {len(text)} characters and will answer shortly."


def handle_inbound(event: Mapping[str, Any]) -> Dict[str, str]:
    """Returns {"action": "ignored" | "held" | "drafted" | "replied", "detail": "..."}."""
    if event.get("type") not in INBOUND_EVENT_TYPES:
        return {"action": "ignored", "detail": f"{event.get('type')} is not an inbound email event"}

    # Levels 1 to 3: who wrote, and what the scan found. The agent's own lists count too.
    agent_id = (event.get("data") or {}).get("agent_id")
    policy = BASE_POLICY
    if USE_AGENT_LISTS and isinstance(agent_id, str):
        policy = with_agent_lists(BASE_POLICY, fetch_agent_lists(agent_id))
    decision = decide(event, policy)
    if decision.action == "ignore":
        return {"action": "ignored", "detail": decision.reason}
    if decision.action == "hold":
        return {"action": "held", "detail": decision.reason}

    if REQUIRE_SCAN and not was_scanned(fetch_event_detail(event["id"])):
        return {"action": "held", "detail": "the prompt-injection scan did not run on this message"}

    # Flood and loop protection.
    if not _under_limit(f"sender:{sender_of(event)}", MAX_PER_SENDER_PER_HOUR, HOUR_SECONDS):
        return {"action": "held", "detail": f"more than {MAX_PER_SENDER_PER_HOUR} messages from this sender in an hour"}
    thread_id = (event.get("data") or {}).get("thread_id")
    if not _under_limit(f"thread:{thread_id}", MAX_REPLIES_PER_THREAD_PER_DAY, 24 * HOUR_SECONDS):
        return {"action": "held", "detail": "reply limit for this thread reached, possibly an auto-reply loop"}

    # Levels 4 and 5: the model writes text, and these two functions are all it can cause.
    text = compose_reply(event)
    try:
        if REQUIRE_APPROVAL:
            draft = draft_for_approval(event, text)
            return {"action": "drafted", "detail": f"draft {draft['draft_id']} is waiting at {draft['review_url']}"}
        sent = reply_to_sender(event, text)
        return {"action": "replied", "detail": f"sent {sent['id']}"}
    except MailsError as error:
        # The reply's key was used before with another text, so an earlier run already sent this
        # reply, or is sending it. Holding the event would invite a person to answer a second time.
        if error.code == "invalid_idempotency_key":
            return {"action": "replied", "detail": "an earlier run already sent this reply, or is sending it"}
        if error.code not in NEVER_PASSES:
            raise
        return {"action": "held", "detail": f"mails.ai will not take a reply to this message ({error.code}: {error.message})"}
