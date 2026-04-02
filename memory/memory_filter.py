"""
memory/memory_filter.py
Pre-inference firewall for memory content.
Strips command-like text, file paths, system directives, and injected content
before any memory record is passed to the LLM planner.
"""
from __future__ import annotations
import re
from typing import Any

from core.context_firewall import clean as _fw_clean

# Additional memory-specific patterns to strip
_MEM_STRIP_PATTERNS: list[re.Pattern] = [
    # Absolute paths
    re.compile(r"(?:^|[\s\"])(\/(?:etc|root|home|var|proc|sys)\/\S+)", re.I | re.M),
    # Environment variable export
    re.compile(r"\bexport\s+\w+=", re.I),
    # Cron patterns
    re.compile(r"\*\s+\*\s+\*\s+\*\s+\*"),
]


def filter_for_inference(text: str, source: str = "memory") -> str:
    """
    Apply context_firewall + memory-specific strip patterns.
    Returns cleaned text safe to include in LLM prompt context.
    """
    text = _fw_clean(text, source=source)
    for pat in _MEM_STRIP_PATTERNS:
        text = pat.sub("[PATH_REDACTED]", text)
    return text


def filter_records(records: list[dict], field: str = "content") -> list[dict]:
    """Filter a list of memory records (dicts) in-place."""
    for r in records:
        if isinstance(r.get(field), str):
            r[field] = filter_for_inference(r[field], source="memory_batch")
    return records


def is_safe_to_store(value: Any) -> bool:
    """Quick check: is this value safe to store in memory at all?"""
    if isinstance(value, str):
        text = _fw_clean(value, source="store_check")
        return text == value  # if firewall changed it, it's not clean
    return True
