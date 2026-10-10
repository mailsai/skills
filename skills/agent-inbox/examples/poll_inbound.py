"""Handle inbound email by polling, for agents that cannot receive webhooks.

Run once:   MAILS_API_KEY=mk_test_... ALLOWED_SENDERS=you@example.com python3 poll_inbound.py --once
Keep going: the same command without --once. It polls every 15 seconds.

The position is saved in STATE_FILE (default ./mails-inbox-state.json), so a restart
neither repeats nor skips mail. The policy settings are listed in handle_inbound.py.
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from mailsai import Client

from handle_inbound import handle_inbound
from inbox_policy import INBOUND_EVENT_TYPES

STATE_FILE = os.environ.get("STATE_FILE", "./mails-inbox-state.json")
POLL_SECONDS = 15
# An event's `created_at` is set as it is written, but the event can be read only once that
# write is finished, so it can turn up after newer ones. Each poll starts this far before the
# newest `created_at` handled, and "handled" keeps what comes back from being handled twice.
OVERLAP = timedelta(minutes=10)


def created_at_form(moment: datetime) -> str:
    """A time in the form every `created_at` has, such as 2026-01-31T12:00:00.000Z."""
    moment = moment.astimezone(timezone.utc)
    return moment.strftime("%Y-%m-%dT%H:%M:%S.") + f"{moment.microsecond // 1000:03d}Z"


def load_state() -> Dict[str, Any]:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, encoding="utf-8") as handle:
            return json.load(handle)
    # First run: start from now.
    return {"since": created_at_form(datetime.now(timezone.utc)), "handled": []}


def save_state(state: Dict[str, Any]) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as handle:
        json.dump(state, handle)


def fetch_inbound(client: Client, since: str) -> List[Dict[str, Any]]:
    """Every inbound event created at or after `since`, oldest first."""
    found: List[Dict[str, Any]] = []
    for event_type in INBOUND_EVENT_TYPES:
        cursor = None
        while True:
            page = client.list_events(event_type=event_type, since=since, limit=100, cursor=cursor)
            found.extend(page["data"])
            cursor = page.get("next_cursor") if page.get("has_more") else None
            if not cursor:
                break
    return sorted(found, key=lambda event: event.get("created_at") or "")


def poll_once(client: Client, state: Dict[str, Any]) -> Dict[str, Any]:
    handled = list(state["handled"])
    since = state["since"]
    start = datetime.fromisoformat(state["since"].replace("Z", "+00:00")) - OVERLAP
    for event in fetch_inbound(client, created_at_form(start)):
        if event["id"] in handled:
            continue  # handled on an earlier poll and read again
        try:
            outcome = handle_inbound(event)
        except Exception as error:  # noqa: BLE001
            # Stop here. The position has not moved past this event, so the next poll tries it again.
            print(f"{event['id']} failed: {error}", file=sys.stderr)
            break
        print(f"{event['id']} {outcome['action']}: {outcome['detail']}")
        handled = (handled + [event["id"]])[-500:]
        if event.get("created_at") and event["created_at"] > since:
            since = event["created_at"]
        # Save after every event, so a crash repeats at most the one in progress.
        save_state({"since": since, "handled": handled})
    return {"since": since, "handled": handled}


def main() -> None:
    client = Client()  # reads MAILS_API_KEY
    state = load_state()
    if "--once" in sys.argv:
        poll_once(client, state)
        return
    while True:
        state = poll_once(client, state)
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
