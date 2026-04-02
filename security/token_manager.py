"""
security/token_manager.py
HMAC token generation and verification.
Used by input_tagger.py to stamp real user keypresses.
"""
from __future__ import annotations
import hashlib
import hmac
import os
import time
from pathlib import Path

_SECRET_PATH = Path("/var/lib/ai-agent/.hmac_secret")
_TOKEN_TTL = 2.0  # seconds — tokens older than this are rejected


def _secret() -> bytes:
    if not _SECRET_PATH.exists():
        _SECRET_PATH.parent.mkdir(parents=True, exist_ok=True)
        _SECRET_PATH.write_bytes(os.urandom(32))
        _SECRET_PATH.chmod(0o600)
    return _SECRET_PATH.read_bytes()


def stamp(payload: str) -> str:
    """Return 'timestamp:hmac' token for a payload string."""
    ts = f"{time.monotonic():.6f}"
    msg = f"{ts}:{payload}".encode()
    sig = hmac.new(_secret(), msg, hashlib.sha256).hexdigest()
    return f"{ts}:{sig}"


def verify(token: str, payload: str, max_age: float = _TOKEN_TTL) -> bool:
    """Returns True only if token is valid and fresh."""
    try:
        ts_str, sig = token.split(":", 1)
        ts = float(ts_str)
    except (ValueError, AttributeError):
        return False

    age = time.monotonic() - ts
    if age < 0 or age > max_age:
        return False

    msg = f"{ts_str}:{payload}".encode()
    expected = hmac.new(_secret(), msg, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig)
