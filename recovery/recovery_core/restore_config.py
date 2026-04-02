"""
recovery/recovery_core/restore_config.py
Restores AI OS configuration files from a Btrfs snapshot.
Part of the immutable recovery core — no LLM dependency.
"""
from __future__ import annotations
import logging
import shutil
import subprocess
from pathlib import Path

log = logging.getLogger("restore_config")

CONFIG_DIR = Path("/opt/ai-os/config")
BACKUP_DIR = Path("/var/lib/ai-agent/config_backup")


def backup_current() -> bool:
    """Save current config to backup dir before overwriting."""
    try:
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        for f in CONFIG_DIR.glob("*.yaml"):
            shutil.copy2(f, BACKUP_DIR / f.name)
        log.info("restore_config: config backed up to %s", BACKUP_DIR)
        return True
    except Exception as e:
        log.error("restore_config: backup failed: %s", e)
        return False


def restore_from_snapshot(snapshot_id: str) -> dict:
    """
    Restore only the /opt/ai-os/config/ directory from a named snapshot.
    Does NOT rollback the entire filesystem (use snapshot.rollback for that).
    """
    backup_current()
    try:
        result = subprocess.run(
            ["snapper", "-c", "ai-os", "undochange",
             f"{snapshot_id}..0", str(CONFIG_DIR)],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            log.info("restore_config: config restored from snapshot #%s", snapshot_id)
            return {"success": True,
                    "message": f"Config restored from snapshot #{snapshot_id}."}
        else:
            return {"success": False, "message": result.stderr}
    except Exception as e:
        return {"success": False, "message": str(e)}


def restore_from_backup() -> dict:
    """Restore config from the last local backup."""
    try:
        for f in BACKUP_DIR.glob("*.yaml"):
            shutil.copy2(f, CONFIG_DIR / f.name)
        return {"success": True, "message": "Config restored from local backup."}
    except Exception as e:
        return {"success": False, "message": str(e)}
