"""
recovery/recovery_core/mini_planner.py
Minimal, IMMUTABLE, read-only recovery planner.
Gap fix #2 from Claude's review.

This is used ONLY when the main AI brain fails.
It cannot be modified by the main OS. It has no LLM dependency.
It uses a fixed decision table only.
"""
from __future__ import annotations
import logging

log = logging.getLogger("mini_planner")

# Fixed recovery decision table — no LLM, no external calls
_RECOVERY_TABLE: dict[str, dict] = {
    "fix_boot": {
        "steps": [
            "Boot from live USB",
            "Mount Btrfs subvolumes",
            "Run: snapper -c ai-os list",
            "Rollback: snapper -c ai-os undochange <N>..0",
        ],
        "risk": "high",
        "human_required": True,
    },
    "fix_config": {
        "steps": [
            "Identify last good snapshot: snapper -c ai-os list",
            "Compare config: snapper -c ai-os diff <N> /opt/ai-os/config/",
            "Restore config: snapper -c ai-os undochange <N>..0 /opt/ai-os/config/",
            "Restart service: systemctl restart ai-agent",
        ],
        "risk": "medium",
        "human_required": False,
    },
    "fix_model_cache": {
        "steps": [
            "Stop ollama: systemctl stop ollama",
            "Clear cache: rm -rf ~/.ollama/models",
            "Re-pull model: ollama pull phi3:mini",
            "Restart: systemctl restart ollama ai-agent",
        ],
        "risk": "low",
        "human_required": False,
    },
    "reset_ai_user": {
        "steps": [
            "Stop all AI services: systemctl stop ai-agent ai-ui-server",
            "Reset home: rm -rf /var/lib/ai-agent/* (keeps .hmac_secret)",
            "Redeploy: bash /opt/ai-os/install/04_deploy.sh",
            "Verify: bash /opt/ai-os/install/05_test.sh",
        ],
        "risk": "high",
        "human_required": True,
    },
}


def diagnose(symptom: str) -> dict:
    """
    Given a symptom string, return the best recovery plan from the fixed table.
    Never calls an LLM. Never makes network requests.
    """
    symptom = symptom.lower()

    if any(w in symptom for w in ("boot", "grub", "initrd", "kernel")):
        key = "fix_boot"
    elif any(w in symptom for w in ("model", "ollama", "cache", "llm")):
        key = "fix_model_cache"
    elif any(w in symptom for w in ("config", "yaml", "settings")):
        key = "fix_config"
    elif any(w in symptom for w in ("agent", "reset", "corrupt", "broken")):
        key = "reset_ai_user"
    else:
        return {
            "plan": "fix_config",
            "steps": _RECOVERY_TABLE["fix_config"]["steps"],
            "note": "No exact match. Defaulting to config restore. Check logs manually.",
            "human_required": False,
        }

    plan = _RECOVERY_TABLE[key]
    log.info("mini_planner: diagnosis=%s risk=%s", key, plan["risk"])
    return {
        "plan": key,
        "steps": plan["steps"],
        "risk": plan["risk"],
        "human_required": plan["human_required"],
    }
