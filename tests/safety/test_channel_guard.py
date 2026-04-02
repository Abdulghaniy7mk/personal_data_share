"""
tests/safety/test_channel_guard.py
"""
import pytest
from unittest.mock import patch
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from security.channel_guard import ChannelGuard


def test_allows_safe_gui_action():
    guard = ChannelGuard()
    with patch("security.channel_guard._active_window_title", return_value="VS Code"):
        action = {"tool": "gui.type_text", "args": {}}
        assert guard.is_safe(action) is True


def test_blocks_typing_in_polkit():
    guard = ChannelGuard()
    with patch("security.channel_guard._active_window_title",
               return_value="PolicyKit Authentication"):
        action = {"tool": "gui.type_text", "args": {}}
        assert guard.is_safe(action) is False


def test_blocks_typing_in_password_dialog():
    guard = ChannelGuard()
    with patch("security.channel_guard._active_window_title",
               return_value="Enter Password"):
        action = {"tool": "gui.type_text", "args": {}}
        assert guard.is_safe(action) is False


def test_blocks_dangerous_terminal_command():
    guard = ChannelGuard()
    action = {"tool": "terminal.run_safe", "args": {"command": "rm -rf /"}}
    assert guard.is_safe(action) is False


def test_allows_safe_terminal_command():
    guard = ChannelGuard()
    action = {"tool": "terminal.run_safe", "args": {"command": "ls -la /tmp"}}
    assert guard.is_safe(action) is True


def test_allows_non_gui_actions_regardless_of_window():
    guard = ChannelGuard()
    with patch("security.channel_guard._active_window_title",
               return_value="sudo dialog"):
        action = {"tool": "chat.respond", "args": {"text": "hello"}}
        assert guard.is_safe(action) is True
