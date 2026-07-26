"""ARAIL's model defaults — the one file to check for what's active.

Historically "which model does chat use by default" and "which model
does AeroLLM load" were each answered by a chain of .env vars, hardcoded
fallback constants, and installed-model detection spread across
app.py/router/backends.py — nobody could answer "what's active" without
reading code. `model_defaults.yaml` (repo root, gitignored, per-machine
like .env — see model_defaults.yaml.example) is now the single,
authoritative source for these two settings.

Deliberately NOT a rewrite of the ~30 call sites that read MODEL_NAME /
AEROLLM_MODEL: `apply()` stamps this file's values into those SAME env
vars, once, at import — every existing reader sees the new source of
truth for free, and nothing downstream needs to change. A missing or
malformed file is not an error; it just means nothing is overridden and
today's .env-based defaults keep working exactly as before.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

_log = logging.getLogger(__name__)

# CWD-relative, matching config.py's convention for .env/lab.conf/etc. —
# every ARAIL entry point (start.sh, the launchd plist's WorkingDirectory,
# pytest's rootdir) already runs with CWD at the repo root.
_DEFAULT_PATH = Path("model_defaults.yaml")


def apply(path: Path | None = None) -> dict[str, Any]:
    """Load model_defaults.yaml (if present) and stamp its values into
    os.environ. Returns what it found (possibly empty); never raises.

    - default_a → MODEL_NAME (Chat Studio's Box A / primary model)
    - default_b → AEROLLM_MODEL (Box B / AeroLLM's deep model)

    An explicit `null`/blank default_b clears any .env-set AEROLLM_MODEL
    rather than leaving a stale value able to silently win — "not
    configured" must stay honestly "not configured".

    Path resolution, mirroring config.py's ARAIL_ENV_FILE pattern exactly
    (same bug class, same fix): ``ARAIL_MODEL_DEFAULTS_FILE`` overrides
    the default CWD-relative lookup when set. Without this, importing
    arail.config in a test process would hydrate whatever's on THIS
    machine's real model_defaults.yaml into every test — the exact
    "developer's real .env leaks into the test suite" bug that
    ARAIL_ENV_FILE / tests/conftest.py's session-level isolation already
    exists to prevent for .env. `path=` (explicit arg) always wins over
    both, for direct unit tests.
    """
    if path is not None:
        p = path
    else:
        override = os.getenv("ARAIL_MODEL_DEFAULTS_FILE", "").strip()
        p = Path(override) if override else _DEFAULT_PATH
    if not p.exists():
        return {}
    try:
        import yaml
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except Exception as e:  # noqa: BLE001 — a bad file must never block boot
        _log.warning("model_defaults: failed to read %s: %s", p, e)
        return {}
    if not isinstance(data, dict):
        _log.warning("model_defaults: %s did not parse to a mapping — ignoring", p)
        return {}

    result: dict[str, Any] = {}

    default_a = data.get("default_a")
    if default_a:
        os.environ["MODEL_NAME"] = str(default_a)
        result["default_a"] = str(default_a)

    if "default_b" in data:
        default_b = data.get("default_b")
        if default_b:
            os.environ["AEROLLM_MODEL"] = str(default_b)
            result["default_b"] = str(default_b)
        else:
            os.environ.pop("AEROLLM_MODEL", None)
            result["default_b"] = None

    return result
