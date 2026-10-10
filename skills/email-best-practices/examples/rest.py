"""Call any mails.ai endpoint that answers JSON, where the Python SDK is not installed.

Library file. Standard library only. Reads MAILS_API_KEY, and MAILS_BASE_URL if it is set.

    from rest import call
    thread = call("PATCH", "/v1/threads/thrd_123", {"status": "closed"})

It does not retry. Wrap it yourself if you need retries (see references/errors-and-retries.md).
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Dict, Optional


class ApiError(Exception):
    """A non-2xx answer. `code` is the stable error code, for example "insufficient_scope".

    `retry_after` is the Retry-After header in seconds, or None when the API sent none.
    `replayed` is True when the answer is one mails.ai stored for this Idempotency-Key
    (the header `Idempotent-Replay: true`): the same key will only get it again.
    """

    def __init__(
        self,
        status: int,
        code: str,
        message: str,
        request_id: Optional[str],
        retry_after: Optional[float] = None,
        replayed: bool = False,
    ):
        super().__init__(f"{status} {code}: {message}")
        self.status = status
        self.code = code
        self.message = message
        self.request_id = request_id
        self.retry_after = retry_after
        self.replayed = replayed


def call(
    method: str,
    path: str,
    body: Optional[Dict[str, Any]] = None,
    idempotency_key: Optional[str] = None,
) -> Any:
    base_url = os.environ.get("MAILS_BASE_URL", "https://api.mails.ai").rstrip("/")
    headers = {
        "Authorization": f"Bearer {os.environ['MAILS_API_KEY']}",
        "Content-Type": "application/json",
    }
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(f"{base_url}{path}", data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            text = response.read().decode("utf-8")
            return json.loads(text) if text else None
    except urllib.error.HTTPError as error:
        try:
            detail = json.loads(error.read().decode("utf-8")).get("error", {})
        except ValueError:
            detail = {}
        try:
            retry_after: Optional[float] = float(error.headers.get("Retry-After", ""))
        except ValueError:
            retry_after = None
        raise ApiError(
            error.code,
            detail.get("code", "unknown"),
            detail.get("message", str(error.reason)),
            error.headers.get("X-Request-Id"),
            retry_after,
            error.headers.get("Idempotent-Replay") == "true",
        ) from None
