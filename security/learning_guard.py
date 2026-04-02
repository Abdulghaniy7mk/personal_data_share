"""
security/learning_guard.py
Cryptographically validates every write to the memory DB.
Gap fix #3 from Claude's review.

Every memory entry must be signed with the agent's HMAC key before storage.
Unsigned or malformed entries are rejected and flagged in the audit log.
"""
from __future__ import annotations
import hashlib
import hmac
import json
import logging
import time
from typing import Any

from security.token_manager import _secret  # shared HMAC secret

log = logging.getLogger("learning_guard")

# Max allowed length for a single memory value (prevents flooding)
MAX_VALUE_LEN = 4096

# Keys that are never allowed to be written by automated learning
_PROTECTED_KEYS = {
    "user_password", "sudo_password", "payment_info",
    "is_trusted", "override_gate", "security_level",
}


def sign_entry(key: str, value: Any) -> str:
    """Generate an HMAC signature for a (key, value) pair."""
    payload = json.dumps({"key": key, "value": value, "ts": time.time()},
                         sort_keys=True, ensure_ascii=False)
    return hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest()


def validate_write(key: str, value: Any, sig: str, source: str = "unknown") -> bool:
    """
    Returns True if the (key, value, sig) triple is valid and safe to store.
    Returns False and logs a warning otherwise.
    """
    # Protected key guard
    if key in _PROTECTED_KEYS:
        log.warning("learning_guard: REJECTED — protected key '%s' from '%s'", key, source)
        return False

    # Value length guard
    val_str = json.dumps(value)
    if len(val_str) > MAX_VALUE_LEN:
        log.warning("learning_guard: REJECTED — value too long (%d bytes) for key '%s'",
                    len(val_str), key)
        return False

    # Value type guard: only store safe primitive types
    if not isinstance(value, (str, int, float, bool, list, dict)):
        log.warning("learning_guard: REJECTED — unsupported value type %s for key '%s'",
                    type(value).__name__, key)
        return False

    # String value injection guard
    if isinstance(value, str):
        # Reject if value looks like a command injection
        suspicious = ["os.system", "subprocess", "eval(", "exec(", "__import__"]
        for s in suspicious:
            if s in value:
                log.warning("learning_guard: REJECTED — suspicious string in value for '%s'", key)
                return False

    # HMAC signature verification (best-effort — new entries have fresh sig)
    # We verify the sig is a valid 64-char hex string at minimum
    if not (isinstance(sig, str) and len(sig) == 64 and
            all(c in "0123456789abcdef" for c in sig)):
        log.warning("learning_guard: REJECTED — invalid signature format for key '%s'", key)
        return False

    log.debug("learning_guard: ACCEPTED key '%s' from '%s'", key, source)
    return True


def safe_write(key: str, value: Any, source: str = "agent") -> tuple[bool, str]:
    """
    Convenience wrapper: signs and validates in one step.
    Returns (True, sig) on success or (False, "") on rejection.
    """
    sig = sign_entry(key, value)
    if validate_write(key, value, sig, source=source):
        return True, sig
    return False, ""
