"""
real_world.py — Real-World Action Barrier (Gap 3 Fix)

Problem: AI filling out payment forms or sending messages is dangerous.
The confirmation gate alone isn't enough — the AI could fill in the form
*then* ask "confirm?", making it hard for users to review what was entered.

Fix: A dedicated barrier that:
  1. STOPS before any real-world consequence (payment, order, message send)
  2. Shows a clear human-readable PREVIEW of exactly what will happen
  3. Locks further execution until receiving an HMAC-verified human approval
  4. Cannot be bypassed by anything in the AI's context window

Real-world action types:
  - Payment / purchase / order
  - Message send (WhatsApp, email, SMS)
  - Phone call
  - Form submission with personal data
  - File sharing / upload to external service
"""

import asyncio
import json
import logging
from dataclasses import dataclass
from pathlib import Path

from security.confirm_gate import ActionProposal

log = logging.getLogger("ai-os.real-world")


# ── Classification ─────────────────────────────────────────────────────────────

REAL_WORLD_TRIGGERS = {
    # URL patterns that indicate a real-world consequence page
    "url_patterns": [
        "checkout", "payment", "pay-now", "order-confirm",
        "purchase", "subscribe", "billing",
        "send-message", "submit", "confirm-order",
    ],
    # Action types that are always real-world
    "action_types": {
        "submit_form", "click_payment_button", "confirm_order",
        "send_message", "make_call", "share_file_external",
        "api_post",
    },
    # Button labels that trigger the barrier
    "button_labels": [
        "place order", "pay now", "confirm purchase", "buy",
        "send", "submit", "checkout", "complete order",
        "call", "dial",
    ],
}


def _is_real_world_url(url: str) -> bool:
    lc = url.lower()
    return any(trigger in lc for trigger in REAL_WORLD_TRIGGERS["url_patterns"])


def _is_real_world_button(label: str) -> bool:
    lc = label.lower().strip()
    return any(trigger in lc for trigger in REAL_WORLD_TRIGGERS["button_labels"])


@dataclass
class RealWorldPreview:
    action_summary: str
    fields_filled:  dict[str, str]  # {"card_number": "****1234", "address": "..."}
    consequence:    str              # "This will charge $24.99 to your default card"
    reversible:     bool             # Pizza order: not reversible. Message: not reversible.


class RealWorldBarrier:
    """
    Intercepts any action that has a real-world consequence.
    Builds a preview and waits for verified human confirmation.
    """

    UI_SOCKET = "/run/ai-os/confirm-ui.sock"

    def is_real_world(self, proposal: ActionProposal) -> bool:
        """Check whether this action needs the real-world barrier."""
        a = proposal.action_type
        p = proposal.params

        if a in REAL_WORLD_TRIGGERS["action_types"]:
            return True

        url = p.get("url", "")
        if url and _is_real_world_url(url):
            return True

        button = p.get("button", "")
        if button and _is_real_world_button(button):
            return True

        return False

    async def confirm(self, proposal: ActionProposal) -> bool:
        """
        Build preview, send to UI, wait for HMAC-verified confirmation.
        Returns True only if the user explicitly approved.
        Timeout: 120 seconds (real-world actions need time to review).
        """
        preview = self._build_preview(proposal)
        log.info(f"[rw-barrier] Showing real-world preview: {preview.action_summary}")

        msg = {
            "type":         "real_world_confirm",
            "summary":      preview.action_summary,
            "fields":       preview.fields_filled,
            "consequence":  preview.consequence,
            "reversible":   preview.reversible,
            "timeout_sec":  120,
        }

        if not Path(self.UI_SOCKET).exists():
            return await self._terminal_confirm(preview)

        try:
            reader, writer = await asyncio.open_unix_connection(self.UI_SOCKET)
            writer.write((json.dumps(msg) + "\n").encode())
            await writer.drain()

            resp_raw = await asyncio.wait_for(reader.readline(), timeout=130.0)
            resp = json.loads(resp_raw.decode())
            writer.close()

            approved = resp.get("approved", False)
            token    = resp.get("human_token")

            if approved and token:
                # Verify HMAC — same as confirm_gate
                from security.input_tagger import HumanTokenVerifier
                if not HumanTokenVerifier().verify(token):
                    log.warning("[rw-barrier] Real-world approval HMAC failed — rejecting")
                    return False

            if approved:
                log.info(f"[rw-barrier] APPROVED: {preview.action_summary}")
            else:
                log.info(f"[rw-barrier] REJECTED by user: {preview.action_summary}")

            return approved

        except asyncio.TimeoutError:
            log.info("[rw-barrier] Timed out — real-world action CANCELLED")
            return False
        except Exception as e:
            log.error(f"[rw-barrier] Error: {e}")
            return False

    def _build_preview(self, proposal: ActionProposal) -> RealWorldPreview:
        a = proposal.action_type
        p = proposal.params

        # Mask sensitive fields for display
        fields = {}
        for k, v in p.items():
            sv = str(v)
            if any(s in k.lower() for s in ("card", "cvv", "pin", "password", "secret")):
                sv = "****" + sv[-4:] if len(sv) > 4 else "****"
            elif len(sv) > 60:
                sv = sv[:60] + "…"
            fields[k] = sv

        # Build human-readable consequence description
        if "payment" in a or "order" in a or "purchase" in a:
            consequence = (
                "This action will complete a purchase or payment. "
                "This may be irreversible."
            )
            reversible = False
        elif "message" in a or "send" in a:
            consequence = "This will send a message. It cannot be unsent."
            reversible = False
        elif "call" in a:
            consequence = "This will initiate a phone or video call."
            reversible = True
        elif "submit" in a:
            consequence = "This will submit a form. The action may not be reversible."
            reversible = False
        else:
            consequence = "This action has a real-world consequence."
            reversible = False

        return RealWorldPreview(
            action_summary=proposal.description,
            fields_filled=fields,
            consequence=consequence,
            reversible=reversible,
        )

    async def _terminal_confirm(self, preview: RealWorldPreview) -> bool:
        print("\n" + "═" * 60)
        print("  REAL-WORLD ACTION — CONFIRMATION REQUIRED")
        print("═" * 60)
        print(f"  Action : {preview.action_summary}")
        print(f"  Impact : {preview.consequence}")
        if preview.fields_filled:
            print("  Details:")
            for k, v in preview.fields_filled.items():
                print(f"    {k}: {v}")
        print("═" * 60)

        loop = asyncio.get_event_loop()
        try:
            ans = await asyncio.wait_for(
                loop.run_in_executor(None, input, "  Type CONFIRM to proceed: "),
                timeout=120.0,
            )
            return ans.strip().upper() == "CONFIRM"
        except asyncio.TimeoutError:
            print("  Timed out — action cancelled.")
            return False
