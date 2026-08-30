"""
Module: runner_env
Role: load KEY=VALUE pairs from the sibling .env file into os.environ before
      anything else in claude-runner.py reads configuration.
Uses: os, pathlib

Used by:
  - claude-runner.py
"""

import os
from pathlib import Path


def load_env() -> None:
    """Load KEY=VALUE pairs from .env file next to this script into os.environ.

    Uses setdefault so existing env vars win (e.g., systemd EnvironmentFile).
    """
    env_path = Path(__file__).parent / ".env"
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)
