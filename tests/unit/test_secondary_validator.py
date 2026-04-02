"""
tests/unit/test_secondary_validator.py
"""
import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from security.secondary_validator import SecondaryValidator


def test_passes_low_risk_chat():
    v = SecondaryValidator()
    action = {"tool": "chat.respond", "risk_score": 0, "args": {}, "rollback": None, "snapshot_before": False}
    assert v.check(action) == ""


def test_blocks_underscore_risk_score():
    v = SecondaryValidator()
    action = {
        "tool": "terminal.apt_install",
        "risk_score": 2,          # too low — min is 5
        "args": {"package": "vim"},
        "rollback": "terminal.apt_remove",
        "snapshot_before": True,
    }
    result = v.check(action)
    assert result != ""
    assert "risk_score" in result


def test_blocks_forbidden_rm_rf():
    v = SecondaryValidator()
    action = {
        "tool": "terminal.run_safe",
        "risk_score": 4,
        "args": {"command": "rm -rf /home"},
        "rollback": None,
        "snapshot_before": False,
    }
    result = v.check(action)
    assert result != ""


def test_blocks_missing_rollback():
    v = SecondaryValidator()
    action = {
        "tool": "terminal.apt_install",
        "risk_score": 5,
        "args": {"package": "vim"},
        "rollback": None,           # missing!
        "snapshot_before": True,
    }
    result = v.check(action)
    assert "rollback" in result


def test_blocks_missing_snapshot():
    v = SecondaryValidator()
    action = {
        "tool": "terminal.apt_install",
        "risk_score": 5,
        "args": {"package": "vim"},
        "rollback": "terminal.apt_remove",
        "snapshot_before": False,   # missing!
    }
    result = v.check(action)
    assert "snapshot" in result


def test_passes_valid_system_action():
    v = SecondaryValidator()
    action = {
        "tool": "terminal.apt_install",
        "risk_score": 5,
        "args": {"package": "vim"},
        "rollback": "terminal.apt_remove",
        "snapshot_before": True,
    }
    assert v.check(action) == ""
