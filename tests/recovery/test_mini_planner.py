"""
tests/recovery/test_mini_planner.py
"""
import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from recovery.recovery_core.mini_planner import diagnose


def test_diagnose_boot_issue():
    result = diagnose("system won't boot, grub error")
    assert result["plan"] == "fix_boot"
    assert result["human_required"] is True
    assert len(result["steps"]) > 0


def test_diagnose_model_issue():
    result = diagnose("Ollama model cache is broken")
    assert result["plan"] == "fix_model_cache"
    assert result["risk"] == "low"


def test_diagnose_config_issue():
    result = diagnose("YAML config is invalid")
    assert result["plan"] == "fix_config"


def test_diagnose_agent_reset():
    result = diagnose("agent is corrupted and broken")
    assert result["plan"] == "reset_ai_user"
    assert result["human_required"] is True


def test_diagnose_unknown_falls_back_to_config():
    result = diagnose("something weird happened")
    assert result["plan"] == "fix_config"
    assert "note" in result


def test_no_llm_import():
    """mini_planner must not import the ollama module (no LLM dependency)."""
    import recovery.recovery_core.mini_planner as mp
    import inspect
    src = inspect.getsource(mp)
    # The docstring may mention "Ollama" as a word, but there must be no import statement
    assert "import ollama" not in src
    assert "from ollama" not in src
    assert "import openai" not in src
