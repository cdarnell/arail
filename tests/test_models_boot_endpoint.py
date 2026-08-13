"""GET /api/models/boot — the boot model-selection banner's data source.

Mode determination:
  - never settled (no model_defaults.yaml)                  -> picker
  - settled, both slots healthy                              -> hidden
  - settled but the configured model vanished / doesn't fit /
    the env drifted away from what was settled               -> problem

Candidate lists (the expensive per-model catalog join + fit checks) are
assembled only when the mode isn't "hidden", or the caller passes
``?full=1`` — this suite pins that contract directly, not just the
end-to-end payload shape.
"""
from __future__ import annotations

import os

import pytest


@pytest.fixture
def client(monkeypatch, tmp_path):
    from arail.registry import core as reg_core
    from arail.portal import models_api

    monkeypatch.setenv("ARAIL_MODEL_REGISTRY_FILE", str(tmp_path / "model_registry.json"))
    monkeypatch.setenv("ARAIL_MODEL_DEFAULTS_FILE", str(tmp_path / "model_defaults.yaml"))
    monkeypatch.setenv("ARAIL_MODELS_DIR", str(tmp_path / "models"))
    monkeypatch.setenv("ARAIL_DATA_DIR", str(tmp_path / "data"))
    (tmp_path / "models").mkdir()
    reg_core.reset_registry()
    models_api._BOOT_CANDIDATES_CACHE["payload"] = None
    models_api._BOOT_CANDIDATES_CACHE["ts"] = 0.0

    from fastapi.testclient import TestClient
    import arail.portal.app as app_mod
    with TestClient(app_mod.app) as c:
        yield c
    reg_core.reset_registry()
    models_api._BOOT_CANDIDATES_CACHE["payload"] = None


def _mock_ollama_installed(monkeypatch, models):
    monkeypatch.setattr("arail.chat._ollama_installed_models", lambda *a, **kw: models)


# ---------------------------------------------------------------------------
# Mode: picker (never settled)
# ---------------------------------------------------------------------------

def test_unsettled_reports_picker_mode(client):
    r = client.get("/api/models/boot")
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "picker"
    assert body["settlement"]["settled"] is False


def test_picker_mode_assembles_candidates_without_full_flag(client):
    """Picker/problem modes always need the full candidate lists — the
    banner can't render a picker with nothing to pick from."""
    r = client.get("/api/models/boot")
    body = r.json()
    assert "candidates" in body["slots"]["a"]
    assert "candidates" in body["slots"]["b"]
    assert len(body["slots"]["a"]["candidates"]) > 0


def test_picker_candidate_row_shape(client):
    r = client.get("/api/models/boot")
    row = r.json()["slots"]["a"]["candidates"][0]
    for key in ("id", "name", "source", "size_gb", "present", "fit", "install_command", "hf_url"):
        assert key in row, f"missing {key!r} in candidate row: {row}"
    assert set(row["fit"].keys()) == {"verdict", "detail"}


def test_slot_b_allows_none(client):
    r = client.get("/api/models/boot")
    assert r.json()["slots"]["b"]["allow_none"] is True
    assert r.json()["slots"]["a"]["allow_none"] is False


# ---------------------------------------------------------------------------
# Mode: hidden (settled + healthy) — candidates must NOT be assembled
# ---------------------------------------------------------------------------

def test_settled_and_healthy_reports_hidden_with_no_candidates(client, monkeypatch, tmp_path):
    from arail import model_defaults
    _mock_ollama_installed(monkeypatch, [
        {"id": "llama-ai-eng", "runtime": "ollama", "size_gb": 0.9,
         "modified": "", "endpoint": "x"}])
    model_defaults.write_defaults("llama-ai-eng", None)
    model_defaults.apply()

    r = client.get("/api/models/boot")
    body = r.json()
    assert body["mode"] == "hidden", body
    assert body["settlement"]["problems"] == []
    # The expensive part (catalog join + per-candidate fit checks) must be
    # skipped entirely when nothing is wrong.
    assert "candidates" not in body["slots"]["a"]
    assert "candidates" not in body["slots"]["b"]


def test_full_flag_forces_candidate_assembly_even_when_hidden(client, monkeypatch):
    from arail import model_defaults
    _mock_ollama_installed(monkeypatch, [
        {"id": "llama-ai-eng", "runtime": "ollama", "size_gb": 0.9,
         "modified": "", "endpoint": "x"}])
    model_defaults.write_defaults("llama-ai-eng", None)
    model_defaults.apply()

    r = client.get("/api/models/boot?full=1")
    body = r.json()
    assert body["mode"] == "hidden"
    assert "candidates" in body["slots"]["a"]


# ---------------------------------------------------------------------------
# Mode: problem (settled but something's wrong)
# ---------------------------------------------------------------------------

def test_slot_a_no_longer_installed_reports_problem(client, monkeypatch):
    from arail import model_defaults
    _mock_ollama_installed(monkeypatch, [
        {"id": "llama-ai-eng", "runtime": "ollama", "size_gb": 0.9,
         "modified": "", "endpoint": "x"}])
    model_defaults.write_defaults("llama-ai-eng", None)
    model_defaults.apply()

    # Now the model vanishes from Ollama (uninstalled, daemon reset, etc.)
    _mock_ollama_installed(monkeypatch, [])

    r = client.get("/api/models/boot")
    body = r.json()
    assert body["mode"] == "problem"
    problems = body["settlement"]["problems"]
    assert any(p["slot"] == "a" and p["kind"] == "missing" for p in problems)


def test_slot_b_directory_removed_after_settling_reports_problem(client, monkeypatch, tmp_path):
    from arail import model_defaults
    _mock_ollama_installed(monkeypatch, [
        {"id": "llama-ai-eng", "runtime": "ollama", "size_gb": 0.9,
         "modified": "", "endpoint": "x"}])
    model_dir = tmp_path / "models" / "Qwen2.5-7B-Instruct-4bit"
    model_dir.mkdir()
    model_defaults.write_defaults("llama-ai-eng", "Qwen2.5-7B-Instruct-4bit")
    model_defaults.apply()

    r = client.get("/api/models/boot")
    assert r.json()["mode"] == "hidden"

    import shutil
    shutil.rmtree(model_dir)
    r = client.get("/api/models/boot")
    body = r.json()
    assert body["mode"] == "problem"
    problems = body["settlement"]["problems"]
    assert any(p["slot"] == "b" and p["kind"] == "missing" for p in problems)


def test_problem_mode_also_assembles_candidates(client, monkeypatch):
    from arail import model_defaults
    _mock_ollama_installed(monkeypatch, [])
    model_defaults.write_defaults("llama-ai-eng", None)
    model_defaults.apply()

    r = client.get("/api/models/boot")
    body = r.json()
    assert body["mode"] == "problem"
    assert "candidates" in body["slots"]["a"]


# ---------------------------------------------------------------------------
# Airgap: no cloud candidates, no HF links
# ---------------------------------------------------------------------------

def test_airgapped_suppresses_hf_urls_on_slot_b(client, monkeypatch):
    monkeypatch.setenv("LAB_MODE", "airgapped")
    r = client.get("/api/models/boot")
    body = r.json()
    assert body["airgapped"] is True
    for row in body["slots"]["b"]["candidates"]:
        assert row["hf_url"] is None


def test_non_airgapped_shows_hf_urls_when_available(client, monkeypatch):
    monkeypatch.setenv("LAB_MODE", "hybrid")
    r = client.get("/api/models/boot")
    body = r.json()
    assert body["airgapped"] is False
    b_ids_with_links = {row["id"]: row["hf_url"] for row in body["slots"]["b"]["candidates"]
                         if row["hf_url"]}
    assert b_ids_with_links, "expected at least one catalog hf|mlx row to carry an hf_url"


def test_no_cloud_source_rows_ever_appear_in_either_slot(client, monkeypatch):
    monkeypatch.setenv("LAB_MODE", "hybrid")
    r = client.get("/api/models/boot")
    body = r.json()
    for slot in ("a", "b"):
        sources = {row["source"] for row in body["slots"][slot]["candidates"]}
        assert "cloud" not in sources


# ---------------------------------------------------------------------------
# Fit verdicts
# ---------------------------------------------------------------------------

def test_oversized_primary_candidate_marked_too_big_and_no_hf_url_leak(client):
    r = client.get("/api/models/boot")
    rows = {row["id"]: row for row in r.json()["slots"]["a"]["candidates"]}
    assert rows["phi4:14b"]["fit"]["verdict"] == "too_big"


def test_stamp_changes_when_settlement_state_changes(client, monkeypatch):
    from arail import model_defaults
    r1 = client.get("/api/models/boot")
    stamp1 = r1.json()["stamp"]

    _mock_ollama_installed(monkeypatch, [
        {"id": "llama-ai-eng", "runtime": "ollama", "size_gb": 0.9,
         "modified": "", "endpoint": "x"}])
    model_defaults.write_defaults("llama-ai-eng", None)
    model_defaults.apply()

    r2 = client.get("/api/models/boot")
    stamp2 = r2.json()["stamp"]
    assert stamp1 != stamp2
