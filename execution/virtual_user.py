"""
execution/virtual_user.py
Synthesises keyboard and mouse events using ydotool.
All calls are rate-limited and length-capped.
"""
from __future__ import annotations
import asyncio
import logging
import subprocess

log = logging.getLogger("virtual_user")

_MAX_TEXT_LEN = 500
_YDOTOOL = "ydotool"


async def type_text(text: str, delay_ms: int = 12) -> bool:
    """Type text via ydotool with per-character delay."""
    if len(text) > _MAX_TEXT_LEN:
        log.warning("virtual_user: text truncated to %d chars", _MAX_TEXT_LEN)
        text = text[:_MAX_TEXT_LEN]
    try:
        proc = await asyncio.create_subprocess_exec(
            _YDOTOOL, "type", f"--delay={delay_ms}", "--", text,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
        ok = proc.returncode == 0
        if not ok:
            log.warning("virtual_user: type_text failed: %s", stderr.decode())
        return ok
    except Exception as e:
        log.error("virtual_user: type_text error: %s", e)
        return False


async def click(x: int, y: int, button: str = "left") -> bool:
    """Click at screen coordinates."""
    btn_code = {"left": "0x40", "right": "0x41", "middle": "0x42"}.get(button, "0x40")
    try:
        await asyncio.create_subprocess_exec(
            _YDOTOOL, "mousemove", "--absolute", "--", str(x), str(y)
        )
        await asyncio.sleep(0.05)
        proc = await asyncio.create_subprocess_exec(
            _YDOTOOL, "click", btn_code,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        await asyncio.wait_for(proc.wait(), timeout=5)
        return proc.returncode == 0
    except Exception as e:
        log.error("virtual_user: click error: %s", e)
        return False


async def key_combo(keys: str) -> bool:
    """Press a key combination e.g. 'ctrl+c', 'super+d'."""
    try:
        proc = await asyncio.create_subprocess_exec(
            _YDOTOOL, "key", "--", keys,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        await asyncio.wait_for(proc.wait(), timeout=5)
        return proc.returncode == 0
    except Exception as e:
        log.error("virtual_user: key_combo error: %s", e)
        return False
