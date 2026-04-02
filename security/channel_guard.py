"""
security/channel_guard.py
Blocks AI input to sensitive windows (auth, payment, password fields).
Validates terminal commands against a deny list.
"""
from __future__ import annotations
import logging
import re
import subprocess
from typing import Any

log = logging.getLogger("channel_guard")

# Window title / class substrings that mean "AI must not type here"
_BLOCKED_WINDOW_PATTERNS: list[re.Pattern] = [
    re.compile(r"polkit|policykit", re.I),
    re.compile(r"sudo|su\b", re.I),
    re.compile(r"password|passphrase|pin\b", re.I),
    re.compile(r"authentication required", re.I),
    re.compile(r"login|sign.?in", re.I),
    re.compile(r"gnome-keyring|kwallet|seahorse", re.I),
    re.compile(r"payment|checkout|billing|credit card", re.I),
    re.compile(r"2fa|two.factor|authenticator|otp", re.I),
]

# Terminal command patterns that are unconditionally denied
_DENIED_COMMANDS: list[re.Pattern] = [
    re.compile(r"\brm\s+-rf\s+/(?:\s|$)"),   # rm -rf / but not rm -rf /tmp
    re.compile(r"\bdd\b.*\bif=/dev/zero\b"),
    re.compile(r"\bmkfs\b"),
    re.compile(r"\bfdisk\b|\bparted\b"),
    re.compile(r"\bshred\b"),
    re.compile(r"\bchmod\s+777\s+/"),
    re.compile(r"\bcurl\b.*\|\s*bash"),
    re.compile(r"\bwget\b.*\|\s*sh"),
    re.compile(r">\s*/dev/sd[a-z]"),
    re.compile(r"\biptables\s+-F\b"),  # flush all firewall rules
]


def _active_window_title() -> str:
    """Best-effort: tries xdotool, falls back to empty string."""
    try:
        wid = subprocess.check_output(
            ["xdotool", "getactivewindow"], timeout=1, stderr=subprocess.DEVNULL
        ).decode().strip()
        return subprocess.check_output(
            ["xdotool", "getwindowname", wid], timeout=1, stderr=subprocess.DEVNULL
        ).decode().strip()
    except Exception:
        return ""


class ChannelGuard:
    def is_safe(self, action: dict[str, Any]) -> bool:
        """Returns True if it is safe for the AI to execute this action now."""
        tool = action.get("tool", "")

        # Only GUI/typing actions need window checks
        if tool in ("gui.type_text", "gui.click", "gui.open_app"):
            window = _active_window_title()
            for pat in _BLOCKED_WINDOW_PATTERNS:
                if pat.search(window):
                    log.warning("channel_guard: blocked — sensitive window '%s'", window)
                    return False

        # Terminal command deny-list
        if tool == "terminal.run_safe":
            cmd = action.get("args", {}).get("command", "")
            for pat in _DENIED_COMMANDS:
                if pat.search(cmd):
                    log.warning("channel_guard: denied command pattern '%s'", pat.pattern)
                    return False

        return True
