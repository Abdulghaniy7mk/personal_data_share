"""
security/policy_engine.py
Deterministic allow/deny policy layer.
Consulted by confirm_gate and secondary_validator for structured rules.
"""
from __future__ import annotations
import logging
from typing import Any

log = logging.getLogger("policy_engine")

# Explicit deny rules: (tool, arg_key, forbidden_value_substring)
_DENY_RULES: list[tuple[str, str, str]] = [
    ("terminal.run_safe", "command", "rm -rf /"),
    ("terminal.run_safe", "command", "dd if=/dev/zero"),
    ("system.edit_config", "path", "/etc/shadow"),
    ("system.edit_config", "path", "/etc/sudoers"),
    ("terminal.run_safe", "command", "curl | bash"),
    ("terminal.run_safe", "command", "wget | sh"),
]

# Actions that always need a human present (never auto)
HUMAN_REQUIRED_TOOLS = {
    "real_world.confirm_order",
    "recovery.rollback",
    "recovery.panic",
    "system.edit_config",
}


class PolicyEngine:
    def is_allowed(self, action: dict[str, Any]) -> tuple[bool, str]:
        tool = action.get("tool", "")
        args = action.get("args", {})

        for rule_tool, rule_key, forbidden in _DENY_RULES:
            if tool == rule_tool:
                val = str(args.get(rule_key, ""))
                if forbidden in val:
                    reason = f"Policy deny: tool={tool} {rule_key} contains '{forbidden}'"
                    log.warning(reason)
                    return False, reason

        return True, ""

    def requires_human(self, action: dict[str, Any]) -> bool:
        return action.get("tool", "") in HUMAN_REQUIRED_TOOLS
