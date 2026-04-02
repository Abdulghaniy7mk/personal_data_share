"""
memory/cognitive_store.py
High-level API for cognitive memory (user preferences, style, habits).
All writes are validated by security/learning_guard.py.
All reads are filtered by memory/memory_filter.py.
"""
from __future__ import annotations
import logging
from typing import Any

from core import memory as _mem
from security.learning_guard import safe_write
from memory.memory_filter import filter_for_inference, is_safe_to_store

log = logging.getLogger("cognitive_store")


def set_preference(key: str, value: Any, source: str = "agent") -> bool:
    """
    Store a user preference.
    Returns True on success, False if learning_guard rejected it.
    """
    if not is_safe_to_store(value):
        log.warning("cognitive_store: value for '%s' failed safety check", key)
        return False

    ok, sig = safe_write(key, value, source=source)
    if not ok:
        log.warning("cognitive_store: learning_guard rejected key '%s'", key)
        return False

    _mem.cog_set(key, value, sig)
    log.info("cognitive_store: stored key='%s' source='%s'", key, source)
    return True


def get_preference(key: str, default: Any = None) -> Any:
    """Retrieve a preference. String values are firewall-filtered."""
    return _mem.cog_get(key, default)


def get_all_filtered() -> dict[str, Any]:
    """Get all cognitive entries, with string values filtered."""
    all_prefs = _mem.cog_all()
    return {
        k: filter_for_inference(v, source=f"cog:{k}") if isinstance(v, str) else v
        for k, v in all_prefs.items()
    }


# Convenience setters for common preference types
def set_favorite_app(app: str) -> bool:
    favs: list = get_preference("favorite_apps", [])
    if app not in favs:
        favs.append(app)
    return set_preference("favorite_apps", favs[:20])  # cap at 20


def set_theme(theme: str) -> bool:
    return set_preference("theme", theme)


def set_language(lang: str) -> bool:
    return set_preference("language", lang)
