"""WP2 egress honesty: Buddy's HuggingFace scan is consent-gated and never
puts the user's goal text into a third-party URL.

  • airgapped → no suggestion, no network
  • hybrid + no consent → creates ONE pending consent request, suggests
    approval, and does NOT fetch
  • hybrid + consent → fetches a FIXED url (no goal text), correlates locally
"""

from __future__ import annotations

import json

import pytest


@pytest.fixture
def consent_tmp(monkeypatch, tmp_path):
    from arail.agents import consent as consent_mod
    monkeypatch.setattr(consent_mod, "CONSENT_DIR", tmp_path / "consent")
    return tmp_path / "consent"


@pytest.fixture
def hybrid(monkeypatch):
    import arail.airgap as airgap
    monkeypatch.setattr(airgap, "is_airgapped", lambda: False)


class _FakeResp:
    def __init__(self, payload):
        self._b = json.dumps(payload).encode()

    def read(self):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_airgapped_no_network(monkeypatch, consent_tmp):
    import arail.airgap as airgap
    import arail.agents._builtin_buddy as buddy
    monkeypatch.setattr(airgap, "is_airgapped", lambda: True)

    def _boom(*a, **k):
        raise AssertionError("must not touch the network when airgapped")
    monkeypatch.setattr("urllib.request.urlopen", _boom)

    out = buddy._suggest_internet_correlation({"title": "quantum error correction"})
    assert out is None


def test_hybrid_no_consent_requests_not_fetches(monkeypatch, consent_tmp, hybrid):
    import arail.agents._builtin_buddy as buddy
    from arail.agents.consent import ConsentStore

    def _boom(*a, **k):
        raise AssertionError("must not fetch before consent")
    monkeypatch.setattr("urllib.request.urlopen", _boom)

    out = buddy._suggest_internet_correlation({"title": "quantum error correction"})
    # A consent-nudge suggestion, not a paper, and no fetch happened.
    assert out is not None
    assert out.suggestion.get("kind") == "consent"
    # Exactly one pending request for huggingface.co was created.
    pending = ConsentStore().list_pending()
    assert [r["domain"] for r in pending] == ["huggingface.co"]
    # A second cycle does NOT pile up duplicate pending requests.
    buddy._suggest_internet_correlation({"title": "quantum error correction"})
    assert len(ConsentStore().list_pending()) == 1


def test_hybrid_with_consent_fetches_clean_url(monkeypatch, consent_tmp, hybrid):
    import arail.agents._builtin_buddy as buddy
    from arail.agents.consent import ConsentStore

    # User approved huggingface.co.
    ConsentStore().add_domain("https://huggingface.co/api/daily_papers")

    seen = {}

    def _fake_urlopen(req, timeout=6):
        seen["url"] = getattr(req, "full_url", str(req))
        return _FakeResp([
            {"paper": {"id": "2401.001",
                       "title": "Advances in quantum error correction codes",
                       "summary": "surface codes and decoding"}},
            {"paper": {"id": "2401.002",
                       "title": "A survey of transformer training",
                       "summary": "unrelated"}},
        ])
    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen)

    out = buddy._suggest_internet_correlation(
        {"title": "quantum error correction on surface codes"})
    # Fetched the FIXED endpoint — no goal text, no query string.
    assert seen["url"] == buddy._HF_PAPERS_URL
    assert "?" not in seen["url"]
    for word in ("quantum", "error", "correction", "surface", "codes"):
        assert word not in seen["url"]
    # Local correlation picked the matching paper.
    assert out is not None
    assert out.suggestion.get("kind") == "paper"
    assert out.suggestion.get("target") == "2401.001"


def test_hybrid_with_consent_no_match_returns_none(monkeypatch, consent_tmp, hybrid):
    import arail.agents._builtin_buddy as buddy
    from arail.agents.consent import ConsentStore
    ConsentStore().add_domain("https://huggingface.co/api/daily_papers")

    def _fake_urlopen(req, timeout=6):
        return _FakeResp([
            {"paper": {"id": "x", "title": "Basket weaving with jute",
                       "summary": "handicrafts"}},
        ])
    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen)

    # No keyword overlap → honest None, not a forced unrelated suggestion.
    out = buddy._suggest_internet_correlation(
        {"title": "quantum error correction on surface codes"})
    assert out is None
