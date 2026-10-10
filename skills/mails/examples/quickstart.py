"""Send an email as an agent, wait for the reply, and answer it in the same thread.

Run: MAILS_API_KEY=mk_test_... python3 quickstart.py

Uses reply@test.mails.ai, the address that answers by itself. No real person gets mail.
"""
from __future__ import annotations

import sys
import time
import uuid
from typing import Any, Dict

from mailsai import Client, MailsError


def wait_for_reply(client: Client, sent_id: str, since: str) -> Dict[str, Any]:
    """Poll the event list until the reply to `sent_id` shows up."""
    for _ in range(30):
        page = client.list_events(event_type="reply.received", since=since, limit=25)
        for event in page["data"]:
            if event["data"].get("thread_root_message_id") == sent_id:
                return event
        time.sleep(2)
    raise TimeoutError("no reply after 60 seconds")


def main() -> None:
    client = Client()  # reads MAILS_API_KEY

    # 1. Check the key, and see whether it is a test key or a live key.
    me = client.me()
    print(f"workspace {(me.get('workspace') or {}).get('slug')}, {me['api_key']['mode']} key")

    # 2. Send. With no `agent`, the workspace's only agent sends, or one is created if the
    #    key holds `manage` (a key made in the dashboard does).
    #    (A workspace with several agents must pass agent="<name>".)
    #    One idempotency key per message, so a retry of this call can never send it twice.
    sent = client.send(
        to="reply@test.mails.ai",
        subject="Order 1042 has shipped",
        body_text="Your order is on its way. Reply to this email if anything looks wrong.",
        idempotency_key=f"order-1042-shipped-{uuid.uuid4()}",
    )
    print(f"sent {sent['id']} as {sent.get('from')}, thread {sent.get('thread_id')}")

    # 3. Wait for the reply. `since` takes the timestamp of the send, exactly as the API returned it.
    reply = wait_for_reply(client, sent["id"], sent["created_at"])
    print(f"reply from {reply['data'].get('from')}: {reply['data'].get('extracted_text')}")
    print(f"injection score {reply.get('injection_score')}, quarantined {reply.get('quarantined')}")

    # 4. Answer in the same thread. Only with a test key, where it is free: with a live key the
    #    answer would count as one more send on your usage.
    received_id = reply["data"].get("source_message_id")
    if me["api_key"]["mode"] == "test" and isinstance(received_id, str):
        answer = client.reply(received_id, body_text="Thanks, noted. Nothing else is needed.")
        print(f"answered with {answer['id']} in thread {answer.get('thread_id')}")


if __name__ == "__main__":
    try:
        main()
    except MailsError as error:
        sys.exit(f"{error.status} {error.code}: {error.message} (request {error.request_id})")
