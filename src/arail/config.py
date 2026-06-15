"""Arail — Configuration loader and runtime paths.

Runtime layout (all relative to the repo root by default):

    lab/
      data/      runtime state: activity.jsonl, goals/, consent/, experiments/, cache/
      models/    downloaded model weights
      pkb/       personal knowledge base tree

Every location is overridable via env var, so deployments can split runtime
state across disks without touching code.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

_log = logging.getLogger(__name__)


def get(key: str, default: str | None = None) -> str | None:
    return os.getenv(key, default)


# Re-export the canonical mode helpers from arail.airgap.
# Any module that was doing its own os.getenv("LAB_MODE", ...) dance
# should import from here (or from arail.airgap directly) instead.
from arail.airgap import lab_mode, is_airgapped  # noqa: E402

MODE = get("ARAIL_MODE", "airgapped")
MODEL_BACKEND = get("MODEL_BACKEND", "auto")
MODEL_NAME = get("MODEL_NAME", "")
LOCAL_API_PORT = int(get("LOCAL_API_PORT", "8000"))


def _resolve(env_key: str, default_rel: str) -> Path:
    raw = os.getenv(env_key)
    if raw:
        return Path(raw).expanduser()
    return Path(default_rel)


def _resolve_pkb_root(default_rel: str) -> Path:
    """Resolve the Personal Knowledge Base root.

    Accepts ``LAB_PKB`` (preferred) or ``LAB_PKM`` (legacy). If only the
    legacy variable is set, a one-time deprecation warning fires so users
    know to update their ``.env``. Paths are tilde-expanded.
    """
    new = os.getenv("LAB_PKB")
    old = os.getenv("LAB_PKM")
    if new:
        return Path(new).expanduser()
    if old:
        _log.warning(
            "LAB_PKM is deprecated — rename to LAB_PKB in your .env. "
            "The old name still works for now."
        )
        return Path(old).expanduser()
    return Path(default_rel)


LAB_ROOT = _resolve("LAB_ROOT", "lab")
DATA_DIR = _resolve("ARAIL_DATA_DIR", str(LAB_ROOT / "data"))
MODELS_DIR = _resolve("ARAIL_MODELS_DIR", str(LAB_ROOT / "models"))
WORLDS_DIR = _resolve("ARAIL_WORLDS_DIR", str(LAB_ROOT / "worlds"))
PKB_ROOT = _resolve_pkb_root(str(LAB_ROOT / "pkb"))
EXPERIMENTS_DIR = _resolve("ARAIL_EXPERIMENTS_DIR", str(DATA_DIR / "experiments"))

# Backwards-compatible alias so existing `from arail.config import PKM_ROOT`
# call sites keep working. Will be removed in a future release.
PKM_ROOT = PKB_ROOT
