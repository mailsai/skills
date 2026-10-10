"""List an agent's conversations, read the newest one, and close it.

Run: MAILS_API_KEY=mk_test_... python3 threads.py [agent-name]

Closing a thread needs a key with the `manage` scope. Reading needs `read`.
"""
from __future__ import annotations

import sys

from mailsai import Client, MailsError


def main() -> None:
    client = Client()  # reads MAILS_API_KEY

    # Threads come newest first, without trash unless you pass `folder`. `agent_id` takes an
    # agent's name or its agt_ id. Leave it out to list every agent's threads; a key tied to
    # one agent lists only its own.
    agent = sys.argv[1] if len(sys.argv) > 1 else None
    page = client.list_threads(agent_id=agent, status="open", limit=10)
    if not page["data"]:
        print("no open threads")
        return
    for thread in page["data"]:
        print(f"{thread['id']}  {thread['message_count']} messages  {thread.get('subject') or '(no subject)'}")

    # One thread with every message in it, oldest first, both directions.
    thread = client.get_thread(page["data"][0]["id"])
    for message in thread["messages"]:
        who = f"from {message['from']}" if message["direction"] == "inbound" else f"to {', '.join(message['to'])}"
        print(f"  {message['direction']} {who}: {message['snippet']}")

    try:
        closed = client.update_thread(thread["id"], status="closed", labels=["answered"])
        print(f"{closed['id']} is now {closed['status']}")
    except MailsError as error:
        if error.code == "insufficient_scope":
            print("this key cannot change threads: it needs the manage scope")
            return
        raise


if __name__ == "__main__":
    main()
