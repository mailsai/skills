"""Send one email with an attachment, tags and metadata, then read the message back.

Run: MAILS_API_KEY=mk_test_... python3 send_with_attachment.py
"""
from __future__ import annotations

import base64
import uuid

from mailsai import Client


def main() -> None:
    client = Client()  # reads MAILS_API_KEY
    invoice = "Invoice 221\nTotal due: 48.00 USD\n"

    sent = client.send(
        to="reply@test.mails.ai",
        subject="Invoice 221",
        body_text="Your invoice is attached.",
        body_html="<p>Your invoice is attached.</p>",
        # Up to 10 files. Base64 content travels inside the request, so together the files can
        # come to about 3 MB. A larger file goes by an https `path` instead, up to 25 MB in all.
        attachments=[
            {
                "filename": "invoice-221.txt",
                "content_base64": base64.b64encode(invoice.encode("utf-8")).decode("ascii"),
                "content_type": "text/plain",
            }
        ],
        # Tags and metadata come back on the message, so you can find it later.
        tags=[{"name": "kind", "value": "invoice"}],
        metadata={"invoice_id": "221"},
        idempotency_key=f"invoice-221-{uuid.uuid4()}",
    )
    print(f"sent {sent['id']}, status {sent['status']}")

    stored = client.get_message(sent["id"])
    print(f"stored with tags {stored.get('tags')}")


if __name__ == "__main__":
    main()
