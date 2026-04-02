"""
core/intent_parser.py
Classifies raw user text into one of:
  chat | gui_action | app_action | system_action | recovery_action | real_world_action

Uses keyword matching for fast, deterministic first-pass classification.
The LLM planner then refines it for complex intents.
"""
from __future__ import annotations
import re
import logging
from dataclasses import dataclass
from functools import lru_cache

log = logging.getLogger(__name__)

# Intent type constants
CHAT = "chat"
GUI = "gui_action"
APP = "app_action"
SYSTEM = "system_action"
RECOVERY = "recovery_action"
REAL_WORLD = "real_world_action"

INTENT_TYPES = [CHAT, GUI, APP, SYSTEM, RECOVERY, REAL_WORLD]


@dataclass
class Intent:
    type: str
    raw: str
    confidence: float       # 0.0 – 1.0 (rule-based is always 0.9+)
    needs_llm: bool         # True if LLM should refine further
    clarification: str = "" # Non-empty if clarification is needed from user


# Keyword sets (order matters — checked top to bottom, first match wins)
# Each keyword is a space-separated list of tokens; ALL tokens must appear
# in the text (not necessarily adjacent), allowing filler words between them.
_RULES: list[tuple[str, list[str]]] = [
    (RECOVERY,   [
        "rollback", "restore", "undo", "revert", "snapshot", "panic", "recovery",
        "boot recovery", "restore config",
    ]),
    (REAL_WORLD, [
        "order", "buy", "purchase", "pay", "pizza", "uber", "book",
        "send message", "send email", "transfer money", "checkout",
    ]),
    (SYSTEM,     [
        "install", "uninstall", "remove package", "update system", "apt", "dpkg",
        "edit config", "change setting", "restart service", "enable service",
        "disable service", "reboot", "shutdown", "mount", "chmod", "chown",
        "fix wifi", "fix bluetooth", "fix fingerprint",
        "repair wifi", "repair bluetooth", "repair fingerprint",
        "repair",
    ]),
    (APP,        [
        "open", "launch", "start", "close", "quit",
        "vs code", "vscode", "firefox", "chrome", "terminal", "vim", "nano",
        "spotify", "vlc", "calculator", "file manager",
    ]),
    (GUI,        [
        "type", "click", "press", "scroll", "drag", "select",
        "copy", "paste", "screenshot",
    ]),
]


def _matches(lower: str, keyword: str) -> bool:
    """
    Returns True if all tokens in the keyword appear as whole words in the text.
    e.g. keyword 'fix wifi' matches 'fix my wifi' and 'please fix the wifi'.
    """
    tokens = keyword.split()
    return all(re.search(rf'\b{re.escape(t)}\b', lower) for t in tokens)


def parse(text: str) -> Intent:
    lower = text.lower().strip()

    for intent_type, keywords in _RULES:
        for kw in keywords:
            if _matches(lower, kw):
                log.debug("intent_parser: '%s' → %s (keyword: '%s')", text[:60], intent_type, kw)
                return Intent(
                    type=intent_type,
                    raw=text,
                    confidence=0.9,
                    needs_llm=(intent_type in (SYSTEM, RECOVERY, REAL_WORLD)),
                )

    # Default: treat as chat; let LLM decide if more complex
    return Intent(type=CHAT, raw=text, confidence=0.7, needs_llm=True)


def needs_clarification(text: str) -> str:
    """
    Returns a clarification question if the intent is ambiguous,
    empty string otherwise.
    """
    lower = text.lower().strip()
    if re.search(r"\b(it|that|this|the thing)\b", lower) and len(lower.split()) <= 4:
        return "Could you be more specific? What exactly would you like me to do?"
    return ""
