"""
tests/unit/test_audit_log.py
"""
import os
import tempfile
import pytest
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

# Patch the DB path to use a temp file for tests
import security.audit_log as al_module
_tmp = tempfile.mktemp(suffix=".db")
al_module.DB_PATH = __import__("pathlib").Path(_tmp)

from security.audit_log import AuditLog


def test_logs_event():
    log = AuditLog()
    h = log.log("test_event", {"key": "value"})
    assert len(h) == 64  # sha256 hex


def test_chain_valid_after_multiple_entries():
    log = AuditLog()
    for i in range(5):
        log.log(f"event_{i}", {"i": i})
    ok, msg = log.verify_chain()
    assert ok, msg


def test_recent_returns_events():
    log = AuditLog()
    log.log("event_a", {"a": 1})
    log.log("event_b", {"b": 2})
    recent = log.recent(10)
    assert len(recent) >= 2


def test_tamper_detection():
    log = AuditLog()
    log.log("legit", {"x": 1})
    # Tamper directly with the DB
    log._conn.execute("UPDATE events SET payload='{\"tampered\":true}' WHERE event='legit'")
    log._conn.commit()
    ok, msg = log.verify_chain()
    assert not ok
    assert "tampered" in msg.lower() or "mismatch" in msg.lower()
