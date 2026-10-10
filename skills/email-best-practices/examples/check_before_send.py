"""Check an address and your sending health before you send, and handle each refusal.

Run: MAILS_API_KEY=mk_test_... python3 check_before_send.py someone@example.com [agent-name]
"""
from __future__ import annotations

import sys
import uuid

from mailsai import Client, MailsError


def main() -> None:
    client = Client()  # reads MAILS_API_KEY
    recipient = sys.argv[1] if len(sys.argv) > 1 else "reply@test.mails.ai"

    # 1. Is the address suppressed? A hard bounce, a spam complaint or an unsubscribe puts it there.
    suppression = client.check_suppression(recipient)
    if suppression.get("suppressed"):
        print(f"not sending: {recipient} is suppressed ({suppression.get('type')}, since {suppression.get('since')})")
        return

    # 2. How healthy is the sending? An agent is paused above 5% bounces or 0.3% complaints.
    #    With an agent name you get that agent's 30-day counts. Without one, the workspace score.
    agent = sys.argv[2] if len(sys.argv) > 2 else None
    health = client.get_reputation(agent_id=agent)
    sends = health.get("send_count_30d") or 0
    if sends > 0:
        bounce_rate = (health.get("bounce_count_30d") or 0) / sends
        complaint_rate = (health.get("complaint_count_30d") or 0) / sends
        print(f"30 days: {sends} sends, {bounce_rate * 100:.2f}% bounced, {complaint_rate * 100:.2f}% complaints")
    else:
        print(f"reputation {health.get('reputation')} (0 to 1)")

    # 3. Send, and handle the refusals that a retry will not fix.
    try:
        sent = client.send(
            agent,
            to=recipient,
            subject="Your receipt for order 1042",
            body_text="Thanks for your order. Your receipt is below.\n\nOrder 1042: 48.00 USD",
            idempotency_key=f"receipt-1042-{uuid.uuid4()}",
        )
    except MailsError as error:
        if error.code == "recipient_suppressed":
            print("refused: the address is suppressed. Do not retry.")
        elif error.code == "cold_email_prohibited":
            print("refused: the message reads as cold outreach. Rewrite it or appeal. Do not retry as is.")
        elif error.code == "agent_paused":
            print("refused: the agent is paused, usually for bounces or complaints. Fix the list first.")
        else:
            raise
        return

    warning = sent.get("classifier_warning")
    if warning:
        # Test keys only: this exact message would be refused on a live key.
        print(f"would be refused on a live key: {warning['reason']}")
    else:
        print(f"sent {sent['id']}")


if __name__ == "__main__":
    main()
