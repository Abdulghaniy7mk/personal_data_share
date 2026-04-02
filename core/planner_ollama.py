"""
core/planner_ollama.py — Ollama-backed Planner

Drop-in replacement for planner.py when using Ollama instead of
llama-cpp-python directly. Ollama handles model loading, quantization,
and GPU offloading automatically — much simpler to set up.

Activated when config has: planner.backend = "ollama"
"""

import json
import logging
import re

import httpx  # async HTTP — pip install httpx

from security.confirm_gate import ActionProposal, RiskLevel
from core.context_firewall import MemoryEntry

log = logging.getLogger("ai-os.planner-ollama")

VALID_ACTION_TYPES = {
    "launch_app", "type_in_app", "click_in_app",
    "open_file", "run_command", "browse_url",
    "install_package", "submit_form",
    "send_message", "make_call",
    "read_screen", "observe",
}

ACTION_RISK_DEFAULTS: dict[str, RiskLevel] = {
    "launch_app":      RiskLevel.AUTO,
    "type_in_app":     RiskLevel.AUTO,
    "click_in_app":    RiskLevel.AUTO,
    "open_file":       RiskLevel.AUTO,
    "run_command":     RiskLevel.CONFIRM,
    "browse_url":      RiskLevel.NOTIFY,
    "install_package": RiskLevel.CONFIRM,
    "submit_form":     RiskLevel.CONFIRM,
    "send_message":    RiskLevel.CONFIRM,
    "make_call":       RiskLevel.CONFIRM,
    "read_screen":     RiskLevel.AUTO,
    "observe":         RiskLevel.AUTO,
}

SYSTEM_PROMPT = """You are the planning module of an AI OS agent.
Convert the user's request into a JSON array of actions.
Each action must follow this schema exactly:

{"action_type": "<type>", "params": {...}, "description": "<human-readable>", "reversible": true/false}

Valid action_types: launch_app, type_in_app, click_in_app, open_file,
run_command, browse_url, install_package, submit_form, send_message,
make_call, read_screen, observe.

Rules:
- Never include shell metacharacters (|, &, ;) in params unless action_type is run_command
- For run_command: single safe command only, no pipes to bash
- Prefer GUI actions (launch_app, click_in_app) over terminal commands
- Respond ONLY with the JSON array — no markdown, no explanation

User preferences context:
{context}"""


class OllamaPlanner:
    def __init__(self, cfg: dict):
        planner_cfg    = cfg.get("planner", {})
        self.model     = planner_cfg.get("ollama_model", "phi3:mini")
        self.host      = planner_cfg.get("ollama_host", "http://localhost:11434")
        self.ctx_len   = planner_cfg.get("ctx_len", 4096)
        self.temp      = planner_cfg.get("temperature", 0.1)

    async def plan(self, user_text: str, context: list[MemoryEntry],
                   source: str) -> list[ActionProposal]:
        ctx_str = self._format_context(context)
        system  = SYSTEM_PROMPT.replace("{context}", ctx_str)

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    f"{self.host}/api/chat",
                    json={
                        "model":  self.model,
                        "stream": False,
                        "options": {
                            "temperature": self.temp,
                            "num_ctx":     self.ctx_len,
                        },
                        "messages": [
                            {"role": "system", "content": system},
                            {"role": "user",   "content": user_text},
                        ],
                    },
                )
                resp.raise_for_status()
                data    = resp.json()
                content = data["message"]["content"]
                return self._parse_actions(content)

        except httpx.ConnectError:
            log.error("[ollama] Cannot connect to Ollama. Is ollama service running?")
            log.error("Run: systemctl start ollama")
            return self._stub_plan(user_text)
        except Exception as e:
            log.error(f"[ollama] Error: {e}")
            return []

    def _parse_actions(self, raw: str) -> list[ActionProposal]:
        raw = re.sub(r"```[a-z]*", "", raw).strip().strip("`")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            # Try to extract JSON array from response
            m = re.search(r"\[.*\]", raw, re.DOTALL)
            if m:
                try:
                    data = json.loads(m.group())
                except Exception:
                    log.error(f"[ollama] Could not parse JSON: {raw[:200]}")
                    return []
            else:
                log.error(f"[ollama] No JSON array in response: {raw[:200]}")
                return []

        if not isinstance(data, list):
            data = [data]

        proposals = []
        for item in data:
            atype = item.get("action_type", "")
            if atype not in VALID_ACTION_TYPES:
                log.warning(f"[ollama] Unknown action_type '{atype}' — skipped")
                continue
            proposals.append(ActionProposal(
                action_type=atype,
                params=item.get("params", {}),
                description=item.get("description", atype),
                risk_level=ACTION_RISK_DEFAULTS.get(atype, RiskLevel.CONFIRM),
                reversible=item.get("reversible", True),
            ))
        return proposals

    def _format_context(self, entries: list[MemoryEntry]) -> str:
        if not entries:
            return "No stored preferences."
        return "\n".join(f"- {e.content}" for e in entries[:8])

    def _stub_plan(self, text: str) -> list[ActionProposal]:
        """Fallback when Ollama is unavailable."""
        tl = text.lower().strip()
        if tl.startswith(("open ", "launch ", "start ")):
            app = text.split(None, 1)[1].strip() if len(text.split()) > 1 else ""
            if app:
                return [ActionProposal(
                    action_type="launch_app",
                    params={"app": app},
                    description=f"Launch {app}",
                    risk_level=RiskLevel.AUTO,
                    reversible=True,
                )]
        return []
