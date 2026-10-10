"""Receive mails.ai webhooks and answer inbound email safely.

Run: MAILS_API_KEY=mk_test_... MAILS_WEBHOOK_SECRET=whsec_... ALLOWED_SENDERS=you@example.com python3 webhook_server.py

MAILS_WEBHOOK_SECRET is the signing secret that POST /v1/webhooks returns once.
PORT defaults to 8787. The policy settings are listed in handle_inbound.py.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict

from handle_inbound import handle_inbound
from verify_signature import verify_signature

SECRET = os.environ.get("MAILS_WEBHOOK_SECRET", "")
PORT = int(os.environ.get("PORT", "8787"))
MAX_BODY_BYTES = 5_000_000
SEEN_TTL_SECONDS = 24 * 60 * 60

# Event ids already handled. In production keep these in a database with a unique index,
# because this dict is empty again after a restart.
_seen: Dict[str, float] = {}
_seen_lock = threading.Lock()


def _first_time(event_id: str) -> bool:
    now = time.time()
    with _seen_lock:
        for known, at in list(_seen.items()):
            if now - at > SEEN_TTL_SECONDS:
                del _seen[known]
        if event_id in _seen:
            return False
        _seen[event_id] = now
        return True


def _work(event: Dict[str, Any]) -> None:
    try:
        outcome = handle_inbound(event)
        print(f"{event['id']} {outcome['action']}: {outcome['detail']}", flush=True)
    except Exception as error:  # noqa: BLE001
        with _seen_lock:
            _seen.pop(event["id"], None)  # let a redelivery try again: POST /v1/events/{id}/redeliver
        print(f"{event['id']} failed: {error}", file=sys.stderr, flush=True)


class Handler(BaseHTTPRequestHandler):
    def _answer(self, status: int, body: str) -> None:
        payload = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/webhooks/mails":
            return self._answer(404, "not found")
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return self._answer(400, "bad content length")
        if length > MAX_BODY_BYTES:
            return self._answer(413, "body too large")
        raw_body = self.rfile.read(length)

        # 1. Signature first. Nothing in the body is trusted before this passes.
        if not verify_signature(raw_body, self.headers.get("X-Mails-Signature"), SECRET):
            return self._answer(401, "bad signature")

        # 2. Parse only after verifying. Take the event id from the signed body, not from a header.
        try:
            event = json.loads(raw_body)
        except ValueError:
            return self._answer(400, "not an event")
        if (
            not isinstance(event, dict)
            or not isinstance(event.get("id"), str)
            or not isinstance(event.get("type"), str)
            or not isinstance(event.get("data"), dict)
        ):
            return self._answer(400, "not an event")

        # 3. Each event is handled once, however many times it is delivered.
        if not _first_time(event["id"]):
            return self._answer(200, "duplicate")

        # 4. Answer before doing the work. mails.ai waits 5 seconds, then counts the attempt as failed.
        #    In production, save the event to a queue or table here and handle it from a worker,
        #    so a crash between the answer and the work does not lose the message.
        self._answer(200, "ok")
        threading.Thread(target=_work, args=(event,), daemon=True).start()

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        return  # keep the output to the outcome lines


if __name__ == "__main__":
    if not SECRET:
        sys.exit("Set MAILS_WEBHOOK_SECRET to the signing secret of your webhook.")
    server = ThreadingHTTPServer(("", PORT), Handler)
    print(f"listening on http://localhost:{PORT}/webhooks/mails", flush=True)
    server.serve_forever()
