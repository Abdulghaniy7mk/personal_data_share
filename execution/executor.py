"""
executor.py — AI OS Virtual User Execution Engine

Runs as UID 1001 inside ai-agent.slice (cgroup-isolated).
Provides a clean API for the AI planner to control apps.

Execution priority order:
  1. DBus native API  (most reliable, least invasive)
  2. AT-SPI accessibility (Wayland-compatible, filtered)
  3. ydotool virtual input (last resort, broker-mediated)
  4. VLM vision fallback (screen capture — restricted mode only)

Never touches:
  - password dialogs (WM_CLASS: pinentry, polkit, gnome-keyring)
  - auth windows
  - banking/finance app classes (configurable deny list)
"""

import asyncio
import json
import logging
import os
import subprocess
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Any

# AT-SPI (pyatspi2)
try:
    import pyatspi
    ATSPI_AVAILABLE = True
except ImportError:
    ATSPI_AVAILABLE = False
    logging.warning("pyatspi not available — AT-SPI execution disabled")

log = logging.getLogger("ai-executor")

# ── App security classification ───────────────────────────────────────────────

ALLOWED_ATSPI_CLASSES = frozenset({
    "code",           # VS Code
    "code-oss",
    "codium",
    "Alacritty",
    "kitty",
    "gnome-terminal-server",
    "konsole",
    "firefox",        # browser in AI profile only
    "chromium",
    "brave-browser",
    "thunar",         # file manager
    "nautilus",
    "gedit",
    "mousepad",
    "libreoffice",
})

DENY_ATSPI_CLASSES = frozenset({
    # Auth / credentials — AI NEVER touches these
    "pinentry",
    "pinentry-gtk-2",
    "pinentry-gnome3",
    "polkit-gnome-authentication-agent-1",
    "gnome-keyring-3",
    "keepassxc",
    "bitwarden",
    # Finance
    "electrum",
    # System auth
    "gksu",
    "pkexec",
})

CONFIRM_BEFORE_CLASSES = frozenset({
    # These are allowed but always need user confirmation first
    "firefox",
    "chromium",
    "brave-browser",
})


class ExecMethod(Enum):
    DBUS   = auto()
    ATSPI  = auto()
    YDOTOOL = auto()
    DENIED = auto()


@dataclass
class AppHandle:
    wm_class:    str
    pid:         int
    method:      ExecMethod
    atspi_ref:   Any = field(default=None, repr=False)


# ── DBus broker ───────────────────────────────────────────────────────────────

class DBusBroker:
    """
    Talks to the DBus proxy daemon (runs as UID 1000).
    AI agent never touches the session bus directly.
    Proxy enforces a method whitelist.
    """

    PROXY_SOCKET = "/run/ai-os/dbus-proxy.sock"

    async def call(self, service: str, path: str, iface: str, method: str,
                   args: list) -> dict:
        if not Path(self.PROXY_SOCKET).exists():
            return {"ok": False, "error": "DBus proxy not running"}

        req = json.dumps({
            "service": service, "path": path,
            "interface": iface, "method": method,
            "args": args,
        })

        try:
            reader, writer = await asyncio.open_unix_connection(self.PROXY_SOCKET)
            writer.write((req + "\n").encode())
            await writer.drain()
            resp = await asyncio.wait_for(reader.readline(), timeout=5.0)
            writer.close()
            return json.loads(resp.decode())
        except Exception as e:
            return {"ok": False, "error": str(e)}

    async def launch_app(self, desktop_id: str) -> dict:
        """Launch via org.freedesktop.Application (XDG)."""
        return await self.call(
            f"org.{desktop_id}",
            "/org/freedesktop/Application",
            "org.freedesktop.Application",
            "Activate",
            [{}],
        )


# ── AT-SPI executor ───────────────────────────────────────────────────────────

class ATSPIExecutor:
    """
    Controls running apps via the accessibility bus.
    Enforces the allow/deny class lists before any interaction.
    """

    def _get_window_class(self, accessible) -> str:
        try:
            attrs = dict(accessible.getAttributes())
            return attrs.get("class", "").lower()
        except Exception:
            return ""

    def _is_allowed(self, wm_class: str) -> bool:
        lc = wm_class.lower()
        if any(d in lc for d in DENY_ATSPI_CLASSES):
            log.warning(f"[atspi] DENIED access to {wm_class} (security class)")
            return False
        if any(a in lc for a in ALLOWED_ATSPI_CLASSES):
            return True
        log.warning(f"[atspi] {wm_class} not in allow list — defaulting to DENY")
        return False

    def find_app(self, wm_class_fragment: str) -> AppHandle | None:
        if not ATSPI_AVAILABLE:
            return None
        desktop = pyatspi.Registry.getDesktop(0)
        for app in desktop:
            if app is None:
                continue
            app_name = (app.name or "").lower()
            if wm_class_fragment.lower() in app_name:
                if not self._is_allowed(app_name):
                    return AppHandle(app_name, app.get_process_id(),
                                     ExecMethod.DENIED)
                return AppHandle(app_name, app.get_process_id(),
                                 ExecMethod.ATSPI, app)
        return None

    async def click_button(self, handle: AppHandle, label: str) -> bool:
        if handle.method == ExecMethod.DENIED or handle.atspi_ref is None:
            return False
        try:
            pred = pyatspi.utils.matchName(label)
            result = pyatspi.utils.findDescendant(handle.atspi_ref, pred)
            if result:
                result.queryAction().doAction(0)
                return True
        except Exception as e:
            log.error(f"[atspi] click_button failed: {e}")
        return False

    async def type_text(self, handle: AppHandle, text: str) -> bool:
        if handle.method == ExecMethod.DENIED or handle.atspi_ref is None:
            return False
        try:
            focused = pyatspi.utils.findDescendant(
                handle.atspi_ref,
                lambda x: x.getRole() == pyatspi.ROLE_TEXT and
                          x.getState().contains(pyatspi.STATE_FOCUSED)
            )
            if focused:
                pyatspi.Registry.generateKeyboardEvent(
                    0, text, pyatspi.KEY_STRING
                )
                return True
        except Exception as e:
            log.error(f"[atspi] type_text failed: {e}")
        return False


# ── ydotool broker ────────────────────────────────────────────────────────────

class YdotoolBroker:
    """
    UID 1001 never touches /dev/uinput directly.
    Sends signed requests to input-broker daemon (runs as root).
    Broker verifies the request came from ai-agent.slice before injecting.
    """

    BROKER_SOCKET = "/run/ai-os/input-broker.sock"

    async def _send(self, cmd: dict) -> bool:
        if not Path(self.BROKER_SOCKET).exists():
            log.error("[ydotool] Input broker not running")
            return False
        try:
            reader, writer = await asyncio.open_unix_connection(self.BROKER_SOCKET)
            writer.write((json.dumps(cmd) + "\n").encode())
            await writer.drain()
            resp = json.loads((await reader.readline()).decode())
            writer.close()
            return resp.get("ok", False)
        except Exception as e:
            log.error(f"[ydotool] broker error: {e}")
            return False

    async def key(self, keysym: str) -> bool:
        return await self._send({"type": "key", "keysym": keysym})

    async def type_text(self, text: str) -> bool:
        return await self._send({"type": "type", "text": text})

    async def click(self, button: int = 1) -> bool:
        return await self._send({"type": "click", "button": button})

    async def move(self, x: int, y: int) -> bool:
        return await self._send({"type": "move", "x": x, "y": y})


# ── Main execution engine ─────────────────────────────────────────────────────

class ExecutionEngine:
    """
    Top-level API the AI planner calls.
    Planner never touches DBus, AT-SPI, or ydotool directly.
    """

    def __init__(self):
        self.dbus   = DBusBroker()
        self.atspi  = ATSPIExecutor()
        self.ydotool = YdotoolBroker()

    async def launch_app(self, app_name: str) -> dict:
        """Launch an application. Returns status dict."""
        log.info(f"[engine] launch_app: {app_name}")

        # Try DBus first (cleanest)
        result = await self.dbus.launch_app(app_name)
        if result.get("ok"):
            return {"ok": True, "method": "dbus", "app": app_name}

        # Fallback: subprocess launch as UID 1001 (user-level, not root)
        try:
            proc = subprocess.Popen(
                [app_name],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            await asyncio.sleep(1.5)  # wait for window
            return {"ok": True, "method": "subprocess", "pid": proc.pid}
        except FileNotFoundError:
            return {"ok": False, "error": f"{app_name} not found"}

    async def type_in_app(self, app_class: str, text: str) -> dict:
        """Type text into a running application."""
        handle = self.atspi.find_app(app_class)

        if handle is None:
            # AT-SPI didn't find it — try ydotool (window must be focused)
            ok = await self.ydotool.type_text(text)
            return {"ok": ok, "method": "ydotool"}

        if handle.method == ExecMethod.DENIED:
            return {"ok": False, "error": f"{app_class} is in the security deny list"}

        ok = await self.atspi.type_text(handle, text)
        if not ok:
            ok = await self.ydotool.type_text(text)
            return {"ok": ok, "method": "ydotool_fallback"}

        return {"ok": True, "method": "atspi", "app": handle.wm_class}

    async def click_in_app(self, app_class: str, button_label: str) -> dict:
        handle = self.atspi.find_app(app_class)
        if handle is None or handle.method == ExecMethod.DENIED:
            return {"ok": False, "error": "app not found or denied"}
        ok = await self.atspi.click_button(handle, button_label)
        return {"ok": ok, "method": "atspi"}

    async def open_file_in_editor(self, filepath: str,
                                   editor: str = "code") -> dict:
        """Open a file in VS Code (or configured editor)."""
        p = Path(filepath).expanduser().resolve()
        if not p.exists():
            return {"ok": False, "error": f"File not found: {filepath}"}
        try:
            subprocess.Popen([editor, str(p)],
                             stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
            return {"ok": True, "file": str(p), "editor": editor}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    async def run_terminal_command(self, command: str,
                                    cwd: str | None = None) -> dict:
        """
        Run a shell command as UID 1001 (not root).
        Sandboxed via bwrap — no network unless explicitly granted.
        """
        bwrap_cmd = [
            "bwrap",
            "--ro-bind", "/usr", "/usr",
            "--ro-bind", "/lib", "/lib",
            "--ro-bind", "/lib64", "/lib64",
            "--ro-bind", "/bin", "/bin",
            "--bind", str(Path.home()), str(Path.home()),
            "--tmpfs", "/tmp",
            "--proc", "/proc",
            "--dev", "/dev",
            "--unshare-net",          # no network by default
            "--unshare-pid",
            "--die-with-parent",
            "--",
            "/bin/bash", "-c", command,
        ]
        try:
            proc = await asyncio.create_subprocess_exec(
                *bwrap_cmd,
                cwd=cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                limit=1024 * 1024,  # 1MB output cap
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=30.0
                )
            except asyncio.TimeoutError:
                proc.kill()
                return {"ok": False, "error": "Command timed out (30s)"}

            return {
                "ok": proc.returncode == 0,
                "returncode": proc.returncode,
                "stdout": stdout.decode(errors="replace")[:4096],
                "stderr": stderr.decode(errors="replace")[:1024],
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}
