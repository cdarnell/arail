"""WK-9: the World Growth Engine — agents evolve a mounted World (correct
existing terms + add new ones) autonomously and reversibly, with a selectable
curation brain (local deep / a cloud provider gateway).
"""

from __future__ import annotations

import json
import time

import pytest
from fastapi.testclient import TestClient

from arail import world_forge as wf, world_mount as wm
from arail.portal import world_routes as wr
from arail.portal.app import app
from tests.world_bundle_builder import make_bundle

CSRF = {"sec-fetch-site": "same-origin"}

BASE_TERMS = [
    {"slug": "algebra", "term": "Algebra", "category": "x", "short": "s",
     "definition": "d", "example": "e", "related": ["misfiled"], "source": "model:local"},
    {"slug": "misfiled", "term": "Misfiled", "category": "x", "short": "s",
     "definition": "d", "example": "e", "related": [], "source": "model:local"},
]
CATS = [{"id": "x", "label": "X"}, {"id": "y", "label": "Y"}]


class GrowRouter:
    """Scripted brain: flags 'misfiled' → category y + a bad edge, and proposes
    one new term 'Ricci flow'."""
    backend_name = "fake-deep"

    def complete(self, prompt, max_tokens=0, temperature=0, **kw):
        class R:
            model = "fake-deep"
        if "Judge it" in prompt and "Misfiled" in prompt:
            R.text = '{"correct": true, "category_ok": false, "better_category": "y", "bad_edges": [], "note": "belongs in Y"}'
        elif "Judge it" in prompt:
            R.text = '{"correct": true, "category_ok": true, "better_category": "", "bad_edges": ["misfiled"], "note": "algebra doesnt link misfiled"}'
        elif "MISSING" in prompt:
            R.text = '{"terms":[{"term":"Ricci flow","category":"x"}]}'
        elif "Define" in prompt:
            R.text = '{"short":"A geometric flow.","definition":"Deforms a metric over time.","example":"Poincare."}'
        else:  # LINK
            R.text = '{"related":["algebra"]}'
        return R()


@pytest.fixture()
def mounted(tmp_path, monkeypatch):
    worlds = tmp_path / "worlds"; data = tmp_path / "data"; pkb = tmp_path / "pkb"
    worlds.mkdir(); data.mkdir()
    monkeypatch.setattr(wm, "_default_worlds_dir", lambda: worlds)
    monkeypatch.setattr(wm, "_default_data_dir", lambda: data)
    monkeypatch.setattr(wm, "_default_pkb_root", lambda: pkb)
    monkeypatch.setattr(wr, "_curation_router", lambda brain: GrowRouter())
    wr._grow_state = {"state": "idle"}
    b = make_bundle(tmp_path / "b", slug="mathworld", display_name="Math World",
                    terms_list=BASE_TERMS, categories=CATS)
    wm.mount(b, data_dir=data, pkb_root=pkb, worlds_dir=worlds)
    yield worlds / "mathworld"
    wr._grow_state = {"state": "idle"}


def _run_to_done(c):
    for _ in range(60):
        st = c.get("/api/worlds/grow").json()
        if st["state"] in ("done", "error"):
            return st
        time.sleep(0.05)
    return c.get("/api/worlds/grow").json()


def test_growth_adds_and_corrects(mounted):
    with _client_ctx() as c:
        r = c.post("/api/worlds/grow", json={"brain": "auto"}, headers=CSRF)
        assert r.status_code == 202
        st = _run_to_done(c)
        assert st["state"] == "done", st
        assert st["added"] == 1 and st["corrected"] >= 1

    # the new term is on disk, gate-valid, and the world re-sealed
    terms = json.loads((mounted / "terms.json").read_bytes())["terms"]
    slugs = {t["slug"] for t in terms}
    assert "ricci-flow" in slugs, "new term should be added to the World"
    ricci = next(t for t in terms if t["slug"] == "ricci-flow")
    assert ricci["source"].startswith("model:"), "new term is honestly model-asserted"
    assert "algebra" in ricci["related"], "new term linked into the existing set"
    # 'misfiled' recategorized to y; algebra's bad edge stripped
    misfiled = next(t for t in terms if t["slug"] == "misfiled")
    assert misfiled["category"] == "y"
    algebra = next(t for t in terms if t["slug"] == "algebra")
    assert "misfiled" not in algebra["related"]
    # bundle still verifies
    assert wm.verify_seal(wm.load_bundle(mounted)).ok


def test_evolution_log_is_reversible_record(mounted):
    with _client_ctx() as c:
        c.post("/api/worlds/grow", json={"brain": "auto"}, headers=CSRF)
        _run_to_done(c)
        got = c.get("/api/worlds/grow").json()
    assert got["passes"], "an evolution pass must be logged"
    p = got["passes"][-1]
    assert p["model"] == "fake-deep"
    assert any(a["slug"] == "ricci-flow" for a in p["added"])
    assert any(ch["kind"] in ("recategorize", "unlink") for ch in p["corrections"])
    # every correction carries before/after so it can be reverted
    for ch in p["corrections"]:
        assert "before" in ch and "after" in ch


def test_grow_requires_mounted_world(tmp_path, monkeypatch):
    worlds = tmp_path / "worlds"; data = tmp_path / "data"
    worlds.mkdir(); data.mkdir()
    monkeypatch.setattr(wm, "_default_worlds_dir", lambda: worlds)
    monkeypatch.setattr(wm, "_default_data_dir", lambda: data)
    with _client_ctx() as c:
        r = c.post("/api/worlds/grow", json={}, headers=CSRF)
        assert r.status_code == 409


def test_grow_csrf_rejected(mounted):
    with _client_ctx() as c:
        r = c.post("/api/worlds/grow", json={}, headers={"sec-fetch-site": "cross-site"})
        assert r.status_code in (400, 403)


def test_curation_router_provider_bridge(monkeypatch):
    """Selecting a cloud brain (e.g. claude) loads the saved token into the
    backend's env var and builds that backend — the 'point at Claude' path."""
    import arail.portal.app as appmod
    monkeypatch.setattr(appmod, "_provider_token", lambda p: "sk-test-key" if p == "claude" else "")
    captured = {}

    class FakeRouter:
        def __init__(self, backend=None, *, billing_source="agent"):
            captured["backend"] = backend
    import arail.router as rr
    monkeypatch.setattr(rr, "ModelRouter", FakeRouter)
    # also patch the name imported inside _curation_router's function scope
    monkeypatch.setattr("arail.router.ModelRouter", FakeRouter)
    import os
    os.environ.pop("ANTHROPIC_API_KEY", None)
    wr._curation_router("claude")
    assert captured.get("backend") == "claude"
    assert os.environ.get("ANTHROPIC_API_KEY") == "sk-test-key"


# TestClient as a context manager so lifespan runs once per test.
def _client_ctx():
    return TestClient(app)
