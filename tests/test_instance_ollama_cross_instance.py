"""REVIEW.md M3 — Ollama must not be killed by a launcher's own cleanup
while a sibling World instance is still live.

`stop_instance()` in reset.sh (the explicit `./arailctl stop --world X`
path) already applies the correct "last one out" guard before touching
Ollama. This covers the OTHER path: Ctrl-C / TERM on the launcher's own
foreground process. Before this fix, `ollama_pid` was a member of
`_INST_PIDS`, so `_instance_cleanup_and_exit` killed it unconditionally
on every exit — including while a sibling instance was actively using
it — a cross-instance side effect §11 explicitly forbids.

Extracts `_instance_cleanup_and_exit` verbatim out of scripts/start.sh
(never a reimplementation) and drives it against a REAL registry
directory with a REAL sibling process, via the real
`scripts/lib/instances.sh` predicate (`inst_alive`/`inst_list_slugs` —
never stubbed, so this is a true end-to-end check of the "last one out"
logic).
"""
from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
START_SH = REPO_ROOT / "scripts" / "start.sh"
INSTANCES_SH = REPO_ROOT / "scripts" / "lib" / "instances.sh"
_BASH = shutil.which("bash")

pytestmark = pytest.mark.skipif(_BASH is None, reason="bash required")


def _extract(text: str, start_marker: str, end_marker: str) -> str:
    start_idx = text.index(start_marker)
    end_idx = text.index(end_marker, start_idx)
    return text[start_idx:end_idx]


def _cleanup_fn() -> str:
    start_sh = START_SH.read_text(encoding="utf-8")
    return _extract(
        start_sh,
        "_instance_cleanup_and_exit() {",
        "\n}\n\n# Resolve + jail",
    ) + "\n}\n"


def _write_record(fake_repo: Path, slug: str, portal_pid: int, portal_port: int) -> None:
    rec = {
        "schema": "arail.instance-registry/v1",
        "slug": slug,
        "display_name": slug,
        "checkout": str(fake_repo),
        "instance_root": str(fake_repo / "lab" / "instances" / slug),
        "data_dir": str(fake_repo / "lab" / "instances" / slug / "data"),
        "pkb_root": str(fake_repo / "lab" / "instances" / slug / "pkb"),
        "bind": "127.0.0.1",
        "portal_port": portal_port,
        "lance_port": portal_port + 4,
        "launcher_pid": portal_pid,
        "portal_pid": portal_pid,
        "memory_pid": portal_pid,
        "token": "t",
        "started_at": "2026-07-28T00:00:00Z",
        "arailctl_version": "test",
    }
    reg_dir = fake_repo / "lab" / "instances" / "registry.d"
    reg_dir.mkdir(parents=True, exist_ok=True)
    (reg_dir / f"{slug}.json").write_text(json.dumps(rec), encoding="utf-8")


def _run_cleanup(fake_repo: Path, current_slug: str, ollama_pid: int) -> subprocess.CompletedProcess:
    script = f"""
        set -uo pipefail
        REPO_ROOT="{fake_repo}"
        _INST_PIDS=()
        _INST_CLAIM_FILE=""
        _INST_OLLAMA_PID="{ollama_pid}"
        _INST_CURRENT_SLUG="{current_slug}"
        # shellcheck disable=SC1091
        source "{INSTANCES_SH}"
        {_cleanup_fn()}
        _instance_cleanup_and_exit 0
    """
    return subprocess.run(
        [_BASH, "-c", script],
        capture_output=True, text=True, timeout=15,
    )


def test_ollama_survives_when_a_sibling_instance_is_still_alive(tmp_path):
    fake_repo = tmp_path / "repo"
    (fake_repo / "lab" / "instances" / "finance" / "data").mkdir(parents=True)

    # A REAL sibling "portal" process with a cmdline inst_alive's real
    # predicate matches (module + --port), so this is not stubbed.
    sibling = subprocess.Popen([
        "python3", "-c", "import time; time.sleep(20)",
        "uvicorn", "arail.portal.app", "--port", "9200",
    ])
    # A REAL "ollama" process this launcher believes it started.
    ollama = subprocess.Popen(["sleep", "20"])
    try:
        _write_record(fake_repo, "ai", sibling.pid, 9200)
        result = _run_cleanup(fake_repo, current_slug="finance", ollama_pid=ollama.pid)
        assert result.returncode == 0, result.stdout + result.stderr
        time.sleep(0.3)
        assert ollama.poll() is None, "Ollama was killed while a sibling instance was still alive (M3)"
    finally:
        sibling.kill(); sibling.wait(timeout=5)
        if ollama.poll() is None:
            ollama.kill(); ollama.wait(timeout=5)


def test_ollama_is_stopped_when_no_sibling_instance_remains(tmp_path):
    fake_repo = tmp_path / "repo"
    (fake_repo / "lab" / "instances" / "finance" / "data").mkdir(parents=True)
    # No other registry records at all — this was the last instance.

    ollama = subprocess.Popen(["sleep", "20"])
    try:
        result = _run_cleanup(fake_repo, current_slug="finance", ollama_pid=ollama.pid)
        assert result.returncode == 0, result.stdout + result.stderr
        ollama.wait(timeout=5)
        assert ollama.returncode is not None
    finally:
        if ollama.poll() is None:
            ollama.kill(); ollama.wait(timeout=5)
