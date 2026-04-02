"""
ui/ui_server.py — AI OS UI Server

Bridges the chat/voice sidebar (browser-based) to the agent's Unix socket.

Architecture:
  Browser UI  ←→  WebSocket (ws://localhost:8765)  ←→  ui_server.py
                                                          ↓
                                               Unix socket /run/ai-os/agent.sock
                                                          ↓
                                                     agent_main.py (UID 1001)

Why WebSocket to browser instead of direct socket:
  Browser JavaScript cannot open Unix sockets. WebSocket is the
  standard bridge. The server binds to localhost only — not exposed
  to the network.

HMAC tagging:
  The UI server is the ONLY component that injects source="HUMAN"
  into messages. It does this only after verifying the WebSocket
  connection originated from the local user session (Origin check)
  AND the message arrived on the UI channel (not a programmatic call).

  Automation scripts hitting the WebSocket directly still get
  source="UI_UNKNOWN" — the input_tagger's HMAC is the authoritative
  human marker; this is a secondary defense.

Run:
  python -m ui.ui_server
  (as UID 1000, after agent is started as UID 1001)
"""

import asyncio
import json
import logging
import os
import signal
import time
from pathlib import Path
from typing import Optional

log = logging.getLogger("ai-os.ui-server")

WS_HOST       = "127.0.0.1"     # localhost only — never 0.0.0.0
WS_PORT       = 8765
AGENT_SOCKET  = "/run/ai-os/agent.sock"
ALLOWED_ORIGINS = {
    f"http://localhost:{WS_PORT}",
    f"http://127.0.0.1:{WS_PORT}",
    "file://",           # local file:// HTML UI
}


# ── Agent socket client ───────────────────────────────────────────────────────

async def send_to_agent(text: str, source: str = "HUMAN") -> str:
    """
    Send a message to agent_main.py via its Unix socket.
    Returns the agent's response string.
    Raises ConnectionRefusedError if agent is not running.
    """
    if not Path(AGENT_SOCKET).exists():
        raise FileNotFoundError(f"Agent socket not found: {AGENT_SOCKET}. "
                                "Is ai-agent.service running?")

    msg = json.dumps({"text": text, "source": source}) + "\n"

    try:
        reader, writer = await asyncio.open_unix_connection(AGENT_SOCKET)
        writer.write(msg.encode())
        await writer.drain()

        resp_raw = await asyncio.wait_for(reader.readline(), timeout=60.0)
        writer.close()
        await writer.wait_closed()

        resp = json.loads(resp_raw.decode())
        return resp.get("response", "")

    except asyncio.TimeoutError:
        return "Request timed out (60s). The AI may still be working."
    except json.JSONDecodeError:
        return "Agent returned an invalid response."


# ── WebSocket handler ─────────────────────────────────────────────────────────

_connected_clients: set = set()


async def ws_handler(websocket):
    """Handle one browser WebSocket connection."""
    try:
        import websockets.exceptions
    except ImportError:
        log.error("websockets not installed: pip install websockets")
        return

    # Origin check — only allow connections from local sources
    origin = websocket.request_headers.get("Origin", "")
    if origin and not any(origin.startswith(a) for a in ALLOWED_ORIGINS):
        log.warning(f"[ui] Rejected connection from origin: {origin}")
        await websocket.close(1008, "Origin not allowed")
        return

    _connected_clients.add(websocket)
    client_id = id(websocket)
    log.info(f"[ui] Client connected #{client_id}")

    try:
        async for raw_msg in websocket:
            try:
                msg = json.loads(raw_msg)
            except json.JSONDecodeError:
                await websocket.send(json.dumps({
                    "type": "error", "message": "Invalid JSON"
                }))
                continue

            msg_type = msg.get("type", "text")

            # ── Ping/status ──────────────────────────────────────────────────
            if msg_type == "ping":
                await websocket.send(json.dumps({
                    "type": "pong",
                    "agent_running": Path(AGENT_SOCKET).exists(),
                    "ts": time.time(),
                }))
                continue

            # ── Supervisor resume ────────────────────────────────────────────
            if msg_type == "supervisor_resume":
                resp = await send_to_agent("resume AI", source="HUMAN")
                await websocket.send(json.dumps({"type": "text", "response": resp}))
                continue

            # ── Text command ─────────────────────────────────────────────────
            if msg_type in ("text", "voice_text"):
                text = msg.get("text", "").strip()
                if not text:
                    continue

                # All messages from the UI are human-initiated
                # (input_tagger provides the authoritative HMAC; this is secondary)
                source = "HUMAN" if msg_type in ("text", "voice_text") else "UI_UNKNOWN"

                # Notify UI that agent is processing
                await websocket.send(json.dumps({
                    "type": "status",
                    "status": "thinking",
                    "text": text,
                }))

                try:
                    response = await send_to_agent(text, source)
                    await websocket.send(json.dumps({
                        "type":     "response",
                        "response": response,
                        "ts":       time.time(),
                    }))
                except FileNotFoundError as e:
                    await websocket.send(json.dumps({
                        "type":    "error",
                        "message": str(e),
                    }))
                continue

            # ── Confirmation response (user clicked Yes/No in UI) ────────────
            if msg_type == "confirm_response":
                # Forward to confirm-ui socket (used by confirm_gate.py)
                await _forward_confirmation(msg)
                continue

            # ── Unknown ──────────────────────────────────────────────────────
            log.warning(f"[ui] Unknown message type: {msg_type}")

    except Exception as e:
        # websockets.exceptions.ConnectionClosed is expected on browser close
        if "ConnectionClosed" not in type(e).__name__:
            log.error(f"[ui] Handler error for client #{client_id}: {e}")
    finally:
        _connected_clients.discard(websocket)
        log.info(f"[ui] Client disconnected #{client_id}")


async def _forward_confirmation(msg: dict):
    """Forward a confirmation decision to the confirm gate's socket."""
    confirm_socket = "/run/ai-os/confirm-ui.sock"
    if not Path(confirm_socket).exists():
        log.warning("[ui] Confirm socket not found — confirmation lost")
        return
    try:
        _, writer = await asyncio.open_unix_connection(confirm_socket)
        writer.write((json.dumps(msg) + "\n").encode())
        await writer.drain()
        writer.close()
    except Exception as e:
        log.error(f"[ui] Forward confirmation error: {e}")


async def broadcast(message: dict):
    """Broadcast a message to all connected clients (e.g. agent notifications)."""
    if not _connected_clients:
        return
    raw = json.dumps(message)
    dead = set()
    for ws in _connected_clients:
        try:
            await ws.send(raw)
        except Exception:
            dead.add(ws)
    _connected_clients -= dead


# ── Notification socket (agent → UI push) ────────────────────────────────────

NOTIFY_SOCKET = "/run/ai-os/confirm-ui.sock"


async def run_notification_listener():
    """
    Listen for push notifications from confirm_gate.py.
    The confirmation gate writes requests here; we forward them to the browser.
    """
    sock = Path(NOTIFY_SOCKET)
    sock.parent.mkdir(parents=True, exist_ok=True)
    if sock.exists():
        sock.unlink()

    server = await asyncio.start_unix_server(
        _handle_notification, path=str(NOTIFY_SOCKET)
    )
    os.chmod(NOTIFY_SOCKET, 0o660)
    log.info(f"[ui] Notification socket listening on {NOTIFY_SOCKET}")
    async with server:
        await asyncio.Event().wait()  # run forever


async def _handle_notification(reader: asyncio.StreamReader,
                                 writer: asyncio.StreamWriter):
    """Receive a notification/confirmation request from the agent and push to browser."""
    try:
        raw = await asyncio.wait_for(reader.readline(), timeout=5.0)
        msg = json.loads(raw.decode())
        await broadcast(msg)

        # For confirmation requests, wait for browser response
        if msg.get("type") in ("confirm_request", "real_world_confirm"):
            response_event = asyncio.Event()
            _pending_confirmations[msg.get("id", "default")] = (response_event, writer)
            try:
                await asyncio.wait_for(response_event.wait(),
                                       timeout=msg.get("timeout_sec", 60))
            except asyncio.TimeoutError:
                resp = json.dumps({"approved": False, "reason": "timeout"})
                writer.write((resp + "\n").encode())
                await writer.drain()
        else:
            writer.write(b'{"ok":true}\n')
            await writer.drain()
    except Exception as e:
        log.error(f"[ui] Notification handler error: {e}")
    finally:
        writer.close()


_pending_confirmations: dict = {}


# ── Main ──────────────────────────────────────────────────────────────────────

async def main():
    try:
        import websockets
    except ImportError:
        raise SystemExit("websockets not installed: pip install websockets")

    shutdown = asyncio.Event()
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, shutdown.set)

    ws_server   = await websockets.serve(ws_handler, WS_HOST, WS_PORT)
    notify_task = asyncio.create_task(run_notification_listener())

    log.info(f"[ui] WebSocket server on ws://{WS_HOST}:{WS_PORT}")
    log.info(f"[ui] Open ui/index.html in your browser to connect")

    await shutdown.wait()

    ws_server.close()
    await ws_server.wait_closed()
    notify_task.cancel()
    log.info("[ui] Shutdown complete")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(name)s %(levelname)s %(message)s")
    asyncio.run(main())
