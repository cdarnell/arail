"""Layer C: driver-watch / release-scout are inert in airgapped mode, gated
on consent in hybrid, never crash without a fetcher, and never auto-approve
a finding. Mirrors mini_experiments.py's honesty-test style.
"""

from __future__ import annotations

import re

import pytest

import arail.agents.consent as consent_mod
from arail.agents.consent import ConsentStore
from arail.research import scouting


@pytest.fixture(autouse=True)
def _consent_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(consent_mod, "CONSENT_DIR", tmp_path / "consent")


def _approved_consent_id(url="https://example-vendor.example/driver-page") -> str:
    cs = ConsentStore()
    req = cs.request_access(url, "test consent")
    cs.approve(req["id"])
    return req["id"]


def _ctx(consent_id=None, fetcher=None):
    return scouting.ScoutContext(
        consent_id=consent_id or "not-a-real-id",
        reason="test scouting fetch",
        fetcher=fetcher,
    )


CHECKS = [scouting.check_driver_watch, scouting.check_release_watch]


@pytest.mark.parametrize("check", CHECKS)
def test_inert_when_airgapped(check, monkeypatch):
    monkeypatch.setenv("LAB_MODE", "airgapped")
    consent_id = _approved_consent_id()
    called = {"n": 0}

    def fetcher():
        called["n"] += 1
        return {"version": "999.99"}

    r = check(_ctx(consent_id=consent_id, fetcher=fetcher))
    assert r.state == "inert_airgapped"
    assert r.finding is None
    assert called["n"] == 0, "airgapped must never call the fetcher"


@pytest.mark.parametrize("check", CHECKS)
def test_consent_required_in_hybrid_without_approval(check, monkeypatch):
    monkeypatch.setenv("LAB_MODE", "hybrid")
    called = {"n": 0}

    def fetcher():
        called["n"] += 1
        return {"version": "999.99"}

    r = check(_ctx(consent_id="never-approved", fetcher=fetcher))
    assert r.state == "consent_required"
    assert r.finding is None
    assert called["n"] == 0, "unapproved consent must never call the fetcher"


@pytest.mark.parametrize("check", CHECKS)
def test_cannot_run_without_fetcher(check, monkeypatch):
    monkeypatch.setenv("LAB_MODE", "hybrid")
    consent_id = _approved_consent_id()
    r = check(_ctx(consent_id=consent_id, fetcher=None))
    assert r.state == "cannot_run"
    assert r.finding is None


@pytest.mark.parametrize("check", CHECKS)
def test_fetch_error_is_cannot_run_not_a_crash(check, monkeypatch):
    monkeypatch.setenv("LAB_MODE", "hybrid")
    consent_id = _approved_consent_id()

    def broken_fetcher():
        raise RuntimeError("vendor page unreachable")

    r = check(_ctx(consent_id=consent_id, fetcher=broken_fetcher))
    assert r.state == "cannot_run"
    assert "RuntimeError" in r.message


@pytest.mark.parametrize("check", CHECKS)
def test_finding_when_hybrid_consented_and_fetch_succeeds(check, monkeypatch):
    monkeypatch.setenv("LAB_MODE", "hybrid")
    consent_id = _approved_consent_id()

    def fetcher():
        return {"whatever": "the caller decided to check"}

    r = check(_ctx(consent_id=consent_id, fetcher=fetcher))
    assert r.state == "finding"
    assert r.finding is not None
    assert r.finding["requires_review"] is True
    assert r.finding["auto_approved"] is False


def test_scouting_module_never_constructs_a_url():
    """Structural guarantee, not a promise: scan the module source for any
    literal URL — it should have none, because it never builds one."""
    import inspect
    src = inspect.getsource(scouting)
    assert not re.search(r"https?://", src), \
        "scouting.py must never hardcode an outbound URL"


def test_scouting_never_imports_compiled_kb():
    """A finding must never be auto-approved — this module has no import
    statement reaching the Compiled-KB approve gate at all."""
    import inspect
    import_lines = [ln for ln in inspect.getsource(scouting).splitlines()
                    if ln.strip().startswith(("import ", "from "))]
    assert not any("compiled_kb" in ln for ln in import_lines)
