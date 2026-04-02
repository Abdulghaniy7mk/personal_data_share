"""
memory/operational_store.py
High-level API for operational memory (action history, results, rollback info).
"""
from __future__ import annotations
import logging
from typing import Any

from core import memory as _mem
from memory.memory_filter import filter_records

log = logging.getLogger("operational_store")


def record_action(action: dict, event_type: str = "execution_result") -> str:
    """Append an action event. Returns the record ID."""
    return _mem.op_log(
        event_type=event_type,
        payload=action,
        action_id=action.get("action_id", ""),
    )


def get_recent_context(n: int = 10) -> list[dict]:
    """
    Return last N operational events, with string fields filtered
    for safe inclusion in LLM prompt context.
    """
    records = _mem.op_recent(n)
    # Keep only lightweight fields for context
    slim = [
        {
            "event_type": r["event_type"],
            "content": str(r["payload"].get("description", r["payload"].get("message", ""))),
            "ts": r["ts"],
        }
        for r in records
    ]
    return filter_records(slim)


def get_rollback_info(action_id: str) -> dict | None:
    """Return rollback info for a specific action, if available."""
    events = _mem.op_by_action(action_id)
    for e in events:
        if e.get("event_type") == "snapshot_taken":
            return e.get("payload")
    return None


def summarize_session() -> dict:
    """Return a lightweight summary of the current session."""
    recent = _mem.op_recent(50)
    total = len(recent)
    errors = sum(1 for r in recent if r["event_type"] == "execution_error")
    snapshots = sum(1 for r in recent if r["event_type"] == "snapshot_taken")
    return {
        "total_events": total,
        "errors": errors,
        "snapshots_taken": snapshots,
    }
