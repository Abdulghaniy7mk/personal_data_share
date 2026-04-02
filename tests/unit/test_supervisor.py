"""
tests/unit/test_supervisor.py
"""
import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from security.supervisor import Supervisor


def _action(tool="chat.respond"):
    return {"tool": tool, "action_id": "test", "risk_score": 1}


def test_allows_normal_actions():
    sup = Supervisor()
    ok, reason = sup.allow(_action())
    assert ok
    assert reason == ""


def test_blocks_after_session_budget():
    sup = Supervisor()
    sup._session_count = 200  # simulate exhausted budget
    ok, reason = sup.allow(_action())
    assert not ok
    assert "budget" in reason.lower()


def test_detects_loop():
    sup = Supervisor()
    for _ in range(3):
        sup.allow(_action("terminal.apt_install"))
    ok, reason = sup.allow(_action("terminal.apt_install"))
    assert not ok
    assert "loop" in reason.lower()


def test_resume_clears_halt():
    sup = Supervisor()
    sup._session_count = 201
    sup.allow(_action())  # triggers halt
    assert sup._halted
    sup.resume()
    assert not sup._halted
    ok, _ = sup.allow(_action())
    assert ok


def test_different_tools_dont_trigger_loop():
    sup = Supervisor()
    tools = ["gui.open_app", "gui.type_text", "chat.respond"]
    for t in tools * 3:
        ok, _ = sup.allow(_action(t))
        assert ok
