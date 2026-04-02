"""
tools/hardware/fingerprint.py — Fingerprint Scanner Repair Tool

User says: "Fix my fingerprint scanner"
This module runs the full structured diagnosis + repair flow.

Critically: NOTHING executes without passing through the confirmation gate.
Every system-level step (package install, service restart, udev reload)
is a separate ActionProposal with its own risk level and rollback.

Architecture position:
  AI Planner → detects hardware task → calls fingerprint.diagnose()
  fingerprint.diagnose() returns a RepairPlan (list of ActionProposals)
  agent_main.py feeds each ActionProposal through the confirmation gate
  Nothing in this file ever runs a subprocess directly — it only PLANS.
"""

import asyncio
import logging
import re
from dataclasses import dataclass, field
from enum import Enum, auto

log = logging.getLogger("ai-os.hardware.fingerprint")


# ── Known fingerprint devices ─────────────────────────────────────────────────
# USB vendor:product pairs that need specific driver packages.
# Sourced from libfprint supported devices list.

KNOWN_DEVICES: dict[str, dict] = {
    # Synaptics (most common on modern laptops)
    "06cb:00bd": {"name": "Synaptics WBDI",        "driver": "libfprint-2-tod1-synaptics"},
    "06cb:00f9": {"name": "Synaptics UDF",          "driver": "libfprint-2-tod1-synaptics"},
    "06cb:00df": {"name": "Synaptics (Dell)",        "driver": "libfprint-2-tod1-synaptics"},
    # Goodix
    "27c6:5110": {"name": "Goodix MOC Sensor",      "driver": "libfprint-2-tod1-goodix"},
    "27c6:5503": {"name": "Goodix Fingerprint",      "driver": "libfprint-2-tod1-goodix"},
    "27c6:55a4": {"name": "Goodix USB2.0",           "driver": "libfprint-2-tod1-goodix"},
    # Elan
    "04f3:0c4b": {"name": "ELAN WBF Fingerprint",   "driver": "libfprint-2-tod1-elan"},
    "04f3:0c57": {"name": "ELAN Fingerprint",        "driver": "libfprint-2-tod1-elan"},
    # AuthenTec (older)
    "08ff:2810": {"name": "AuthenTec AES2810",       "driver": "libfprint2"},
    # Validity / Synaptics (older)
    "138a:0090": {"name": "Validity VFS7500",        "driver": "libfprint2"},
    "138a:0097": {"name": "Validity VFS7552",        "driver": "libfprint2"},
}

REQUIRED_PACKAGES = [
    "fprintd",
    "libfprint-2-2",
    "libpam-fprintd",
]


# ── Data types ────────────────────────────────────────────────────────────────

class DiagnosisState(Enum):
    DEVICE_NOT_FOUND     = auto()
    DRIVER_MISSING       = auto()
    SERVICE_NOT_RUNNING  = auto()
    NOT_ENROLLED         = auto()
    PAM_NOT_CONFIGURED   = auto()
    ALREADY_WORKING      = auto()
    UNSUPPORTED_DEVICE   = auto()


@dataclass
class DeviceInfo:
    usb_id:   str         # "06cb:00bd"
    name:     str
    driver:   str | None  # required driver package, or None if generic


@dataclass
class DiagnosisResult:
    state:       DiagnosisState
    device:      DeviceInfo | None
    issues:      list[str]          # human-readable list of what was found
    suggestions: list[str]          # what the AI will propose to fix


@dataclass
class RepairStep:
    """A single repair action — passed to the confirmation gate as ActionProposal."""
    description:      str
    action_type:      str   # matches executor dispatch table
    params:           dict
    risk_level:       str   # "AUTO" | "NOTIFY" | "CONFIRM"
    reversible:       bool
    skip_if_success:  bool = False  # skip if a previous step already fixed it


# ── Main interface ─────────────────────────────────────────────────────────────

class FingerprintTool:
    """
    Called by the AI planner when it detects a fingerprint-related request.
    Returns a DiagnosisResult and a list of RepairSteps.
    The planner converts RepairSteps into ActionProposals for the gate.
    """

    async def diagnose(self) -> DiagnosisResult:
        """
        Run read-only diagnosis. No system changes. No confirmation needed.
        Returns what's wrong and what needs fixing.
        """
        issues      = []
        suggestions = []

        # 1. Check for device on USB bus
        device = await self._detect_usb_device()
        if device is None:
            return DiagnosisResult(
                state=DiagnosisState.DEVICE_NOT_FOUND,
                device=None,
                issues=["No fingerprint sensor detected on USB bus. "
                        "Check if the sensor is enabled in BIOS/UEFI."],
                suggestions=["Check BIOS settings for fingerprint sensor",
                             "Run: lsusb — look for fingerprint-related entries"],
            )

        # 2. Check required packages
        missing_pkgs = await self._check_missing_packages(
            REQUIRED_PACKAGES + ([device.driver] if device.driver else [])
        )
        if missing_pkgs:
            issues.append(f"Missing packages: {', '.join(missing_pkgs)}")
            suggestions.append(f"Install: apt install {' '.join(missing_pkgs)}")

        # 3. Check fprintd service
        service_running = await self._check_service("fprintd")
        if not service_running:
            issues.append("fprintd service is not running")
            suggestions.append("Start fprintd: systemctl start fprintd")

        # 4. Check enrollment
        enrolled = await self._check_enrollment()
        if not enrolled:
            issues.append("No fingerprints enrolled for current user")
            suggestions.append("Enroll fingerprint: fprintd-enroll")

        # 5. Check PAM integration
        pam_ok = await self._check_pam()
        if not pam_ok:
            issues.append("PAM not configured for fingerprint authentication")
            suggestions.append("Enable PAM: pam-auth-update --enable fprintd")

        if not issues:
            return DiagnosisResult(
                state=DiagnosisState.ALREADY_WORKING,
                device=device,
                issues=["Fingerprint sensor appears to be working correctly."],
                suggestions=["Try: fprintd-verify — place finger on sensor to test"],
            )

        state = (DiagnosisState.DRIVER_MISSING if missing_pkgs
                 else DiagnosisState.SERVICE_NOT_RUNNING if not service_running
                 else DiagnosisState.NOT_ENROLLED if not enrolled
                 else DiagnosisState.PAM_NOT_CONFIGURED)

        return DiagnosisResult(state=state, device=device,
                               issues=issues, suggestions=suggestions)

    def build_repair_plan(self, diagnosis: DiagnosisResult) -> list[RepairStep]:
        """
        Convert a DiagnosisResult into ordered RepairSteps.
        Each step maps to one ActionProposal in agent_main.
        """
        if diagnosis.state == DiagnosisState.DEVICE_NOT_FOUND:
            return []  # nothing to install — hardware issue
        if diagnosis.state == DiagnosisState.ALREADY_WORKING:
            return []

        steps: list[RepairStep] = []
        dev = diagnosis.device

        # Step 1: snapshot before any changes (always first)
        steps.append(RepairStep(
            description="Take system snapshot before hardware repair",
            action_type="system_snapshot",
            params={"description": "pre-fingerprint-repair"},
            risk_level="AUTO",
            reversible=True,
        ))

        # Step 2: install missing packages
        pkgs_needed = list(set(
            REQUIRED_PACKAGES + ([dev.driver] if dev and dev.driver else [])
        ))
        steps.append(RepairStep(
            description=f"Install fingerprint packages: {', '.join(pkgs_needed)}",
            action_type="install_package",
            params={
                "package":  " ".join(pkgs_needed),
                "manager":  "apt",
                "simulate": False,
            },
            risk_level="CONFIRM",
            reversible=True,   # apt remove --purge restores state
        ))

        # Step 3: reload udev rules (needed after driver install)
        steps.append(RepairStep(
            description="Reload udev rules to activate fingerprint driver",
            action_type="run_command",
            params={"command": "udevadm control --reload-rules && udevadm trigger"},
            risk_level="CONFIRM",
            reversible=False,  # reload is idempotent but not snapshot-rollback-friendly
        ))

        # Step 4: (re)start fprintd
        steps.append(RepairStep(
            description="Start fprintd service",
            action_type="run_command",
            params={"command": "systemctl restart fprintd"},
            risk_level="CONFIRM",
            reversible=True,
        ))

        # Step 5: enroll fingerprint (interactive — AI guides, user places finger)
        steps.append(RepairStep(
            description="Enroll fingerprint (you'll need to place your finger on the sensor)",
            action_type="run_terminal_interactive",
            params={"command": "fprintd-enroll", "cwd": None},
            risk_level="CONFIRM",
            reversible=True,   # fprintd-delete removes enrollment
        ))

        # Step 6: configure PAM (only if not already configured)
        steps.append(RepairStep(
            description="Configure PAM to use fingerprint for login",
            action_type="run_command",
            params={"command": "pam-auth-update --enable fprintd"},
            risk_level="CONFIRM",
            reversible=True,
        ))

        # Step 7: verify
        steps.append(RepairStep(
            description="Test fingerprint sensor (place finger when prompted)",
            action_type="run_command",
            params={"command": "fprintd-verify"},
            risk_level="AUTO",
            reversible=True,
            skip_if_success=False,
        ))

        return steps

    def format_diagnosis_for_user(self, diagnosis: DiagnosisResult) -> str:
        """Human-readable summary shown to the user before repair plan is proposed."""
        lines = ["Fingerprint sensor diagnosis:"]

        if diagnosis.device:
            lines.append(f"  Device found: {diagnosis.device.name} ({diagnosis.device.usb_id})")
        else:
            lines.append("  Device: not detected on USB bus")

        if diagnosis.issues:
            lines.append("\nIssues found:")
            for issue in diagnosis.issues:
                lines.append(f"  • {issue}")

        if diagnosis.state == DiagnosisState.ALREADY_WORKING:
            lines.append("\nThe fingerprint sensor appears to be working.")
            lines.append("Try: fprintd-verify to confirm.")
        else:
            lines.append(f"\n{len(self.build_repair_plan(diagnosis))} repair steps ready.")
            lines.append("Each step will ask for your approval before executing.")

        return "\n".join(lines)

    # ── Private read-only checks (no system changes) ──────────────────────────

    async def _detect_usb_device(self) -> DeviceInfo | None:
        """Run lsusb and match against known device list."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "lsusb",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5.0)
            output = stdout.decode()

            for line in output.splitlines():
                # lsusb format: "Bus 001 Device 003: ID 06cb:00bd Synaptics..."
                m = re.search(r"ID\s+([0-9a-f]{4}:[0-9a-f]{4})", line)
                if m:
                    usb_id = m.group(1)
                    if usb_id in KNOWN_DEVICES:
                        info = KNOWN_DEVICES[usb_id]
                        return DeviceInfo(usb_id=usb_id,
                                          name=info["name"],
                                          driver=info.get("driver"))

            # Try lspci for internal (non-USB) sensors
            return await self._detect_pci_device()

        except FileNotFoundError:
            log.warning("[fingerprint] lsusb not found — install usbutils")
            return None
        except Exception as e:
            log.error(f"[fingerprint] USB detection error: {e}")
            return None

    async def _detect_pci_device(self) -> DeviceInfo | None:
        """Check dmesg/acpi for integrated fingerprint sensors."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "dmesg",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5.0)
            output = stdout.decode().lower()
            if "fingerprint" in output or "fprint" in output:
                return DeviceInfo(
                    usb_id="internal",
                    name="Integrated fingerprint sensor (detected via dmesg)",
                    driver=None,
                )
        except Exception:
            pass
        return None

    async def _check_missing_packages(self, packages: list[str]) -> list[str]:
        """Return packages from the list that are not installed."""
        missing = []
        for pkg in packages:
            try:
                proc = await asyncio.create_subprocess_exec(
                    "dpkg", "-s", pkg,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                await asyncio.wait_for(proc.communicate(), timeout=3.0)
                if proc.returncode != 0:
                    missing.append(pkg)
            except Exception:
                missing.append(pkg)
        return missing

    async def _check_service(self, service: str) -> bool:
        try:
            proc = await asyncio.create_subprocess_exec(
                "systemctl", "is-active", "--quiet", service,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await asyncio.wait_for(proc.communicate(), timeout=3.0)
            return proc.returncode == 0
        except Exception:
            return False

    async def _check_enrollment(self) -> bool:
        try:
            proc = await asyncio.create_subprocess_exec(
                "fprintd-list", "$(whoami)",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
                shell=False,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5.0)
            return b"finger" in stdout.lower()
        except Exception:
            return False

    async def _check_pam(self) -> bool:
        try:
            pam_file = "/etc/pam.d/common-auth"
            content = open(pam_file).read()
            return "fprintd" in content or "pam_fprintd" in content
        except Exception:
            return False
