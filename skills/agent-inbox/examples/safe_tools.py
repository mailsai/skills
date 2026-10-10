"""The only ways the inbound handler sends mail. Levels 4 and 5 of the agent-inbox skill.

Library file. If your model calls tools, give it one of these two and nothing else that can send.

  Level 4  reply_to_sender      a reply that can only reach the person who wrote
  Level 5  draft_for_approval   a draft that a person sends from the dashboard

The two reads at the end are for the handler, not for the model.
"""
from __future__ import annotations

import threading
import time
from functools import lru_cache
from typing import Any, Dict, List, Mapping, Tuple

from mailsai import Client


# A subject may have 998 characters (POST /v1/drafts), and received mail can carry a longer one.
MAX_SUBJECT = 998


@lru_cache(maxsize=1)
def _client() -> Client:
    return Client()  # reads MAILS_API_KEY


def _field(event: Mapping[str, Any], name: str) -> str:
    value = (event.get("data") or {}).get(name)
    if not isinstance(value, str) or value == "":
        raise ValueError(f"event {event.get('id')} has no data.{name}")
    return value


def _sender_address(event: Mapping[str, Any]) -> str:
    sender = (event.get("data") or {}).get("from")
    address = sender.get("address") if isinstance(sender, dict) else None
    if not isinstance(address, str) or "@" not in address:
        raise ValueError(f"event {event.get('id')} has no sender address")
    return address


def reply_to_sender(event: Mapping[str, Any], text: str) -> Dict[str, Any]:
    """Level 4. Reply to the person who wrote, in the same thread.

    mails.ai takes the recipient from the received message, so the model cannot choose who gets the mail.
    This function takes no cc or bcc on purpose: those would let a hijacked model copy someone in.
    The Idempotency-Key is built from the event id, so handling the same event twice sends one reply.
    """
    return _client().reply(
        _field(event, "source_message_id"),
        body_text=text,
        idempotency_key=f"reply-{event['id']}",
    )


def draft_for_approval(event: Mapping[str, Any], text: str) -> Dict[str, str]:
    """Level 5. Write the reply as a draft and stop. Nothing is sent.

    A person opens the returned URL, reads the draft and presses Send (or deletes it).
    """
    subject = (event.get("data") or {}).get("subject") or "your message"
    draft = _client().create_draft(
        agent=_field(event, "agent_id"),
        to=_sender_address(event),
        subject=(subject if subject.lower().startswith("re:") else f"Re: {subject}")[:MAX_SUBJECT],
        body_text=text,
        in_reply_to_message_id=_field(event, "source_message_id"),
    )
    return {"draft_id": draft["id"], "review_url": f"https://app.mails.ai/drafts/{draft['id']}"}


AGENT_LISTS_TTL_SECONDS = 60
_agent_lists: Dict[str, Tuple[float, Dict[str, List[str]]]] = {}
_agent_lists_lock = threading.Lock()


def fetch_agent_lists(agent_id: str) -> Dict[str, List[str]]:
    """The agent's allowlist_domains and blocklist_domains, read at most once a minute per agent."""
    with _agent_lists_lock:
        cached = _agent_lists.get(agent_id)
    if cached and time.time() - cached[0] < AGENT_LISTS_TTL_SECONDS:
        return cached[1]
    agent = _client().get_agent(agent_id)
    lists = {
        "allowlist_domains": agent.get("allowlist_domains") or [],
        "blocklist_domains": agent.get("blocklist_domains") or [],
    }
    with _agent_lists_lock:
        _agent_lists[agent_id] = (time.time(), lists)
    return lists


def fetch_event_detail(event_id: str) -> Dict[str, Any]:
    """The event as GET /v1/events/{id} returns it, which adds injection_categories."""
    return _client().get_event(event_id)
