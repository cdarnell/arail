"""CO-2: bench must preflight-check that the incumbent Ollama model exists.

If `ollama list` returns output that doesn't include 'qwen2.5:7b', the bench
must exit 30 with a clear operator message rather than silently populating
outputs with '[ERROR: ...]' strings.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import bench_ai_eng


def _make_run_result(stdout: str = "", returncode: int = 0) -> MagicMock:
    r = MagicMock()
    r.stdout = stdout
    r.stderr = ""
    r.returncode = returncode
    return r


def test_preflight_exits_30_when_model_absent(monkeypatch):
    """Empty ollama list output must cause sys.exit(30)."""
    monkeypatch.setattr(
        bench_ai_eng.subprocess,
        "run",
        lambda *a, **kw: _make_run_result(stdout="NAME\n"),
    )
    with pytest.raises(SystemExit) as exc_info:
        bench_ai_eng._preflight_ollama_incumbent("qwen2.5:7b")
    assert exc_info.value.code == 30


def test_preflight_passes_when_model_present(monkeypatch):
    """ollama list output containing the model name must not exit."""
    monkeypatch.setattr(
        bench_ai_eng.subprocess,
        "run",
        lambda *a, **kw: _make_run_result(
            stdout="NAME                    ID              SIZE    MODIFIED\nqwen2.5:7b              abc123def456    4.7 GB  2 days ago\n"
        ),
    )
    # Should return without raising
    bench_ai_eng._preflight_ollama_incumbent("qwen2.5:7b")


def test_preflight_exits_30_when_ollama_missing(monkeypatch):
    """If ollama is not installed (FileNotFoundError), must exit 30."""
    def fake_run(*a, **kw):
        raise FileNotFoundError("ollama not found")

    monkeypatch.setattr(bench_ai_eng.subprocess, "run", fake_run)
    with pytest.raises(SystemExit) as exc_info:
        bench_ai_eng._preflight_ollama_incumbent("qwen2.5:7b")
    assert exc_info.value.code == 30
