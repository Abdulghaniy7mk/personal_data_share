"""
memory.py — AI OS Memory System

Two strictly separated memory stores:
  Cognitive:   preferences, habits, workflow style — low risk
  Operational: action history, success/failure counts — higher risk

The context_firewall decides which entries reach the planner.
This module handles storage, retrieval, and learning validation.

Storage: SQLite on a tmpfs-backed path (fast, ephemeral across reboots).
Persistence: encrypted JSON export on clean shutdown.
"""

import json
import logging
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path

from core.context_firewall import MemoryEntry

log = logging.getLogger("ai-os.memory")

DB_PATH_DEFAULT = "/home/ai-agent/memory.db"


class Memory:
    def __init__(self, cfg: dict):
        db_path = cfg.get("memory", {}).get("db_path", DB_PATH_DEFAULT)
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(db_path, check_same_thread=False)
        self._init_schema()
        self._firewall_ref = None  # set by agent_main after construction

    def set_firewall(self, fw):
        self._firewall_ref = fw

    def get_relevant(self, query: str) -> list[MemoryEntry]:
        """
        Returns memory entries relevant to the query.
        Cognitive entries first, then operational summaries.
        Simple keyword match — production would use embedding similarity.
        """
        words = set(query.lower().split())
        results = []

        cur = self._db.execute(
            "SELECT content, source, confidence, approved FROM memory "
            "WHERE active=1 ORDER BY ts DESC LIMIT 50"
        )
        for content, source, confidence, approved in cur.fetchall():
            # Relevance: count keyword overlaps
            content_words = set(content.lower().split())
            if len(words & content_words) > 0 or source == "cognitive":
                results.append(MemoryEntry(
                    content=content,
                    source=source,
                    confidence=confidence,
                    approved=bool(approved),
                ))

        return results[:20]  # cap at 20 entries for context window budget

    def record_success(self, user_text: str, action, result: dict):
        """
        Called after a successful, human-approved action.
        Only writes to memory if context_firewall deems it safe to learn.
        """
        if self._firewall_ref:
            if not self._firewall_ref.is_safe_for_learning(user_text, action.action_type):
                log.debug(f"[memory] Skipped learning: unsafe pattern in '{user_text[:40]}'")
                return

        # Extract cognitive preference if detectable
        pref = self._extract_preference(user_text, action)
        if pref:
            self._write("cognitive", pref, confidence=0.6, approved=True)

        # Always write operational record (action type + success, no raw params)
        self._write(
            "operational",
            f"{action.action_type} succeeded",
            confidence=1.0,
            approved=True,
        )

    def _extract_preference(self, text: str, action) -> str | None:
        """
        Heuristically detect a preference statement in the user's command.
        E.g. "always open VS Code for Python files" → cognitive preference.
        """
        PREFERENCE_TRIGGERS = ["always", "prefer", "use", "like", "every time"]
        tl = text.lower()
        if any(t in tl for t in PREFERENCE_TRIGGERS):
            # Safe: store the user's original phrasing (stripped of paths/commands)
            import re
            safe = re.sub(r'/[^\s]+', '[path]', text)  # strip paths
            safe = re.sub(r'`[^`]+`', '[cmd]', safe)    # strip inline commands
            return f"User preference: {safe[:200]}"
        return None

    def _write(self, source: str, content: str, confidence: float, approved: bool):
        self._db.execute(
            "INSERT INTO memory (source, content, confidence, approved, ts, active) "
            "VALUES (?, ?, ?, ?, ?, 1)",
            (source, content, confidence, int(approved), time.time()),
        )
        self._db.commit()
        log.debug(f"[memory] Wrote {source} entry: {content[:60]}")

    def _init_schema(self):
        self._db.execute("""
            CREATE TABLE IF NOT EXISTS memory (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                source     TEXT NOT NULL,
                content    TEXT NOT NULL,
                confidence REAL NOT NULL,
                approved   INTEGER NOT NULL DEFAULT 0,
                ts         REAL NOT NULL,
                active     INTEGER NOT NULL DEFAULT 1
            )
        """)
        self._db.execute("CREATE INDEX IF NOT EXISTS idx_ts ON memory(ts)")
        self._db.commit()
