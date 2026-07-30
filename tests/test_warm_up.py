"""Warm-up (sprints/2026-07-29-elite-cli/ARCHITECTURE.md §11, Ruling 6 — WP6).

Covers the Python-side half of the gate list: T22 (``_boot_warm_explicit()``
gating, ``_warm_primary_router()`` timing/backend recording, the
``/api/instance`` field set), F16 (no model id leaks), and T29 (the
onboarding allow-list is unchanged by this sprint — the warm signal rides
the endpoint that was already allow-listed, per A6).

The CLI-side half (``start --warm`` polling and reporting) is
tests/cli/warmup_driver.sh — see that file's header for why the split.
"""
from __future__ import annotations

import ast
import asyncio
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
APP_PY = REPO_ROOT / "src" / "arail" / "portal" / "app.py"


class _FakeRouter:
    backend_name = "ollama_native"

    def __init__(self):
        self.calls = []

    def complete(self, prompt, max_tokens=512, *a, **k):
        self.calls.append((prompt, max_tokens))

        class _R:
            text = "ok"
        return _R()


@pytest.fixture
def wired(monkeypatch, tmp_path):
    from arail.registry import core as reg_core
    monkeypatch.setenv("ARAIL_MODEL_REGISTRY_FILE",
                       str(tmp_path / "model_registry.json"))
    monkeypatch.setenv("MODEL_BACKEND", "ollama_native")
    monkeypatch.setenv("MODEL_NAME", "ai-engineer:latest")
    monkeypatch.delenv("MODEL_API_BASE", raising=False)
    reg_core.reset_registry()

    import arail.portal.app as app_mod
    fake = _FakeRouter()
    monkeypatch.setattr(app_mod, "_get_primary_router", lambda: fake)
    yield app_mod, fake
    reg_core.reset_registry()


# ---------------------------------------------------------------------------
# _boot_warm_explicit() — the new gate function itself
# ---------------------------------------------------------------------------

def test_boot_warm_explicit_unset_is_false(monkeypatch):
    from arail.portal import app as app_mod
    monkeypatch.delenv("ARAIL_TIER0_BOOT_WARM", raising=False)
    assert app_mod._boot_warm_explicit() is False


@pytest.mark.parametrize("val", ["1", "true", "True", "yes", "on"])
def test_boot_warm_explicit_truthy_values(monkeypatch, val):
    from arail.portal import app as app_mod
    monkeypatch.setenv("ARAIL_TIER0_BOOT_WARM", val)
    assert app_mod._boot_warm_explicit() is True


@pytest.mark.parametrize("val", ["0", "false", "no", "garbage", ""])
def test_boot_warm_explicit_falsy_or_explicit_zero(monkeypatch, val):
    """An explicit '0'/'false'/'no' must NOT count as an explicit warm
    request (§11.1: '=0 still disables') — distinct from 'unset'."""
    from arail.portal import app as app_mod
    monkeypatch.setenv("ARAIL_TIER0_BOOT_WARM", val)
    assert app_mod._boot_warm_explicit() is False


def test_startup_schedules_warm_on_autochecks_or_explicit_request():
    """Pins the coupling _boot_warm_explicit() must have with _startup()'s
    scheduling decision — mirrors the source-inspection pattern this repo
    already uses for boot-task gating (tests/test_boot_security_scan.py's
    'we can't easily run the FastAPI startup hook here' note) rather than
    driving the actual fire-and-forget asyncio.create_task through
    TestClient's sync wrapper, which does not reliably give a scheduled task
    a chance to run before the test client tears the loop down.
    """
    text = APP_PY.read_text(encoding="utf-8")
    tree = ast.parse(text)
    startup_src = None
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "_startup":
            startup_src = ast.get_source_segment(text, node)
            break
    assert startup_src, "_startup() not found in app.py"
    assert re.search(
        r"if\s+_autochecks_on\s+or\s+_boot_warm_explicit\(\)\s*:",
        startup_src,
    ), (
        "_startup()'s warm-scheduling condition no longer reads "
        "'_autochecks_on or _boot_warm_explicit()' — quiet-boot-with-"
        "explicit-warm-override (T22) has regressed"
    )
    # And the quiet-boot else branch must still flip _MODEL_WARM immediately
    # (so /api/ready's overlay dismisses even when warming never runs).
    assert "_MODEL_WARM = True" in startup_src


# ---------------------------------------------------------------------------
# _warm_primary_router() — timing/backend/skip-reason recording
# ---------------------------------------------------------------------------

def test_warm_records_ms_and_backend_on_a_real_completion(wired):
    app_mod, fake = wired
    app_mod._MODEL_WARM = False
    asyncio.run(app_mod._warm_primary_router())
    assert fake.calls == [("ok", 1)]
    assert app_mod._MODEL_WARM is True
    assert app_mod._MODEL_WARM_BACKEND == "ollama_native"
    assert isinstance(app_mod._MODEL_WARM_MS, int)
    assert app_mod._MODEL_WARM_MS >= 0
    assert app_mod._MODEL_WARM_SKIP_REASON is None


def test_warm_records_skip_reason_when_disabled_by_env(wired, monkeypatch):
    app_mod, fake = wired
    monkeypatch.setenv("ARAIL_TIER0_BOOT_WARM", "0")
    app_mod._MODEL_WARM = False
    asyncio.run(app_mod._warm_primary_router())
    assert fake.calls == []
    assert app_mod._MODEL_WARM is True
    assert app_mod._MODEL_WARM_MS is None
    assert app_mod._MODEL_WARM_BACKEND == "ollama_native"  # backend is still known
    assert app_mod._MODEL_WARM_SKIP_REASON == "ARAIL_TIER0_BOOT_WARM=0"


def test_warm_records_skip_reason_for_in_process_backend(wired, monkeypatch):
    """A backend that isn't ollama_native/openai_compat (weights load
    in-process, e.g. mlx/aerollm) never issues a completion — §11.1's
    'not applicable' case. warm_ms stays null; warm_skipped explains why."""
    app_mod, fake = wired
    fake.backend_name = "mlx"
    app_mod._MODEL_WARM = False
    asyncio.run(app_mod._warm_primary_router())
    assert fake.calls == []
    assert app_mod._MODEL_WARM is True
    assert app_mod._MODEL_WARM_MS is None
    assert app_mod._MODEL_WARM_BACKEND == "mlx"
    assert app_mod._MODEL_WARM_SKIP_REASON is not None
    assert "in-process" in app_mod._MODEL_WARM_SKIP_REASON


def test_warm_records_skip_reason_on_failure(wired, monkeypatch):
    app_mod, fake = wired

    def _boom(*a, **k):
        raise ConnectionError("ollama down")
    monkeypatch.setattr(fake, "complete", _boom)
    app_mod._MODEL_WARM = False
    asyncio.run(app_mod._warm_primary_router())
    assert app_mod._MODEL_WARM is True     # overlay must never trap the user
    assert app_mod._MODEL_WARM_MS is None
    assert app_mod._MODEL_WARM_SKIP_REASON is not None
    assert "ConnectionError" in app_mod._MODEL_WARM_SKIP_REASON


# ---------------------------------------------------------------------------
# GET /api/instance — exact new field set, both branches, no model id (F16)
# ---------------------------------------------------------------------------

_WARM_FIELD_NAMES = {"warm", "warm_ms", "warm_skipped", "backend"}
_MODEL_ID_LOOKING_KEYS = {"model", "model_id", "model_name", "checkpoint",
                          "weights", "model_path"}


def test_api_instance_root_branch_exposes_warm_fields_and_no_model_id(monkeypatch):
    from fastapi.testclient import TestClient
    import arail.portal.app as app_mod
    monkeypatch.delenv("ARAIL_INSTANCE", raising=False)
    # Monkeypatch AFTER the TestClient's __enter__ has already run _startup()
    # — _startup() itself unconditionally sets _MODEL_WARM on a quiet boot
    # (the documented "flip now so the overlay dismisses" branch), which
    # would otherwise clobber a value set beforehand.
    with TestClient(app_mod.app) as client:
        monkeypatch.setattr(app_mod, "_MODEL_WARM", True)
        monkeypatch.setattr(app_mod, "_MODEL_WARM_MS", 4200)
        monkeypatch.setattr(app_mod, "_MODEL_WARM_BACKEND", "ollama_native")
        monkeypatch.setattr(app_mod, "_MODEL_WARM_SKIP_REASON", None)
        r = client.get("/api/instance")
    assert r.status_code == 200
    body = r.json()
    assert _WARM_FIELD_NAMES <= set(body.keys())
    assert body["warm"] is True
    assert body["warm_ms"] == 4200
    assert body["warm_skipped"] is None
    assert body["backend"] == "ollama_native"
    assert not (_MODEL_ID_LOOKING_KEYS & set(body.keys())), (
        "a model-identifying field leaked into /api/instance: "
        f"{_MODEL_ID_LOOKING_KEYS & set(body.keys())}"
    )
    # "ollama_native" is a backend CLASS name, never a specific model id
    # (e.g. "ai-engineer:latest" / "llama-ai-eng") anywhere in the body.
    assert "ai-engineer" not in str(body.values())
    assert "llama-ai-eng" not in str(body.values())


def test_api_instance_world_branch_exposes_warm_fields(monkeypatch):
    from fastapi.testclient import TestClient
    import arail.portal.app as app_mod
    monkeypatch.setenv("ARAIL_INSTANCE", "finance")
    monkeypatch.setenv("ARAIL_INSTANCE_TOKEN", "abc123")
    with TestClient(app_mod.app) as client:
        # See the sibling root-branch test for why this happens AFTER entry.
        monkeypatch.setattr(app_mod, "_MODEL_WARM", False)
        monkeypatch.setattr(app_mod, "_MODEL_WARM_MS", None)
        monkeypatch.setattr(app_mod, "_MODEL_WARM_BACKEND", None)
        monkeypatch.setattr(app_mod, "_MODEL_WARM_SKIP_REASON", None)
        r = client.get("/api/instance")
    assert r.status_code == 200
    body = r.json()
    assert _WARM_FIELD_NAMES <= set(body.keys())
    assert body["warm"] is False
    assert body["warm_ms"] is None
    assert body["backend"] is None


# ---------------------------------------------------------------------------
# T29 — no new pre-onboarding endpoint; the allow-list is unchanged
# ---------------------------------------------------------------------------

def _onboarding_gate_allowlist() -> tuple:
    """Mirrors tests/test_instance_live_launch_findings.py's
    _onboarding_gate_allowlist() (duplicated, not imported — that file is a
    test module, not a library; the ~15-line AST walk is cheap to keep in
    sync since both copies pin the SAME literal tuple in app.py)."""
    text = APP_PY.read_text(encoding="utf-8")
    tree = ast.parse(text)
    for node in ast.walk(tree):
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)) \
                and node.name == "onboarding_gate":
            for sub in ast.walk(node):
                if isinstance(sub, ast.Assign) and any(
                    isinstance(t, ast.Name) and t.id == "allowed_prefixes"
                    for t in sub.targets
                ):
                    return tuple(
                        e.value for e in sub.value.elts  # type: ignore[attr-defined]
                        if isinstance(e, ast.Constant) and isinstance(e.value, str)
                    )
    raise AssertionError("onboarding_gate's allowed_prefixes not found")


# Frozen at WP6 time (sprints/2026-07-29-elite-cli) — the warm-up signal
# rides the ALREADY-allow-listed /api/instance (A6); this sprint adds no new
# prefix. An exact tuple comparison so any future addition is a deliberate,
# reviewed change to THIS test, not a silent expansion of anonymous surface.
_EXPECTED_ALLOWLIST = (
    "/welcome",
    "/api/welcome",
    "/static/",
    "/api/system/health",
    "/api/system/metrics",
    "/api/instance",
    "/favicon.ico",
    "/health",
    "/healthz",
    "/metrics",
)


def test_onboarding_gate_allowlist_unchanged_by_this_sprint():
    assert _onboarding_gate_allowlist() == _EXPECTED_ALLOWLIST
