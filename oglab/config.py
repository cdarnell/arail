"""OGLab — Configuration loader."""

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
MODELS_DIR = Path(get("OGLAB_MODELS_DIR", "./models"))
EXPERIMENTS_DIR = Path(get("OGLAB_EXPERIMENTS_DIR", "./experiments"))
