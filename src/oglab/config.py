"""OGLab — Configuration loader and runtime paths.

Runtime layout (all relative to the repo root by default):

    lab/
      data/      runtime state: activity.jsonl, goals/, consent/, experiments/, cache/
      models/    downloaded model weights
      pkm/       personal knowledge management tree

Every location is overridable via env var, so deployments can split runtime
state across disks without touching code.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def get(key: str, default: str | None = None) -> str | None:
    return os.getenv(key, default)


MODE = get("OGLAB_MODE", "airgapped")
MODEL_BACKEND = get("MODEL_BACKEND", "auto")
MODEL_NAME = get("MODEL_NAME", "")
LOCAL_API_PORT = int(get("LOCAL_API_PORT", "8000"))


def _resolve(env_key: str, default_rel: str) -> Path:
    raw = os.getenv(env_key)
    if raw:
        return Path(raw).expanduser()
    return Path(default_rel)


LAB_ROOT = _resolve("LAB_ROOT", "lab")
DATA_DIR = _resolve("OGLAB_DATA_DIR", str(LAB_ROOT / "data"))
MODELS_DIR = _resolve("OGLAB_MODELS_DIR", str(LAB_ROOT / "models"))
PKM_ROOT = _resolve("LAB_PKM", str(LAB_ROOT / "pkm"))
EXPERIMENTS_DIR = _resolve("OGLAB_EXPERIMENTS_DIR", str(DATA_DIR / "experiments"))
