"""
security/secondary_validator.py
INDEPENDENT rule-based validator for high-risk actions.
Gap fix #1 from Claude's review.

Does NOT use the LLM. Pure deterministic rules.
Runs AFTER the planner but BEFORE the confirmation gate.
"""
from __future__ import annotations
import logging
import re
from typing import Any

log = logging.getLogger("secondary_validator")

# Maps tool names to their minimum allowed risk score.
# If the planner under-scored a dangerous tool, we catch it here.
_TOOL_MIN_RISK: dict[str, int] = {
    "terminal.apt_install": 5,
    "terminal.apt_remove": 5,
    "terminal.run_safe": 4,
    "system.edit_config": 6,
    "system.restart_service": 5,
    "recovery.rollback": 7,
    "recovery.panic": 8,
    "real_world.browser_action": 6,
    "real_world.confirm_order": 9,
}

# Arg value patterns that are never acceptable regardless of risk score
_FORBIDDEN_ARG_PATTERNS: list[re.Pattern] = [
    re.compile(r"\brm\s+-rf\s+/"),
    re.compile(r"\bdd\b.*of=/dev/sd"),
    re.compile(r"/etc/shadow"),
    re.compile(r"/etc/sudoers"),
    re.compile(r"base64\s*-d"),
    re.compile(r"\|\s*bash"),
    re.compile(r"\|\s*sh\b"),
]

# Tools that always require rollback to be defined
_ROLLBACK_REQUIRED_TOOLS = {
    "terminal.apt_install", "terminal.apt_remove",
    "system.edit_config",
    "recovery.rollback",
}


class SecondaryValidator:
    def check(self, action: dict[str, Any]) -> str:
        """
        Returns empty string if the action passes all checks.
        Returns a human-readable veto reason string if it fails.
        """
        tool = action.get("tool", "")
        risk = int(action.get("risk_score", 0))
        args = action.get("args", {})

        # ── Risk score floor ──────────────────────────────────────────────
        min_risk = _TOOL_MIN_RISK.get(tool)
        if min_risk is not None and risk < min_risk:
            reason = (
                f"Validator: tool '{tool}' has risk_score={risk} "
                f"but minimum required is {min_risk}. Planner may have under-scored."
            )
            log.warning(reason)
            return reason

        # ── Forbidden argument patterns ───────────────────────────────────
        args_str = str(args)
        for pat in _FORBIDDEN_ARG_PATTERNS:
            if pat.search(args_str):
                reason = f"Validator: forbidden pattern '{pat.pattern}' found in args."
                log.warning(reason)
                return reason

        # ── Rollback required ─────────────────────────────────────────────
        if tool in _ROLLBACK_REQUIRED_TOOLS and not action.get("rollback"):
            reason = f"Validator: tool '{tool}' requires a rollback path but none was provided."
            log.warning(reason)
            return reason

        # ── Snapshot required for high-risk ───────────────────────────────
        if risk >= 5 and not action.get("snapshot_before"):
            reason = f"Validator: risk_score={risk} requires snapshot_before=true."
            log.warning(reason)
            return reason

        return ""  # All checks passed
