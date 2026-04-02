"""
snapshot.py — Btrfs Snapshot Manager

Takes pre-action snapshots and provides rollback.
Uses snapper (which handles the Btrfs subvolume mechanics).
Runs as UID 1001 but snapper is configured with sudo rules
to allow only 'snapper create' and 'snapper rollback' for this UID.
"""

import asyncio
import logging
import time
from pathlib import Path

log = logging.getLogger("ai-os.snapshots")


class SnapshotManager:
    def __init__(self, cfg: dict):
        self.enabled = cfg.get("snapshots", {}).get("enabled", True)
        self.config_name = cfg.get("snapshots", {}).get("snapper_config", "root")
        self._last_snapshot_num: int | None = None

    async def take(self, description: str) -> int | None:
        """Take a pre-action snapshot. Returns snapshot number or None."""
        if not self.enabled:
            return None
        desc = f"ai-os: {description}"[:80]
        try:
            proc = await asyncio.create_subprocess_exec(
                "sudo", "snapper", "-c", self.config_name,
                "create", "--description", desc, "--print-number",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10.0)
            num = int(stdout.decode().strip())
            self._last_snapshot_num = num
            log.info(f"[snapshot] Created #{num}: {desc}")
            return num
        except Exception as e:
            log.error(f"[snapshot] Failed to create snapshot: {e}")
            return None

    async def rollback(self, snapshot_num: int | None = None) -> bool:
        """Roll back to a snapshot number (or the last one taken)."""
        num = snapshot_num or self._last_snapshot_num
        if num is None:
            log.error("[snapshot] No snapshot to roll back to")
            return False
        try:
            proc = await asyncio.create_subprocess_exec(
                "sudo", "snapper", "-c", self.config_name,
                "rollback", str(num),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(proc.communicate(), timeout=30.0)
            log.info(f"[snapshot] Rolled back to #{num}")
            return proc.returncode == 0
        except Exception as e:
            log.error(f"[snapshot] Rollback failed: {e}")
            return False
