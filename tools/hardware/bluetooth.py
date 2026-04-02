"""
tools/hardware/bluetooth.py — Bluetooth Repair Tool
Same structured pattern: diagnose (read-only) → plan → gate → execute.
"""

import asyncio
import logging
from dataclasses import dataclass
from enum import Enum, auto

log = logging.getLogger("ai-os.hardware.bluetooth")


class BTState(Enum):
    SERVICE_DOWN     = auto()
    RFKILL_BLOCKED   = auto()
    ADAPTER_DOWN     = auto()
    DRIVER_MISSING   = auto()
    ALREADY_WORKING  = auto()


@dataclass
class BTDiagnosis:
    state:     BTState
    issues:    list[str]
    suggestions: list[str]


@dataclass
class RepairStep:
    description: str
    action_type: str
    params:      dict
    risk_level:  str
    reversible:  bool


class BluetoothTool:
    async def diagnose(self) -> BTDiagnosis:
        issues, suggestions = [], []

        if await self._is_rfkill_blocked():
            issues.append("Bluetooth blocked by rfkill")
            suggestions.append("rfkill unblock bluetooth")

        if not await self._check_service("bluetooth"):
            issues.append("bluetooth.service not running")
            suggestions.append("systemctl start bluetooth")

        if not await self._check_adapter():
            issues.append("No Bluetooth adapter found (hciconfig)")
            suggestions.append("Check: dmesg | grep -i bluetooth")

        if not issues:
            return BTDiagnosis(state=BTState.ALREADY_WORKING, issues=[], suggestions=[])

        return BTDiagnosis(
            state=BTState.RFKILL_BLOCKED if "rfkill" in issues[0] else BTState.SERVICE_DOWN,
            issues=issues, suggestions=suggestions,
        )

    def build_repair_plan(self, diagnosis: BTDiagnosis) -> list[RepairStep]:
        if diagnosis.state == BTState.ALREADY_WORKING:
            return []
        steps = []
        if diagnosis.state == BTState.RFKILL_BLOCKED:
            steps.append(RepairStep(
                description="Unblock Bluetooth via rfkill",
                action_type="run_command",
                params={"command": "rfkill unblock bluetooth"},
                risk_level="CONFIRM", reversible=True,
            ))
        steps.append(RepairStep(
            description="Restart Bluetooth service",
            action_type="run_command",
            params={"command": "systemctl restart bluetooth"},
            risk_level="CONFIRM", reversible=True,
        ))
        steps.append(RepairStep(
            description="Bring up Bluetooth adapter",
            action_type="run_command",
            params={"command": "hciconfig hci0 up"},
            risk_level="CONFIRM", reversible=True,
        ))
        return steps

    def format_diagnosis_for_user(self, d: BTDiagnosis) -> str:
        if d.state == BTState.ALREADY_WORKING:
            return "Bluetooth appears to be working."
        return "Bluetooth issues:\n" + "\n".join(f"  • {i}" for i in d.issues)

    async def _is_rfkill_blocked(self) -> bool:
        try:
            proc = await asyncio.create_subprocess_exec(
                "rfkill", "list", "bluetooth",
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
            )
            stdout, _ = await proc.communicate()
            return b"blocked: yes" in stdout
        except Exception:
            return False

    async def _check_service(self, name: str) -> bool:
        try:
            proc = await asyncio.create_subprocess_exec(
                "systemctl", "is-active", "--quiet", name,
                stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
            )
            await proc.communicate()
            return proc.returncode == 0
        except Exception:
            return False

    async def _check_adapter(self) -> bool:
        try:
            proc = await asyncio.create_subprocess_exec(
                "hciconfig",
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
            )
            stdout, _ = await proc.communicate()
            return b"hci" in stdout
        except Exception:
            return False
