"""
tests/safety/test_policy_engine.py
"""
import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from security.policy_engine import PolicyEngine


def test_allows_safe_action():
    engine = PolicyEngine()
    action = {"tool": "terminal.run_safe", "args": {"command": "echo hello"}}
    ok, reason = engine.is_allowed(action)
    assert ok


def test_denies_rm_rf_root():
    engine = PolicyEngine()
    action = {"tool": "terminal.run_safe", "args": {"command": "rm -rf /"}}
    ok, reason = engine.is_allowed(action)
    assert not ok
    assert "rm -rf" in reason


def test_denies_shadow_file_edit():
    engine = PolicyEngine()
    action = {"tool": "system.edit_config", "args": {"path": "/etc/shadow"}}
    ok, reason = engine.is_allowed(action)
    assert not ok


def test_requires_human_for_order():
    engine = PolicyEngine()
    action = {"tool": "real_world.confirm_order", "args": {}}
    assert engine.requires_human(action) is True


def test_does_not_require_human_for_chat():
    engine = PolicyEngine()
    action = {"tool": "chat.respond", "args": {}}
    assert engine.requires_human(action) is False
