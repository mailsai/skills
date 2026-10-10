"""Verify the signature on a mails.ai webhook delivery.

Library file: import verify_signature from your webhook handler. Standard library only.

How mails.ai signs a delivery:
  header   X-Mails-Signature: t=<unix seconds>,v1=<hex digest>
  digest   HMAC-SHA256(key = signing secret, message = f"{t}.{raw_body}")
The signing secret is the whole "whsec_..." string, used as UTF-8 text.
raw_body is the request body exactly as received. Do not parse and re-serialize it first.
Every v1 in the header is checked, and the delivery passes when any of them matches.
"""
from __future__ import annotations

import hashlib
import hmac
import re
import time
from typing import List, Optional, Union

# How old a signature may be, in seconds. mails.ai's own verifier uses the same window.
DEFAULT_TOLERANCE_SECONDS = 300

_TIMESTAMP = re.compile(r"[0-9]{1,15}")
_DIGEST = re.compile(r"[0-9a-fA-F]{64}")


def verify_signature(
    raw_body: Union[bytes, str],
    signature_header: Optional[str],
    signing_secret: str,
    tolerance_seconds: int = DEFAULT_TOLERANCE_SECONDS,
    now_seconds: Optional[int] = None,
) -> bool:
    if not signature_header or not signing_secret:
        return False

    t: Optional[str] = None
    digests: List[str] = []
    for piece in signature_header.split(","):
        key, separator, value = piece.partition("=")
        if not separator:
            continue
        key, value = key.strip(), value.strip()
        if key == "t" and t is None:
            t = value
        elif key == "v1":
            digests.append(value)
    if t is None or not _TIMESTAMP.fullmatch(t):
        return False

    # An old timestamp means a captured request is being replayed. A far-future one is not ours.
    timestamp = int(t)
    now = int(time.time()) if now_seconds is None else now_seconds
    if abs(now - timestamp) > tolerance_seconds:
        return False

    body = raw_body if isinstance(raw_body, bytes) else raw_body.encode("utf-8")
    message = str(timestamp).encode("ascii") + b"." + body
    expected = hmac.new(signing_secret.encode("utf-8"), message, hashlib.sha256).digest()
    return any(
        _DIGEST.fullmatch(digest) is not None and hmac.compare_digest(expected, bytes.fromhex(digest))
        for digest in digests
    )
