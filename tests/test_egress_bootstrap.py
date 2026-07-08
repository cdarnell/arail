"""Adversarial tests for egress.allow_bootstrap_fetch — the ONE consent-gated
exemption that works in airgapped mode (sprint 2026-07-08-world-kb-bootstrap).

Threat model: the seam must be impossible to enter without a recorded,
approved consent; impossible to use for hosts outside the allowlist; and
impossible to leak past its with-block. The airgapped DEFAULT must be
byte-for-byte unchanged for every caller outside the scope.
"""

from __future__ import annotations

import pytest

from arail import egress
from arail.agents.consent import ConsentStore
from arail.airgap import EgressBlocked


@pytest.fixture()
def store(tmp_path, monkeypatch):
    s = ConsentStore(data_dir=tmp_path / "consent")
    # allow_bootstrap_fetch constructs its own ConsentStore() — point the
    # default data dir at the tmp store.
    import arail.agents.consent as consent_mod
    monkeypatch.setattr(consent_mod, "CONSENT_DIR", tmp_path / "consent")
    return s


@pytest.fixture()
def airgapped(monkeypatch):
    monkeypatch.setenv("LAB_MODE", "airgapped")
    monkeypatch.setenv("ARAIL_MODE", "airgapped")
    from arail import airgap
    if hasattr(airgap, "invalidate_probe_cache"):
        airgap.invalidate_probe_cache()
    yield


def _approved_consent(store: ConsentStore) -> str:
    req = store.request_access("https://en.wikipedia.org/", "bootstrap test", agent="forge")
    store.approve(req["id"])
    return req["id"]


# ── entry guards ───────────────────────────────────────────────────────


def test_no_consent_no_entry(store, airgapped):
    with pytest.raises(EgressBlocked, match="consent"):
        with egress.allow_bootstrap_fetch("t", ["wikipedia.org"], consent_id="nope1234"):
            pass


def test_denied_consent_no_entry(store, airgapped):
    req = store.request_access("https://en.wikipedia.org/", "r", agent="forge")
    store.deny(req["id"])
    with pytest.raises(EgressBlocked, match="consent"):
        with egress.allow_bootstrap_fetch("t", ["wikipedia.org"], consent_id=req["id"]):
            pass


def test_pending_consent_no_entry(store, airgapped):
    req = store.request_access("https://en.wikipedia.org/", "r", agent="forge")
    with pytest.raises(EgressBlocked, match="consent"):
        with egress.allow_bootstrap_fetch("t", ["wikipedia.org"], consent_id=req["id"]):
            pass


@pytest.mark.parametrize("bad_hosts", [
    [], None,
    ["http://wikipedia.org"],          # scheme
    ["wikipedia.org/w/api.php"],       # path
    ["wikipedia.org:443"],             # port
    ["*"], ["*.wikipedia.org"],        # wildcards are not bare domains
    ["localhost"],                     # no TLD — suffix match would be meaningless
    [""],
])
def test_malformed_host_allowlists_rejected(store, airgapped, bad_hosts):
    cid = _approved_consent(store)
    with pytest.raises(ValueError):
        with egress.allow_bootstrap_fetch("t", bad_hosts, consent_id=cid):
            pass


@pytest.mark.parametrize("bad_reason", ["", None, "x" * 201])
def test_bad_reason_rejected(store, airgapped, bad_reason):
    cid = _approved_consent(store)
    with pytest.raises(ValueError):
        with egress.allow_bootstrap_fetch(bad_reason, ["wikipedia.org"], consent_id=cid):
            pass


# ── host scoping inside the scope ──────────────────────────────────────


def test_allowlisted_host_passes_and_is_audited(store, airgapped, monkeypatch):
    cid = _approved_consent(store)
    allowed: list = []
    monkeypatch.setattr(egress, "record_allow", lambda url, caller, reason: allowed.append((url, reason)))
    with egress.allow_bootstrap_fetch("bootstrap: math", ["wikipedia.org"], consent_id=cid):
        egress._check_egress_or_raise("https://en.wikipedia.org/api/rest_v1/page/summary/Algebra")
    assert allowed and "bootstrap: math" in allowed[0][1]


def test_subdomain_matches_but_lookalike_does_not(store, airgapped):
    cid = _approved_consent(store)
    with egress.allow_bootstrap_fetch("t", ["wikipedia.org"], consent_id=cid):
        egress._check_egress_or_raise("https://en.wikipedia.org/x")   # subdomain ok
        for evil in (
            "https://evilwikipedia.org/x",        # suffix trick without dot
            "https://wikipedia.org.evil.com/x",   # registered lookalike
            "https://notwikipedia.org/x",
        ):
            with pytest.raises(EgressBlocked):
                egress._check_egress_or_raise(evil)


def test_non_allowlisted_host_blocked_inside_scope(store, airgapped):
    cid = _approved_consent(store)
    with egress.allow_bootstrap_fetch("t", ["wikipedia.org"], consent_id=cid):
        with pytest.raises(EgressBlocked):
            egress._check_egress_or_raise("https://example.com/steal")


# ── scope death ────────────────────────────────────────────────────────


def test_airgap_restored_after_scope(store, airgapped):
    cid = _approved_consent(store)
    with egress.allow_bootstrap_fetch("t", ["wikipedia.org"], consent_id=cid):
        egress._check_egress_or_raise("https://en.wikipedia.org/x")
    with pytest.raises(EgressBlocked):
        egress._check_egress_or_raise("https://en.wikipedia.org/x")


def test_scope_does_not_leak_to_other_threads(store, airgapped):
    import threading
    cid = _approved_consent(store)
    result: dict = {}

    def _other_thread():
        try:
            egress._check_egress_or_raise("https://en.wikipedia.org/x")
            result["blocked"] = False
        except EgressBlocked:
            result["blocked"] = True

    with egress.allow_bootstrap_fetch("t", ["wikipedia.org"], consent_id=cid):
        t = threading.Thread(target=_other_thread)
        t.start()
        t.join(timeout=5)
    assert result.get("blocked") is True, "bootstrap scope leaked to a foreign thread"


def test_exception_inside_scope_still_restores(store, airgapped):
    cid = _approved_consent(store)
    with pytest.raises(RuntimeError):
        with egress.allow_bootstrap_fetch("t", ["wikipedia.org"], consent_id=cid):
            raise RuntimeError("boom")
    with pytest.raises(EgressBlocked):
        egress._check_egress_or_raise("https://en.wikipedia.org/x")


# ── the old ratchet is untouched ───────────────────────────────────────


def test_allow_egress_ratchet_still_hard_in_airgapped(airgapped):
    with pytest.raises(EgressBlocked):
        with egress.allow_egress("should still be refused"):
            pass
