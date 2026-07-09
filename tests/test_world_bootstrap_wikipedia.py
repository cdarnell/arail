"""WK-3: the Wikipedia sourced-bootstrap pipeline — NO network.

A FakeSession maps URL/param shapes to canned MediaWiki + REST JSON, so the
whole pipeline (resolve → harvest → define → link → gate → sourced) is
exercised deterministically. Also covers the SKILL top-N cap and the forge
endpoint's source=fetch consent wiring.
"""

from __future__ import annotations

import threading

import pytest

from arail import world_forge as wf
from arail.agents.consent import ConsentStore
from arail.world_sources import wikipedia as wk


class _Resp:
    def __init__(self, payload, status=200):
        self._p = payload
        self.status_code = status

    def json(self):
        if self._p is None:
            raise ValueError("not json")
        return self._p


# A tiny math world: Algebra ← subject; links to Group, Ring; category members.
_SEARCH = {"query": {"search": [{"title": "Algebra"}]}}
_LINKS_ALGEBRA = {"query": {"pages": {"1": {"links": [
    {"title": "Group (mathematics)"}, {"title": "Ring (mathematics)"},
    {"title": "List of algebra topics"},  # skipped (List of)
]}}}}
_CATS = {"query": {"categorymembers": [
    {"title": "Field (mathematics)"}, {"title": "Category:Algebra"},  # Category: skipped
]}}
_SUMMARIES = {
    "Group_(mathematics)": {"extract": "A group is a set with an operation. It satisfies axioms.",
                            "description": "algebraic structure",
                            "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/Group_(mathematics)"}}},
    "Ring_(mathematics)": {"extract": "A ring is a set with two operations.",
                           "description": "algebraic structure",
                           "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/Ring_(mathematics)"}}},
    "Field_(mathematics)": {"extract": "A field is a ring where division works.",
                            "description": "algebraic structure",
                            "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/Field_(mathematics)"}}},
}
# cross-links among selected terms (for the LINK stage)
_LINKS_OF = {
    "Group (mathematics)": {"query": {"pages": {"1": {"links": [{"title": "Ring (mathematics)"}]}}}},
    "Ring (mathematics)": {"query": {"pages": {"1": {"links": [{"title": "Field (mathematics)"}, {"title": "Group (mathematics)"}]}}}},
    "Field (mathematics)": {"query": {"pages": {"1": {"links": [{"title": "Ring (mathematics)"}]}}}},
}


class FakeSession:
    def __init__(self, summaries=None, fail_summary=None):
        self.summaries = summaries if summaries is not None else _SUMMARIES
        self.fail_summary = fail_summary or set()
        self.calls = []

    def get(self, url, params=None, headers=None, timeout=None):
        from urllib.parse import unquote
        self.calls.append((url, params))
        if wk.REST_SUMMARY in url:
            title = unquote(url.rsplit("/", 1)[-1])  # decode %28 → (
            if title in self.fail_summary:
                return _Resp(None, status=404)
            return _Resp(self.summaries.get(title, None) or None,
                         status=200 if title in self.summaries else 404)
        # api.php
        p = params or {}
        if p.get("list") == "search":
            return _Resp(_SEARCH)
        if p.get("list") == "categorymembers":
            return _Resp(_CATS)
        if p.get("prop") == "links":
            title = p.get("titles", "")
            if title == "Algebra":
                return _Resp(_LINKS_ALGEBRA)
            return _Resp(_LINKS_OF.get(title, {"query": {"pages": {"1": {"links": []}}}}))
        return _Resp({})


@pytest.fixture()
def approved_consent(tmp_path, monkeypatch):
    import arail.agents.consent as cm
    monkeypatch.setattr(cm, "CONSENT_DIR", tmp_path / "consent")
    monkeypatch.setenv("LAB_MODE", "airgapped")
    monkeypatch.setenv("ARAIL_MODE", "airgapped")
    store = ConsentStore(data_dir=tmp_path / "consent")
    req = store.request_access("https://en.wikipedia.org/", "test", agent="world-forge")
    store.approve(req["id"])
    return req["id"]


# ── pipeline ───────────────────────────────────────────────────────────


def test_happy_path_sourced_world(approved_consent):
    res = wk.bootstrap_subject("algebra", 25, consent_id=approved_consent, session=FakeSession())
    assert res.tier == "sourced"
    slugs = {t["slug"] for t in res.terms}
    assert {"group-mathematics", "ring-mathematics", "field-mathematics"} <= slugs
    # every term has a real wikipedia URL source
    assert all(t["source"].startswith("https://en.wikipedia.org/") for t in res.terms)
    # closed related graph: ring links to group + field, both present
    ring = next(t for t in res.terms if t["slug"] == "ring-mathematics")
    assert "group-mathematics" in ring["related"] and "field-mathematics" in ring["related"]
    # gate passes
    gate = wf.assert_closed_sourced_graph(res.terms, {"core-concepts"})
    assert gate.ok


def test_junk_titles_filtered(approved_consent):
    res = wk.bootstrap_subject("algebra", 25, consent_id=approved_consent, session=FakeSession())
    terms_titles = {t["term"] for t in res.terms}
    assert "List of algebra topics" not in terms_titles
    assert not any("Category:" in t for t in terms_titles)


def test_missing_summaries_skipped(approved_consent):
    fs = FakeSession(fail_summary={"Ring_(mathematics)"})
    res = wk.bootstrap_subject("algebra", 25, consent_id=approved_consent, session=fs)
    assert "ring-mathematics" not in {t["slug"] for t in res.terms}
    assert res.tier == "sourced" and res.terms


def test_429_backs_off_then_succeeds(approved_consent, monkeypatch):
    monkeypatch.setattr(wk.time, "sleep", lambda *_: None)  # no real wait

    class Flaky(FakeSession):
        def __init__(self):
            super().__init__()
            self.first = True

        def get(self, url, params=None, headers=None, timeout=None):
            if self.first and params and params.get("list") == "search":
                self.first = False
                return _Resp(None, status=503)  # transient; retried
            return super().get(url, params, headers, timeout)

    res = wk.bootstrap_subject("algebra", 25, consent_id=approved_consent, session=Flaky())
    assert res.terms and res.tier == "sourced"


def test_cancel_mid_define(approved_consent):
    ev = threading.Event()
    calls = {"n": 0}

    class Cancelling(FakeSession):
        def get(self, url, params=None, headers=None, timeout=None):
            if wk.REST_SUMMARY in url:
                calls["n"] += 1
                ev.set()  # trip cancel on the first define call
            return super().get(url, params, headers, timeout)

    with pytest.raises(wk.BootstrapCancelled):
        wk.bootstrap_subject("algebra", 25, consent_id=approved_consent,
                             cancel=ev, session=Cancelling())


def test_unresolvable_subject_raises_empty(approved_consent):
    class NoHits(FakeSession):
        def get(self, url, params=None, headers=None, timeout=None):
            if params and params.get("list") == "search":
                return _Resp({"query": {"search": []}})
            return super().get(url, params, headers, timeout)

    with pytest.raises(wk.BootstrapEmpty):
        wk.bootstrap_subject("zzznotathing", 25, consent_id=approved_consent, session=NoHits())


def test_no_consent_blocks_at_egress(tmp_path, monkeypatch):
    import arail.agents.consent as cm
    monkeypatch.setattr(cm, "CONSENT_DIR", tmp_path / "consent")
    monkeypatch.setenv("LAB_MODE", "airgapped")
    from arail.airgap import EgressBlocked
    with pytest.raises(EgressBlocked):
        wk.bootstrap_subject("algebra", 25, consent_id="never-approved", session=FakeSession())


# ── SKILL top-N cap ────────────────────────────────────────────────────


def test_skill_md_caps_big_world():
    # 400 fake terms → SKILL.md must fit the budget and carry the honest note.
    terms = [{"slug": f"t{i}", "term": f"Term {i}", "category": "c",
              "short": "x" * 120, "definition": "y" * 300, "example": "",
              "related": [f"t{(i+1) % 400}"], "source": "https://en.wikipedia.org/wiki/x"}
             for i in range(400)]
    kept, note = wf._skill_terms_capped(terms)
    assert note is not None and "400 terms" in note
    assert len(kept) < 400
    md = wf.render_world_skill({"slug": "big", "display_name": "Big",
                                "categories": [{"id": "c", "label": "C"}]},
                               {"provenance_tier": "sourced"}, kept, "abc123", extra_note=note)
    assert len(md) < 56_000
    assert "full glossary lives in the Knowledge Base" in md
