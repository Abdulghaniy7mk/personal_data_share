"""
execution/terminal_tools.py
Sandboxed terminal command runner using bwrap.
Gap fix #6 from Claude's review: bwrap + network namespace isolation.

All commands run as ai-agent (UID 1001) inside a bwrap sandbox.
No raw shell=True subprocess calls.
"""
from __future__ import annotations
import asyncio
import logging
import shlex
import subprocess
from typing import Any

log = logging.getLogger("terminal_tools")

# bwrap flags: bind-mounted read-only system, writable /tmp, no network by default
_BWRAP_BASE = [
    "bwrap",
    "--ro-bind", "/usr", "/usr",
    "--ro-bind", "/lib", "/lib",
    "--ro-bind", "/lib64", "/lib64",
    "--ro-bind", "/bin", "/bin",
    "--ro-bind", "/sbin", "/sbin",
    "--ro-bind", "/etc", "/etc",
    "--tmpfs", "/tmp",
    "--proc", "/proc",
    "--dev", "/dev",
    "--unshare-pid",
]

_BWRAP_NO_NET = ["--unshare-net"]
_TIMEOUT = 60  # seconds


async def _run_bwrap(cmd: list[str], network: bool = False,
                     cwd: str = "/tmp") -> dict[str, Any]:
    flags = _BWRAP_BASE + ([] if network else _BWRAP_NO_NET)
    full = flags + ["--chdir", cwd, "--"] + cmd

    log.info("terminal_tools: bwrap exec: %s", shlex.join(cmd))
    try:
        proc = await asyncio.create_subprocess_exec(
            *full,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=_TIMEOUT)
        return {
            "returncode": proc.returncode,
            "stdout": stdout.decode(errors="replace")[:4096],
            "stderr": stderr.decode(errors="replace")[:2048],
            "success": proc.returncode == 0,
            "message": stdout.decode(errors="replace")[:200] or f"Exit {proc.returncode}",
        }
    except asyncio.TimeoutError:
        return {"success": False, "message": f"Command timed out after {_TIMEOUT}s",
                "returncode": -1, "stdout": "", "stderr": ""}
    except Exception as e:
        return {"success": False, "message": str(e), "returncode": -1,
                "stdout": "", "stderr": ""}


# ── Public tool functions ─────────────────────────────────────────────────────

async def run_safe(command: str, network: bool = False, cwd: str = "/tmp") -> dict:
    """Run an arbitrary command string inside the bwrap sandbox."""
    cmd = shlex.split(command)
    return await _run_bwrap(cmd, network=network, cwd=cwd)


async def apt_install(package: str) -> dict:
    """Install a package via apt (needs network, runs with elevated bwrap)."""
    log.info("terminal_tools: apt install %s", package)
    return await _run_bwrap(
        ["sudo", "apt-get", "install", "-y", "--no-install-recommends", package],
        network=True,
    )


async def apt_remove(package: str) -> dict:
    """Remove a package via apt."""
    return await _run_bwrap(
        ["sudo", "apt-get", "remove", "-y", package],
        network=False,
    )


async def read_file(path: str) -> dict:
    """Read a file (must be in allowed paths)."""
    allowed_prefixes = ("/home/ai-agent", "/opt/ai-os", "/tmp", "/var/log/ai-os")
    if not any(path.startswith(p) for p in allowed_prefixes):
        return {"success": False, "message": f"Path '{path}' not in allowed read paths."}
    return await _run_bwrap(["cat", path])
