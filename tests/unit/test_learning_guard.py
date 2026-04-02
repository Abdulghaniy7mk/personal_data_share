"""
tests/unit/test_learning_guard.py
"""
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))


def _make_tmp_secret():
    """Create a temporary 32-byte secret file and return its path."""
    f = tempfile.NamedTemporaryFile(delete=False, suffix=".secret")
    f.write(os.urandom(32))
    f.close()
    return Path(f.name)


# Patch the secret path before importing learning_guard
_tmp_secret_path = _make_tmp_secret()

import security.token_manager as tm_module
tm_module._SECRET_PATH = _tmp_secret_path

from security.learning_guard import validate_write, sign_entry, safe_write


def test_valid_simple_string():
    sig = sign_entry("theme", "dark")
    assert validate_write("theme", "dark", sig) is True


def test_rejects_protected_key():
    sig = sign_entry("user_password", "secret")
    assert validate_write("user_password", "secret", sig) is False


def test_rejects_too_long_value():
    big = "x" * 5000
    sig = sign_entry("some_key", big)
    assert validate_write("some_key", big, sig) is False


def test_rejects_malformed_signature():
    assert validate_write("theme", "dark", "badsig") is False


def test_rejects_injection_in_string():
    sig = sign_entry("note", "os.system('rm -rf /')")
    assert validate_write("note", "os.system('rm -rf /')", sig) is False


def test_safe_write_convenience():
    ok, sig = safe_write("favorite_app", "vscode")
    assert ok
    assert len(sig) == 64


def test_safe_write_rejects_protected():
    ok, sig = safe_write("sudo_password", "s3cr3t")
    assert not ok
    assert sig == ""
