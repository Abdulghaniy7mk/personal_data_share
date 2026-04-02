"""
security/supervisor.py
Rate limiter + loop detector + per-session action budget.
Gap fix #5 from Claude's review.

Limits:
  - Max 30 actions/minute
  - Max 200 actions/session
  - Loop detection: same tool × 3 in 60 seconds → halt
"""
from __future__ import annotations
import collections
import logging
import time
from threading import Lock
from typing import Any

log = logging.getLogger("supervisor")

MAX_PER_MINUTE = 30
MAX_PER_SESSION = 200
LOOP_WINDOW_SEC = 60
LOOP_THRESHOLD = 3  # same tool repeated this many times in window = loop


class Supervisor:
    def __init__(self) -> None:
        self._lock = Lock()
        self._session_count = 0
        self._minute_times: collections.deque[float] = collections.deque()
        self._recent_tools: collections.deque[tuple[float, str]] = collections.deque()
        self._halted = False
        self._halt_reason = ""

    def allow(self, action: dict[str, Any]) -> tuple[bool, str]:
        """
        Returns (True, "") if the action is allowed,
        or (False, reason) if it should be blocked.
        """
        with self._lock:
            if self._halted:
                return False, f"Supervisor halted: {self._halt_reason}"

            now = time.monotonic()
            tool = action.get("tool", "unknown")

            # ── Session budget ────────────────────────────────────────────
            self._session_count += 1
            if self._session_count > MAX_PER_SESSION:
                reason = f"Session action budget exhausted ({MAX_PER_SESSION} actions)"
                self._halt(reason)
                return False, reason

            # ── Rate limit (per minute) ───────────────────────────────────
            cutoff_1m = now - 60.0
            while self._minute_times and self._minute_times[0] < cutoff_1m:
                self._minute_times.popleft()
            self._minute_times.append(now)

            if len(self._minute_times) > MAX_PER_MINUTE:
                reason = f"Rate limit: >{MAX_PER_MINUTE} actions/minute"
                self._halt(reason)
                return False, reason

            # ── Loop detection ────────────────────────────────────────────
            cutoff_loop = now - LOOP_WINDOW_SEC
            while self._recent_tools and self._recent_tools[0][0] < cutoff_loop:
                self._recent_tools.popleft()
            self._recent_tools.append((now, tool))

            recent_same = sum(1 for _, t in self._recent_tools if t == tool)
            if recent_same > LOOP_THRESHOLD:
                reason = f"Loop detected: tool '{tool}' called {recent_same}× in {LOOP_WINDOW_SEC}s"
                self._halt(reason)
                return False, reason

            return True, ""

    def _halt(self, reason: str) -> None:
        self._halted = True
        self._halt_reason = reason
        log.warning("SUPERVISOR HALT: %s", reason)

    def resume(self) -> None:
        """Human operator manually resumes the agent."""
        with self._lock:
            self._halted = False
            self._halt_reason = ""
            self._session_count = 0
            self._minute_times.clear()
            self._recent_tools.clear()
        log.info("Supervisor: agent resumed by operator")

    @property
    def stats(self) -> dict:
        with self._lock:
            return {
                "session_count": self._session_count,
                "last_minute": len(self._minute_times),
                "halted": self._halted,
                "halt_reason": self._halt_reason,
            }
