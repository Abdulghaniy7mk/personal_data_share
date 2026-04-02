"""
agent_main.py — AI OS Central Agent Loop

Entry point for the AI agent process (UID 1001, ai-agent.slice).
Connects: voice → planner → supervisor → gate → executor → log.

Run: python -m core.agent_main --config config/default.yaml
"""

import asyncio
import logging
import signal
import sys
import time
from pathlib import Path

import yaml

from core.planner import Planner, PlannedAction
from core.context_firewall import ContextFirewall
from core.memory import Memory
from security.supervisor import Supervisor
from security.channel_guard import ChannelGuard
from security.confirm_gate import ConfirmationGate, ActionProposal, RiskLevel
from execution.executor import ExecutionEngine
from execution.real_world import RealWorldBarrier
from recovery.snapshot import SnapshotManager

log = logging.getLogger("ai-os.agent")


# ── Config ────────────────────────────────────────────────────────────────────

def load_config(path: str) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


# ── Signal handling ───────────────────────────────────────────────────────────

_shutdown = asyncio.Event()

def _handle_signal(sig, _):
    log.warning(f"[agent] Signal {sig.name} received — initiating shutdown")
    _shutdown.set()


# ── Main agent class ──────────────────────────────────────────────────────────

class AIAgent:
    def __init__(self, cfg: dict):
        self.cfg        = cfg
        self.memory     = Memory(cfg)
        self.firewall   = ContextFirewall(cfg)
        self.planner    = Planner(cfg)
        self.supervisor = Supervisor(cfg)
        self.chan_guard  = ChannelGuard()
        self.executor   = ExecutionEngine()
        self.rw_barrier = RealWorldBarrier()
        self.snapshots  = SnapshotManager(cfg)

        # Wire confirmation gate → executor
        self.gate = ConfirmationGate(
            on_execute=self._dispatch,
            on_block=self._on_block,
        )

        self._session_actions: list[dict] = []

    # ── Public entry points ───────────────────────────────────────────────────

    async def handle_text(self, text: str, source: str = "HUMAN") -> str:
        """
        Process a text command. source="HUMAN" only if HMAC-verified by input_tagger.
        Content the AI read from files/web always comes in as source="AI_READ".
        """
        log.info(f"[agent] handle_text | source={source} | text={text[:80]}")

        # 1. Supervisor: check rate limits and loop detection first
        supervisor_ok, reason = self.supervisor.check(text, source)
        if not supervisor_ok:
            return f"[Supervisor blocked]: {reason}"

        # 2. Build planning context (filtered by context firewall)
        raw_memory   = self.memory.get_relevant(text)
        safe_context = self.firewall.filter_for_planning(raw_memory)

        # 3. Plan
        try:
            actions = await self.planner.plan(text, safe_context, source)
        except Exception as e:
            log.error(f"[agent] Planner error: {e}")
            return "I encountered an error while planning. Please try again."

        if not actions:
            return "I understood your request but couldn't determine specific actions."

        # 4. Execute each planned action through the gate
        results = []
        for action in actions:
            # Channel guard: block AI typing into auth dialogs etc.
            if not self.chan_guard.is_allowed(action):
                log.warning(f"[chan_guard] Blocked: {action.action_type} → {action.params}")
                results.append(f"Blocked by channel guard: {action.description}")
                continue

            # Real-world barrier: payments, orders, calls need special confirmation
            if self.rw_barrier.is_real_world(action):
                ok = await self.rw_barrier.confirm(action)
                if not ok:
                    results.append(f"Real-world action cancelled by user: {action.description}")
                    continue

            # Take a snapshot before any system-level action
            if action.risk_level in (RiskLevel.CONFIRM, RiskLevel.BLOCK):
                await self.snapshots.take(f"pre_{action.action_type}")

            # Main confirmation gate
            result = await self.gate.process(action)
            results.append(self._format_result(action, result))

            # Record to memory only on success + human-approved actions
            if result.get("ok") and source == "HUMAN":
                self.memory.record_success(text, action, result)

            # Supervisor: record completed action
            self.supervisor.record_action(action.action_type, result.get("ok", False))

        return "\n".join(results) if results else "Done."

    async def handle_voice(self, audio_bytes: bytes) -> str:
        """
        Transcribe audio then handle as human input.
        STT is local (Whisper) — audio never leaves the device.
        """
        try:
            from voice.voice_pipeline import transcribe
            text = await transcribe(audio_bytes, self.cfg)
            return await self.handle_text(text, source="HUMAN")
        except Exception as e:
            log.error(f"[agent] Voice error: {e}")
            return "Voice transcription failed."

    # ── Internal ──────────────────────────────────────────────────────────────

    async def _dispatch(self, proposal: ActionProposal) -> dict:
        """Called by ConfirmationGate after approval. Calls the right executor method."""
        a = proposal.action_type
        p = proposal.params

        dispatch_table = {
            "launch_app":         lambda: self.executor.launch_app(p["app"]),
            "type_in_app":        lambda: self.executor.type_in_app(p["app_class"], p["text"]),
            "click_in_app":       lambda: self.executor.click_in_app(p["app_class"], p["button"]),
            "open_file":          lambda: self.executor.open_file_in_editor(p["path"], p.get("editor","code")),
            "run_command":        lambda: self.executor.run_terminal_command(p["command"], p.get("cwd")),
            "browse_url":         lambda: self._browse(p["url"]),
            "install_package":    lambda: self.executor.run_terminal_command(f"apt install -y {p['package']}"),
        }

        handler = dispatch_table.get(a)
        if handler is None:
            return {"ok": False, "error": f"Unknown action type: {a}"}

        try:
            return await handler()
        except Exception as e:
            log.error(f"[agent] Dispatch error for {a}: {e}")
            return {"ok": False, "error": str(e)}

    async def _browse(self, url: str) -> dict:
        """Open URL in browser — always notified, never silent."""
        return await self.executor.launch_app(f"firefox --new-tab {url}")

    def _on_block(self, proposal: ActionProposal, _risk):
        log.warning(f"[agent] Hard-blocked: {proposal.action_type} — {proposal.description}")

    def _format_result(self, action: ActionProposal, result: dict) -> str:
        if result.get("blocked"):
            return f"Blocked: {action.description}"
        if result.get("rejected"):
            return f"Cancelled: {action.description}"
        if result.get("ok"):
            return f"Done: {action.description}"
        return f"Failed: {action.description} — {result.get('error','unknown error')}"


# ── Startup ───────────────────────────────────────────────────────────────────

async def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/default.yaml")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    cfg = load_config(args.config)
    agent = AIAgent(cfg)

    # Register signals
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _handle_signal, sig, None)

    log.info("[agent] AI OS Agent started — UID=%d", os.getuid() if hasattr(os, 'getuid') else -1)

    # Start the input socket listener (receives text from UI/voice)
    await asyncio.gather(
        _run_input_socket(agent, cfg),
        _shutdown.wait(),
    )
    log.info("[agent] Shutdown complete.")


import os

async def _run_input_socket(agent: AIAgent, cfg: dict):
    """
    Listens on a Unix socket for commands from the UI frontend.
    Each message: {"text": "...", "source": "HUMAN"|"AI_READ", "hmac": "..."}
    """
    socket_path = cfg.get("agent_socket", "/run/ai-os/agent.sock")
    Path(socket_path).parent.mkdir(parents=True, exist_ok=True)
    if Path(socket_path).exists():
        Path(socket_path).unlink()

    server = await asyncio.start_unix_server(
        lambda r, w: asyncio.create_task(_handle_client(agent, r, w)),
        path=socket_path,
    )
    os.chmod(socket_path, 0o660)
    log.info(f"[agent] Listening on {socket_path}")

    async with server:
        await _shutdown.wait()


import json

async def _handle_client(agent: AIAgent, reader, writer):
    try:
        raw = await asyncio.wait_for(reader.readline(), timeout=30.0)
        msg = json.loads(raw.decode())
        text   = msg.get("text", "")
        source = msg.get("source", "UNKNOWN")

        if not text:
            writer.write(b'{"ok":false,"error":"empty text"}\n')
        else:
            response = await agent.handle_text(text, source)
            writer.write((json.dumps({"ok": True, "response": response}) + "\n").encode())

        await writer.drain()
    except Exception as e:
        log.error(f"[agent] Client handler error: {e}")
    finally:
        writer.close()


if __name__ == "__main__":
    asyncio.run(main())
