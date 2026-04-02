"""
core/config.py — loads config/default.yaml or config/low_ram.yaml
based on RAM, then merges config/active_model.yaml if present.
"""
from __future__ import annotations
import os
import yaml
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
CONFIG_DIR = REPO_ROOT / "config"


def _total_ram_mb() -> int:
    with open("/proc/meminfo") as f:
        for line in f:
            if line.startswith("MemTotal"):
                return int(line.split()[1]) // 1024
    return 0


def load() -> dict:
    ram = _total_ram_mb()
    cfg_file = CONFIG_DIR / ("default.yaml" if ram >= 7500 else "low_ram.yaml")
    with open(cfg_file) as f:
        cfg: dict = yaml.safe_load(f)

    # Merge active model override (written by install/03_ai_brain.sh)
    override = CONFIG_DIR / "active_model.yaml"
    if override.exists():
        with open(override) as f:
            cfg.update(yaml.safe_load(f))

    cfg["_ram_mb"] = ram
    cfg["_config_file"] = str(cfg_file)
    return cfg


# Singleton
_cfg: dict | None = None


def get() -> dict:
    global _cfg
    if _cfg is None:
        _cfg = load()
    return _cfg
