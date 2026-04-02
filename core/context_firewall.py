"""
context_firewall.py — Context Firewall (Gap 4 Fix)

Problem: Even if memory storage is safe, combining cognitive memory
(habits, preferences) with operational memory (commands, paths) at
inference time lets the AI plan unsafe actions from innocent-looking
preferences.

Example attack: adversary causes user to do many "rm -rf node_modules"
actions → AI learns "user prefers rm -rf for cleanup" → planner generates
rm -rf for unrelated cleanup tasks.

Fix: Strip command-like strings, file paths, and system-level patterns
from cognitive memory before injecting it into the planning context.
Only preferences, style, and workflow patterns are allowed through.
"""

import re
import logging
from dataclasses import dataclass

log = logging.getLogger("ai-os.context-firewall")


# ── Pattern classifiers ────────────────────────────────────────────────────────

# These patterns in a memory entry mark it as operational (not safe for planning context)
COMMAND_PATTERNS = [
    re.compile(r'\b(rm|mv|cp|chmod|chown|sudo|apt|pip|curl|wget|bash|sh|python|node)\b'),
    re.compile(r'[|&;`$]'),              # shell metacharacters
    re.compile(r'/[a-z]{2,}(/[^\s]+)+'), # absolute paths like /etc/fstab
    re.compile(r'\.\./'),               # path traversal
    re.compile(r'\brm\s+-'),            # rm flags
    re.compile(r'\bsystemctl\b'),
    re.compile(r'\bkill\b|\bpkill\b'),
    re.compile(r'\bdd\s+if='),
    re.compile(r'https?://\S+'),        # URLs — not preferences
]

# Allowed content — these are what cognitive memory SHOULD contain
PREFERENCE_INDICATORS = [
    "prefer", "like", "always", "usually", "style", "format",
    "language", "tone", "theme", "color", "font", "editor",
    "workflow", "habit", "shortcut", "alias",
]

# Hard block — these strings never enter the planning context regardless of source
HARD_BLOCK_STRINGS = [
    "ignore previous", "ignore all", "disregard", "forget instructions",
    "new instructions:", "system:", "assistant:", "you are now",
    "override", "jailbreak",
]


@dataclass
class MemoryEntry:
    content:    str
    source:     str      # "cognitive" | "operational"
    confidence: float    # 0.0–1.0
    approved:   bool     # was this from a user-approved action?


class ContextFirewall:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self._blocked_count = 0

    def filter_for_planning(self, entries: list[MemoryEntry]) -> list[MemoryEntry]:
        """
        Returns only entries safe to inject into the AI planning context.
        Operational entries are summarized (action counts, not raw commands).
        """
        safe = []
        for entry in entries:
            result = self._classify(entry)
            if result == "block":
                self._blocked_count += 1
                log.debug(f"[firewall] BLOCKED entry: {entry.content[:60]}")
            elif result == "summarize":
                # Include a safe summary, not the raw operational content
                safe.append(MemoryEntry(
                    content=self._summarize_operational(entry),
                    source="cognitive_summary",
                    confidence=entry.confidence * 0.7,
                    approved=entry.approved,
                ))
            else:  # "allow"
                safe.append(entry)

        log.debug(f"[firewall] {len(entries)} entries → {len(safe)} safe ({self._blocked_count} total blocked)")
        return safe

    def filter_external_content(self, text: str) -> str:
        """
        Strip prompt injection attempts from text the AI is about to READ
        (web pages, PDF content, file contents).
        Called before feeding external content to the LLM.
        """
        for pattern in HARD_BLOCK_STRINGS:
            if pattern.lower() in text.lower():
                log.warning(f"[firewall] Injection attempt in external content: '{pattern}'")
                # Replace the injection with a visible marker — don't silently drop
                text = re.sub(
                    re.escape(pattern), f"[FILTERED:{pattern[:20]}]",
                    text, flags=re.IGNORECASE
                )
        # Truncate extremely long inputs (>50KB) — reduces attack surface
        if len(text) > 50_000:
            text = text[:50_000] + "\n[Content truncated by context firewall]"
        return text

    def is_safe_for_learning(self, text: str, action_type: str) -> bool:
        """
        Called by memory.record_success — returns False if learning this
        action would create a dangerous preference.
        """
        # Never learn from command-like strings
        if any(p.search(text) for p in COMMAND_PATTERNS):
            return False
        # Never learn bulk destructive operations
        dangerous_actions = {"run_command", "install_package", "delete_file", "system_config_change"}
        if action_type in dangerous_actions:
            return False
        return True

    # ── Internal ─────────────────────────────────────────────────────────────

    def _classify(self, entry: MemoryEntry) -> str:
        text = entry.content

        # Hard block — injection strings, even in "approved" memory
        if any(s.lower() in text.lower() for s in HARD_BLOCK_STRINGS):
            return "block"

        # Operational memory entries: only include safe summaries
        if entry.source == "operational":
            return "summarize"

        # Cognitive entries with command patterns: block
        if any(p.search(text) for p in COMMAND_PATTERNS):
            log.warning(f"[firewall] Cognitive entry has command pattern: {text[:60]}")
            return "block"

        # Unapproved cognitive entries: extra suspicion
        if not entry.approved and entry.confidence < 0.8:
            return "block"

        return "allow"

    def _summarize_operational(self, entry: MemoryEntry) -> str:
        """
        Convert an operational memory entry to a safe cognitive summary.
        'rm -rf node_modules ran 12 times in ~/project' becomes
        'User frequently cleans build artifacts in project directories'
        """
        # In production this calls a lightweight summarizer model
        # For now: return a generic pattern description
        return f"User has established a workflow pattern involving {entry.source} operations."
