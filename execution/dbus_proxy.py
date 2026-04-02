"""
execution/dbus_proxy.py — DBus Proxy Daemon

THE FUNDAMENTAL PROBLEM this solves:
  UID 1001 (AI agent) has no access to UID 1000's D-Bus session bus.
  Apps like VS Code, Firefox, and Steam all live on that session bus.
  Direct access from UID 1001 is blocked by the D-Bus daemon itself.

THE SOLUTION:
  This daemon runs as UID 1000 (real user's systemd user service).
  It listens on a Unix socket that UID 1001 CAN reach.
  It forwards only explicitly whitelisted method calls — nothing else.
  The AI agent sends JSON requests; this daemon makes the real D-Bus call
  and returns the result. UID 1001 never touches the session bus directly.

DEPLOYMENT:
  systemctl --user enable --now ai-dbus-proxy
  (runs as UID 1000, started by the user's systemd session)

SOCKET:
  /run/user/1000/ai-dbus-proxy.sock
  Owned by 1000:ai-agent (group), mode 0660
  UID 1001 is in the 'ai-agent' group → can connect, cannot impersonate UID 1000
"""

import asyncio
import json
import logging
import os
import signal
from pathlib import Path

log = logging.getLogger("ai-os.dbus-proxy")

# ── Whitelist ─────────────────────────────────────────────────────────────────
# Format: "service::interface::method" → allowed
# This is the ONLY set of D-Bus calls the AI agent can make.
# Adding a new capability requires editing this list — deliberate friction.

ALLOWED_CALLS: dict[str, dict] = {
    # XDG application activation (launch any .desktop app cleanly)
    "org.freedesktop.Application": {
        "interface": "org.freedesktop.Application",
        "methods":   {"Activate", "Open"},
        "path":      None,   # any path (app-specific)
    },
    # GNOME Shell (window management — raise, focus)
    "org.gnome.Shell": {
        "interface": "org.gnome.Shell",
        "methods":   {"FocusSearch", "ShowApplications"},
        "path":      "/org/gnome/Shell",
    },
    # KWin (KDE window management)
    "org.kde.KWin": {
        "interface": "org.kde.KWin",
        "methods":   {"nextDesktop", "previousDesktop"},
        "path":      "/KWin",
    },
    # MPRIS — media player control (play/pause/next for music apps)
    "org.mpris.MediaPlayer2": {
        "interface": "org.mpris.MediaPlayer2.Player",
        "methods":   {"Play", "Pause", "Next", "Previous", "Stop"},
        "path":      "/org/mpris/MediaPlayer2",
    },
    # Notifications (AI can send desktop notifications)
    "org.freedesktop.Notifications": {
        "interface": "org.freedesktop.Notifications",
        "methods":   {"Notify"},
        "path":      "/org/freedesktop/Notifications",
    },
    # File manager (open folder in Nautilus/Thunar)
    "org.freedesktop.FileManager1": {
        "interface": "org.freedesktop.FileManager1",
        "methods":   {"ShowFolders", "ShowItems"},
        "path":      "/org/freedesktop/FileManager1",
    },
}

# Hard-deny regardless of whitelist (extra safety net)
DENY_SERVICES = {
    "org.freedesktop.secrets",
    "org.gnome.keyring",
    "org.freedesktop.NetworkManager",
    "org.freedesktop.PolicyKit1",
    "org.kde.kdeconnect",
    "org.freedesktop.login1",      # systemd-logind (session control)
    "org.freedesktop.systemd1",    # systemd unit control
}


# ── Request validation ────────────────────────────────────────────────────────

def validate_request(req: dict) -> tuple[bool, str]:
    """
    Returns (allowed, reason).
    Checked before any D-Bus call is made.
    """
    service   = req.get("service", "")
    interface = req.get("interface", "")
    method    = req.get("method", "")
    args      = req.get("args", [])

    # Hard deny first
    for denied in DENY_SERVICES:
        if service.startswith(denied):
            return False, f"Service '{service}' is permanently denied"

    # Must be in whitelist
    if service not in ALLOWED_CALLS:
        return False, f"Service '{service}' not in allowlist"

    rule = ALLOWED_CALLS[service]

    if method not in rule["methods"]:
        return False, f"Method '{method}' not allowed for {service}"

    if rule["interface"] != interface:
        return False, f"Interface mismatch: expected {rule['interface']}, got {interface}"

    # Arg safety: no args containing shell metacharacters or path traversal
    for arg in args:
        if isinstance(arg, str):
            if any(c in arg for c in (";", "|", "&", "`", "$", "..")):
                return False, f"Unsafe characters in argument: {arg[:60]}"

    return True, ""


# ── D-Bus call (runs as UID 1000 — has session bus access) ───────────────────

async def make_dbus_call(req: dict) -> dict:
    """
    Executes the validated D-Bus call using dbus-python (synchronous,
    run in executor to avoid blocking the event loop).
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _sync_dbus_call, req)


def _sync_dbus_call(req: dict) -> dict:
    try:
        import dbus
        bus     = dbus.SessionBus()
        service = req["service"]
        path    = req.get("path") or ALLOWED_CALLS[service].get("path") or "/"
        iface   = req["interface"]
        method  = req["method"]
        args    = req.get("args", [])

        obj    = bus.get_object(service, path)
        proxy  = dbus.Interface(obj, iface)
        fn     = getattr(proxy, method)
        result = fn(*args) if args else fn()

        return {"ok": True, "result": str(result) if result is not None else ""}

    except ImportError:
        return {"ok": False, "error": "dbus-python not installed: pip install dbus-python"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── Socket server ─────────────────────────────────────────────────────────────

PROXY_SOCKET = f"/run/user/{os.getuid()}/ai-dbus-proxy.sock"
AI_AGENT_GID: int = -1  # resolved at startup


async def handle_connection(reader: asyncio.StreamReader,
                             writer: asyncio.StreamWriter):
    """Handle one request from the AI agent."""
    peer = writer.get_extra_info("peername")
    try:
        raw = await asyncio.wait_for(reader.readline(), timeout=5.0)
        if not raw:
            return

        try:
            req = json.loads(raw.decode())
        except json.JSONDecodeError:
            writer.write(b'{"ok":false,"error":"invalid JSON"}\n')
            await writer.drain()
            return

        allowed, reason = validate_request(req)
        if not allowed:
            log.warning(f"[dbus-proxy] DENIED: {req.get('service')}.{req.get('method')}: {reason}")
            resp = json.dumps({"ok": False, "error": reason})
        else:
            log.info(f"[dbus-proxy] ALLOWED: {req.get('service')}.{req.get('method')}")
            result = await make_dbus_call(req)
            resp = json.dumps(result)

        writer.write((resp + "\n").encode())
        await writer.drain()

    except asyncio.TimeoutError:
        writer.write(b'{"ok":false,"error":"timeout"}\n')
        await writer.drain()
    except Exception as e:
        log.error(f"[dbus-proxy] Handler error: {e}")
    finally:
        writer.close()


async def run_proxy():
    sock = Path(PROXY_SOCKET)
    sock.parent.mkdir(parents=True, exist_ok=True)
    if sock.exists():
        sock.unlink()

    server = await asyncio.start_unix_server(handle_connection, path=PROXY_SOCKET)

    # Set socket permissions: UID 1000 owns it, ai-agent group can connect
    import grp
    try:
        gid = grp.getgrnam("ai-agent").gr_gid
        os.chown(PROXY_SOCKET, os.getuid(), gid)
        os.chmod(PROXY_SOCKET, 0o660)
        log.info(f"[dbus-proxy] Socket {PROXY_SOCKET} owned by uid={os.getuid()} gid={gid}")
    except KeyError:
        # ai-agent group doesn't exist yet — world-readable fallback (less secure)
        os.chmod(PROXY_SOCKET, 0o666)
        log.warning("[dbus-proxy] 'ai-agent' group not found — socket is world-writable. Run setup.sh first.")

    log.info(f"[dbus-proxy] Listening on {PROXY_SOCKET}")

    shutdown = asyncio.Event()
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, shutdown.set)

    async with server:
        await shutdown.wait()

    sock.unlink()
    log.info("[dbus-proxy] Shutdown")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(name)s %(levelname)s %(message)s")
    if os.getuid() == 0:
        raise SystemExit("dbus_proxy must run as UID 1000, not root")
    asyncio.run(run_proxy())
