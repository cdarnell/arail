"""Tests 30-31 of sprints/2026-08-10-arail2-persistence-instantiated/
ARCHITECTURE.md §7 — the provisioning class check.

The rule under test: declared and not instantiated => a finding, never
silence. Test 31 constructs each registered mechanism in the
declared-not-instantiated state and asserts a finding, PLUS a synthetic
"instance four" to prove the mechanism generalizes rather than hardcoding
the three known bugs.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from arail import provisioning
from arail.provisioning import Assertion


@pytest.fixture(autouse=True)
def pkb_index_reset():
    import arail.pkb_index as pki
    pki._reset_for_tests()
    yield
    pki._reset_for_tests()


REPO_ROOT = Path(__file__).resolve().parents[1]


# ── test 30: doctor exit codes on the built-in registry ────────────────────

def test_healthy_registry_has_no_required_findings(tmp_path: Path):
    """relational_store: fresh dir -> not-yet-created is a legitimate,
    expected finding pre-install, so we ensure it first to prove the
    'clean machine, freshly provisioned' path reports OK."""
    from arail.dbspec.ensure import ensure_db
    ensure_db(tmp_path, apply=True, spec_dir=REPO_ROOT / "spec")

    a = provisioning.check_relational_store(
        repo_root=REPO_ROOT, data_dir=tmp_path, spec_dir=REPO_ROOT / "spec")
    assert a.finding is False


def test_uninstantiated_relational_store_is_a_required_finding(tmp_path: Path):
    a = provisioning.check_relational_store(
        repo_root=REPO_ROOT, data_dir=tmp_path, spec_dir=REPO_ROOT / "spec")
    assert a.declared is True
    assert a.instantiated is False
    assert a.finding is True
    assert a.tier == "required"
    assert a.action


# ── test 31: one test per row + the synthetic "instance four" ──────────────

def test_vector_backend_uninstantiated_is_a_finding(monkeypatch):
    monkeypatch.setattr("arail.vector_index.available", lambda: False)
    a = provisioning.check_vector_backend()
    assert a.finding is True
    assert a.tier == "required"


def test_vector_backend_instantiated_is_not_a_finding(monkeypatch):
    monkeypatch.setattr("arail.vector_index.available", lambda: True)
    a = provisioning.check_vector_backend()
    assert a.finding is False


def test_kb_gate_declared_and_nothing_approved_is_a_finding(monkeypatch):
    from arail import compiled_kb
    monkeypatch.setattr(compiled_kb, "gate_enabled", lambda: True, raising=False)
    monkeypatch.setattr(compiled_kb, "approved_paths", lambda: [])
    a = provisioning.check_kb_gate()
    assert a.declared is True
    assert a.instantiated is False
    assert a.finding is True


def test_kb_gate_declared_and_approved_is_not_a_finding(monkeypatch):
    from arail import compiled_kb
    monkeypatch.setattr(compiled_kb, "gate_enabled", lambda: True, raising=False)
    monkeypatch.setattr(compiled_kb, "approved_paths", lambda: ["a.md", "b.md"])
    a = provisioning.check_kb_gate()
    assert a.finding is False


def test_embedding_provenance_finding_when_degraded():
    from arail import pkb_index
    pkb_index.set_degraded("dimension", "mismatch")
    a = provisioning.check_embedding_provenance()
    assert a.finding is True


def test_embedding_provenance_not_a_finding_when_healthy():
    a = provisioning.check_embedding_provenance()
    assert a.finding is False


def test_instance_registry_finding_when_ondisk_unregistered(tmp_path: Path):
    (tmp_path / "lab" / "instances" / "orphan" / "data").mkdir(parents=True)
    (tmp_path / "lab" / "instances" / "registry.d").mkdir(parents=True)
    a = provisioning.check_instance_registry(repo_root=tmp_path)
    assert a.finding is True
    assert "orphan" in a.detail


def test_instance_registry_no_finding_when_fully_registered(tmp_path: Path):
    a = provisioning.check_instance_registry(repo_root=tmp_path)
    assert a.finding is False


def test_synthetic_instance_four_generalizes():
    """Register a dummy mechanism declared-and-not-instantiated and assert
    it produces a finding — proving the mechanism generalizes rather than
    hardcoding three known bugs."""
    saved = dict(provisioning._REGISTRY)
    try:
        provisioning.register(
            "synthetic_instance_four",
            lambda **_kw: Assertion("synthetic_instance_four", "required",
                                    True, False, "never instantiated", "fix it"))
        results = provisioning.evaluate_all(
            repo_root=Path("."), data_dir=Path("."))
        found = [a for a in results if a.key == "synthetic_instance_four"]
        assert len(found) == 1
        assert found[0].finding is True
    finally:
        provisioning._REGISTRY.clear()
        provisioning._REGISTRY.update(saved)


def test_to_json_schema():
    a = Assertion("x", "required", True, False, "detail", "action")
    payload = provisioning.to_json([a])
    assert payload["schema"] == "arail.provisioning/v1"
    assert payload["assertions"][0]["finding"] is True
