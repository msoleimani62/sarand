"""Persisted, cross-platform user configuration for sarand.

A small JSON file in the OS-appropriate config directory, read on
every run and writable via ``sarand --set-output-dir``.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

CONFIG_FILE_NAME = "config.json"


def get_config_dir() -> Path:
    """Return the OS-appropriate config directory for sarand.

    - Linux:   $XDG_CONFIG_HOME/sarand or ~/.config/sarand
    - macOS:   ~/Library/Application Support/sarand
    - Windows: %APPDATA%/sarand
    """
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming")))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
    return base / "sarand"


def get_config_path() -> Path:
    return get_config_dir() / CONFIG_FILE_NAME


def load_persisted_config() -> dict[str, Any]:
    """Load the persisted config file. Never raises -- a broken/missing
    config file must not block a normal run."""
    path = get_config_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_persisted_config(updates: dict[str, Any]) -> Path:
    """Merge ``updates`` into the persisted config file and save it."""
    path = get_config_path()
    current = load_persisted_config()
    current.update(updates)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(current, indent=2, ensure_ascii=False), encoding="utf-8")
    return path
