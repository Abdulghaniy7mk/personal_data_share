"""
security/audit_log.py
Merkle-chained tamper-evident event log.
Every entry hashes the previous entry's hash.
Stored in SQLite at /var/log/ai-os/audit.db
"""
from __future__ import annotations
import hashlib
import json
import logging
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

log = logging.getLogger("audit_log")
DB_PATH = Path("/var/log/ai-os/audit.db")


class AuditLog:
    def __init__(self) -> None:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        self._init()
        self._last_hash = self._get_last_hash()

    def _init(self) -> None:
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id        TEXT PRIMARY KEY,
                ts        REAL NOT NULL,
                event     TEXT NOT NULL,
                payload   TEXT NOT NULL,
                prev_hash TEXT NOT NULL,
                hash      TEXT NOT NULL
            )
        """)
        self._conn.commit()

    def _get_last_hash(self) -> str:
        row = self._conn.execute(
            "SELECT hash FROM events ORDER BY ts DESC LIMIT 1"
        ).fetchone()
        return row[0] if row else "genesis"

    def log(self, event: str, payload: Any) -> str:
        """Append an event. Returns the entry's hash."""
        entry_id = str(uuid.uuid4())
        ts = time.time()
        payload_str = json.dumps(payload, default=str)

        raw = f"{entry_id}:{ts}:{event}:{payload_str}:{self._last_hash}"
        entry_hash = hashlib.sha256(raw.encode()).hexdigest()

        self._conn.execute(
            "INSERT INTO events VALUES(?,?,?,?,?,?)",
            (entry_id, ts, event, payload_str, self._last_hash, entry_hash)
        )
        self._conn.commit()
        self._last_hash = entry_hash
        return entry_hash

    def verify_chain(self) -> tuple[bool, str]:
        """Verify the entire chain. Returns (True, '') or (False, reason)."""
        rows = self._conn.execute(
            "SELECT * FROM events ORDER BY ts ASC"
        ).fetchall()

        prev = "genesis"
        for row in rows:
            entry_id, ts, event, payload, prev_hash, stored_hash = row
            if prev_hash != prev:
                return False, f"Chain broken at entry {entry_id}: prev_hash mismatch"
            raw = f"{entry_id}:{ts}:{event}:{payload}:{prev_hash}"
            computed = hashlib.sha256(raw.encode()).hexdigest()
            if computed != stored_hash:
                return False, f"Hash mismatch at entry {entry_id}: data may be tampered"
            prev = stored_hash
        return True, ""

    def recent(self, n: int = 20) -> list[dict]:
        rows = self._conn.execute(
            "SELECT id, ts, event, payload FROM events ORDER BY ts DESC LIMIT ?", (n,)
        ).fetchall()
        return [{"id": r[0], "ts": r[1], "event": r[2],
                 "payload": json.loads(r[3])} for r in rows]
