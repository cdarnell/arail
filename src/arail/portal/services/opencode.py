"""opencode service module — subprocess lifecycle for opencode serve.

Design decisions (from ARCHITECTURE.md @ 50ce5ad):
- Direct iframe, no reverse proxy.
- OPENCODE_SERVER_PASSWORD NOT set.
- Loopback-only binding (--hostname 127.0.0.1 hard-coded, no env override).
- Readiness probe: GET /doc (OpenAPI JSON). No /healthz endpoint.
- --port REQUIRED (opencode default is 0 / OS-assigned).
- Log capped at 10 MB; rotated to opencode.log.1 on start.
- Module-level Lock serialises start/stop/restart against concurrent callers.
"""

from __future__ import annotations

import logging
import os
import platform
import shutil
import socket
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

_log = logging.getLogger(__name__)

# ── Public constants ────────────────────────────────────────────────────────

PORT_DEFAULT: int = 4096
HOST: str = "127.0.0.1"
LOG_PATH = Path("lab/logs/opencode.log")
READINESS_PATH: str = "/doc"
_LOG_MAX_BYTES: int = 10 * 1024 * 1024  # 10 MB

# ── Module-level lock (F-PROC-4, F-CONFIG-3) ───────────────────────────────
_lock = threading.Lock()

# ── Provider constants (mirrors app.py) ────────────────────────────────────
_CLOUD_PROVIDER_BASES: dict[str, str] = {
    "claude":      "https://api.anthropic.com/v1",
    "nvidia":      "https://integrate.api.nvidia.com/v1",
    "openrouter":  "https://openrouter.ai/api/v1",
    "huggingface": "https://api-inference.huggingface.co",
    "custom":      "",  # reads MODEL_API_BASE
}

_PROVIDER_KEY_ENVS: dict[str, str] = {
    "claude":      "ANTHROPIC_API_KEY",
    "nvidia":      "NVIDIA_API_KEY",
    "openrouter":  "OPENROUTER_API_KEY",
    "huggingface": "HF_TOKEN",
    "custom":      "MODEL_API_KEY",
}


# ── Public API ──────────────────────────────────────────────────────────────

def is_installed() -> bool:
    """True iff opencode binary is on PATH. Never raises."""
    try:
        return bool(shutil.which("opencode"))
    except Exception:
        return False


def is_running(port: int = PORT_DEFAULT) -> bool:
    """TCP probe — True if something is listening on HOST:port.

    Returns within ~300 ms (sub-second timeout matches _port_open in app.py).
    TCP-open does NOT mean opencode is ready; use _wait_ready for that.
    """
    try:
        with socket.create_connection((HOST, port), timeout=0.3):
            return True
    except OSError:
        return False


def start(port: int = PORT_DEFAULT) -> dict[str, Any]:
    """Spawn `opencode serve --port <port> --hostname 127.0.0.1`.

    Returns {"ok": True, "pid": int} on success or
            {"ok": False, "error": str} on any failure.

    Side effects:
    - Creates lab/logs/ if missing (F-PROC-5).
    - Rotates log at 10 MB (F-PROC-6).
    - Merges _compute_source_env() into subprocess env (F-RESTART-2).
    - Does NOT set OPENCODE_SERVER_PASSWORD (architecture decision).
    - Hard-codes --hostname 127.0.0.1 (F-SEC-6, no env override).
    """
    with _lock:
        if not is_installed():
            return {"ok": False, "error": "opencode not installed"}

        if is_running(port):
            return {"ok": False, "error": "port busy"}

        # Prepare log file (F-PROC-5, F-PROC-6)
        log_file = Path(LOG_PATH)
        log_file.parent.mkdir(parents=True, exist_ok=True)
        _maybe_rotate_log(log_file)

        # Build env — fresh every call (F-RESTART-2)
        env = {**os.environ, **_compute_source_env()}

        try:
            f = log_file.open("ab")
            proc = subprocess.Popen(
                ["opencode", "serve", "--port", str(port), "--hostname", HOST],
                env=env,
                stdout=f,
                stderr=f,
            )
            _log.info("opencode started pid=%s port=%s", proc.pid, port)
            return {"ok": True, "pid": proc.pid}
        except Exception as exc:
            _log.error("opencode start failed: %s", exc)
            return {"ok": False, "error": str(exc)}


def stop(port: int = PORT_DEFAULT) -> dict[str, Any]:
    """Kill all processes bound to HOST:port via lsof.

    Returns {"ok": True, "killed": [pid, ...]} or
            {"ok": False, "error": str}.
    Sends SIGTERM first; if still running after 2 s, sends SIGKILL.
    Never raises.
    """
    with _lock:
        return _stop_unlocked(port)


def _stop_unlocked(port: int) -> dict[str, Any]:
    """Inner stop — caller MUST hold _lock."""
    if not shutil.which("lsof"):
        return {"ok": False, "error": "lsof unavailable"}
    try:
        result = subprocess.run(
            ["lsof", "-ti", f":{port}"],
            capture_output=True, text=True,
        )
        raw_pids = [p.strip() for p in result.stdout.strip().split() if p.strip()]
        if not raw_pids:
            return {"ok": True, "killed": []}

        # SIGTERM first
        for pid in raw_pids:
            try:
                subprocess.run(["kill", pid], check=False)
            except Exception:
                pass

        # Wait up to 2 s, then SIGKILL stragglers
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            still = subprocess.run(
                ["lsof", "-ti", f":{port}"],
                capture_output=True, text=True,
            ).stdout.strip().split()
            if not still:
                break
            time.sleep(0.1)

        still = subprocess.run(
            ["lsof", "-ti", f":{port}"],
            capture_output=True, text=True,
        ).stdout.strip().split()
        for pid in still:
            try:
                subprocess.run(["kill", "-9", pid], check=False)
            except Exception:
                pass

        _log.info("opencode stopped port=%s killed=%s", port, raw_pids)
        return {"ok": True, "killed": raw_pids}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def restart(port: int = PORT_DEFAULT) -> dict[str, Any]:
    """Best-effort restart: stop → wait port free → start → wait ready.

    Caller MUST fire this in a daemon thread (it blocks up to ~13 s).
    Returns {"ok": True} only after readiness confirmed.
    Returns {"ok": False, "error": "<phase>: <detail>"} on timeout.
    """
    with _lock:
        # 1. Stop
        stop_result = _stop_unlocked(port)
        if not stop_result.get("ok"):
            _log.warning("opencode restart/stop failed: %s", stop_result)
            # Continue anyway — maybe it was already down

        # 2. Wait up to 3 s for port to be free (F-RESTART-3)
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            if not is_running(port):
                break
            time.sleep(0.1)
        if is_running(port):
            return {"ok": False, "error": "stop: port still bound after 3 s"}

        # 3. Start (calls _start_inner without locking again since we hold it)
        start_result = _start_inner(port)
        if not start_result.get("ok"):
            return {"ok": False, "error": f"start: {start_result.get('error', 'unknown')}"}

        # 4. Wait ready
        if not _wait_ready(port, timeout_s=10.0):
            return {"ok": False, "error": "ready: opencode did not respond on /doc within 10 s"}

        return {"ok": True}


def _start_inner(port: int) -> dict[str, Any]:
    """Start without acquiring _lock — caller must hold it."""
    if not is_installed():
        return {"ok": False, "error": "opencode not installed"}

    if is_running(port):
        return {"ok": False, "error": "port busy"}

    log_file = Path(LOG_PATH)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    _maybe_rotate_log(log_file)

    env = {**os.environ, **_compute_source_env()}

    try:
        f = log_file.open("ab")
        proc = subprocess.Popen(
            ["opencode", "serve", "--port", str(port), "--hostname", HOST],
            env=env,
            stdout=f,
            stderr=f,
        )
        _log.info("opencode started pid=%s port=%s", proc.pid, port)
        return {"ok": True, "pid": proc.pid}
    except Exception as exc:
        _log.error("opencode start failed: %s", exc)
        return {"ok": False, "error": str(exc)}


def _wait_ready(port: int, timeout_s: float) -> bool:
    """Poll GET http://HOST:port/doc every 200 ms until 200 OK or timeout.

    Uses `requests` with a short per-call timeout (1.0 s).
    Returns True on first 200, False on timeout.
    """
    import requests  # already in pyproject.toml (A10)

    url = f"http://{HOST}:{port}{READINESS_PATH}"
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            resp = requests.get(url, timeout=1.0)
            if resp.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(0.2)
    return False


def _maybe_rotate_log(log_file: Path) -> None:
    """Rotate log to .log.1 if it exceeds _LOG_MAX_BYTES (F-PROC-6)."""
    if log_file.exists() and log_file.stat().st_size > _LOG_MAX_BYTES:
        rotated = log_file.with_suffix(".log.1")
        try:
            log_file.rename(rotated)
        except OSError:
            pass


def _compute_source_env() -> dict[str, str]:
    """Translate active Compute Source into opencode env vars.

    Reads (no writes): imports from app.py helpers via lazy import to
    avoid circular dependency at module load time.
    Never logs token values (F-SEC-2).

    Mapping:
      my_machine  → OPENCODE_API_BASE=MODEL_API_BASE or ollama default
                    OPENCODE_MODEL=MODEL_NAME
                    OPENCODE_API_KEY='not-needed'
      cloud       → OPENCODE_API_BASE=_PROVIDER_META[p]['base']
                    OPENCODE_MODEL=MODEL_NAME
                    OPENCODE_API_KEY=token (never logged)
    Unknown provider falls back to my_machine mapping.
    """
    # Lazy import — avoids circular import at module level and matches
    # the pattern used in the providers_active hook.
    try:
        from arail.portal.app import (  # type: ignore[import]
            _load_active_provider,
            _provider_token,
        )
        provider = _load_active_provider()
        token = _provider_token(provider) if provider != "my_machine" else ""
    except Exception:
        provider = "my_machine"
        token = ""

    if provider == "my_machine" or provider not in _CLOUD_PROVIDER_BASES:
        base = os.getenv("MODEL_API_BASE") or "http://127.0.0.1:11434/v1"
        return {
            "OPENCODE_API_BASE": base,
            "OPENCODE_MODEL": os.getenv("MODEL_NAME", ""),
            "OPENCODE_API_KEY": "not-needed",
        }

    # Cloud provider
    if provider == "custom":
        base = os.getenv("MODEL_API_BASE") or ""
    else:
        base = _CLOUD_PROVIDER_BASES.get(provider, "")

    return {
        "OPENCODE_API_BASE": base,
        "OPENCODE_MODEL": os.getenv("MODEL_NAME", ""),
        "OPENCODE_API_KEY": token,
    }


def install_hint() -> dict[str, str]:
    """Return platform-specific install instructions for opencode.

    Pure: reads platform.system() + os.uname() only. No I/O.
    """
    system = platform.system()
    if system == "Darwin":
        return {
            "platform": "darwin",
            "command": "brew install sst/tap/opencode",
            "docs_url": "https://opencode.ai/docs",
        }
    if system == "Linux":
        # Distinguish WSL
        try:
            uname_r = os.uname().release.lower()
        except Exception:
            uname_r = ""
        if "microsoft" in uname_r or "wsl" in uname_r:
            return {
                "platform": "wsl",
                "command": "curl -fsSL https://opencode.ai/install | bash",
                "docs_url": "https://opencode.ai/docs",
            }
        return {
            "platform": "linux",
            "command": "curl -fsSL https://opencode.ai/install | bash",
            "docs_url": "https://opencode.ai/docs",
        }
    # Windows or other
    if system == "Windows":
        return {
            "platform": "windows",
            "command": "winget install sst.opencode",
            "docs_url": "https://opencode.ai/docs",
        }
    return {
        "platform": "other",
        "command": "curl -fsSL https://opencode.ai/install | bash",
        "docs_url": "https://opencode.ai/docs",
    }
