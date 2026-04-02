"""
input_tagger.py — AI OS Input Tagger Daemon

Runs as root (or with CAP_NET_ADMIN + evdev group).
Watches physical input devices via evdev.
Stamps real user keystrokes/mouse events with an HMAC token
and writes them to a Unix domain socket the AI agent can read.

The AI agent receives events BUT cannot forge the HMAC —
it never sees the signing key (stored in a root-owned tmpfs).

This is the OUT-OF-BAND AUTH channel. The AI model context
window never contains the HMAC key or the raw token.
"""

import asyncio
import hashlib
import hmac
import json
import os
import struct
import time
from pathlib import Path

import evdev  # pip install evdev

# ── Configuration ────────────────────────────────────────────────────────────

SOCKET_PATH = "/run/ai-os/input-tagger.sock"
KEY_PATH    = "/run/ai-os/tagger.key"   # root-owned tmpfs, mode 0600
AI_UID      = 1001                       # the AI agent UID

SENSITIVE_KEY_CODES = {
    evdev.ecodes.KEY_ENTER,
    evdev.ecodes.KEY_KPENTER,
}

# ── Key management ────────────────────────────────────────────────────────────

def load_or_create_session_key() -> bytes:
    """
    Session key lives in root-owned tmpfs. Regenerated each boot.
    AI agent (UID 1001) has no read access to this file.
    """
    p = Path(KEY_PATH)
    p.parent.mkdir(parents=True, exist_ok=True)

    if not p.exists():
        key = os.urandom(32)
        p.write_bytes(key)
        p.chmod(0o600)
        os.chown(p, 0, 0)  # root:root
        print(f"[tagger] Created new session key at {KEY_PATH}")
    else:
        key = p.read_bytes()

    return key


SESSION_KEY = load_or_create_session_key()


# ── Token generation ─────────────────────────────────────────────────────────

def make_human_token(event_data: dict) -> str:
    """
    HMAC-SHA256 over event payload + monotonic timestamp.
    The AI agent can *verify* a token was issued for a specific event,
    but cannot *forge* one — it never has SESSION_KEY.
    """
    payload = json.dumps(event_data, sort_keys=True).encode()
    tag = hmac.new(SESSION_KEY, payload, hashlib.sha256).hexdigest()
    return tag


def make_stamped_event(raw_event: evdev.InputEvent, device_name: str) -> dict:
    ev = {
        "source":      "HUMAN",          # OS-asserted, not model-visible
        "device":      device_name,
        "type":        raw_event.type,
        "code":        raw_event.code,
        "value":       raw_event.value,
        "monotonic_ns": time.monotonic_ns(),
    }
    ev["hmac"] = make_human_token(ev)
    return ev


# ── Client API (used by the policy engine, NOT the AI model) ─────────────────

class HumanTokenVerifier:
    """
    Import this in the policy engine (runs as UID 0 or a trusted service UID).
    The AI model layer never gets an instance of this class.
    """

    def __init__(self):
        self._key = SESSION_KEY  # loaded from tmpfs

    def verify(self, stamped_event: dict) -> bool:
        ev_copy = {k: v for k, v in stamped_event.items() if k != "hmac"}
        expected = make_human_token(ev_copy)
        return hmac.compare_digest(expected, stamped_event.get("hmac", ""))

    def is_human_confirmed(self, context_events: list[dict]) -> bool:
        """
        True if the last ENTER keypress in context_events is HMAC-verified.
        Used by confirmation gate to decide if "yes" came from a real human.
        """
        for ev in reversed(context_events):
            if ev.get("code") in SENSITIVE_KEY_CODES:
                return self.verify(ev)
        return False


# ── Daemon ────────────────────────────────────────────────────────────────────

async def watch_device(device_path: str, clients: list):
    try:
        dev = evdev.InputDevice(device_path)
        print(f"[tagger] Watching {dev.name} ({device_path})")
        async for event in dev.async_read_loop():
            if event.type not in (evdev.ecodes.EV_KEY, evdev.ecodes.EV_REL):
                continue
            stamped = make_stamped_event(event, dev.name)
            msg = (json.dumps(stamped) + "\n").encode()
            dead = []
            for w in clients:
                try:
                    w.write(msg)
                    await w.drain()
                except Exception:
                    dead.append(w)
            for w in dead:
                clients.remove(w)
    except Exception as e:
        print(f"[tagger] Device error on {device_path}: {e}")


async def accept_clients(sock_path: str, clients: list):
    sock = Path(sock_path)
    sock.parent.mkdir(parents=True, exist_ok=True)
    if sock.exists():
        sock.unlink()

    server = await asyncio.start_unix_server(
        lambda r, w: clients.append(w),
        path=str(sock),
    )
    # Only AI agent UID can connect
    os.chmod(sock_path, 0o660)
    os.chown(sock_path, 0, AI_UID)

    print(f"[tagger] Listening on {sock_path}")
    async with server:
        await server.serve_forever()


async def main():
    clients: list = []
    devices = [evdev.InputDevice(p) for p in evdev.list_devices()
               if "keyboard" in evdev.InputDevice(p).name.lower()
               or "mouse" in evdev.InputDevice(p).name.lower()]

    if not devices:
        print("[tagger] WARNING: No input devices found. Run as root.")

    tasks = [asyncio.create_task(watch_device(d.path, clients)) for d in devices]
    tasks.append(asyncio.create_task(accept_clients(SOCKET_PATH, clients)))
    await asyncio.gather(*tasks)


if __name__ == "__main__":
    if os.geteuid() != 0:
        raise PermissionError("input_tagger must run as root (or with evdev CAP)")
    asyncio.run(main())
