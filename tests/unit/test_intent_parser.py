"""
tests/unit/test_intent_parser.py
"""
import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from core.intent_parser import parse, CHAT, APP, SYSTEM, RECOVERY, REAL_WORLD, GUI


def test_open_vscode_is_app():
    intent = parse("Open VS Code")
    assert intent.type == APP


def test_fix_wifi_is_system():
    intent = parse("Fix my wifi")
    assert intent.type == SYSTEM


def test_order_pizza_is_real_world():
    intent = parse("Order a pizza for me")
    assert intent.type == REAL_WORLD


def test_rollback_is_recovery():
    intent = parse("Rollback to last snapshot")
    assert intent.type == RECOVERY


def test_type_text_is_gui():
    intent = parse("Type hello world in the editor")
    assert intent.type == GUI


def test_question_is_chat():
    intent = parse("What is Python?")
    assert intent.type == CHAT


def test_high_confidence_for_clear_intent():
    intent = parse("Install vim")
    assert intent.confidence >= 0.9


def test_needs_llm_for_system_action():
    intent = parse("Install vim")
    assert intent.needs_llm is True
