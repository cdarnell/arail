"""WK-10: the review-queue API — GET pending, POST promote/reject/revoke,
with the CSRF envelope on every write."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from arail import compiled_kb as ckb
from arail.portal.app import app

CSRF = {"sec-fetch-site": "same-origin"}


@pytest.fixture()
def pkb(tmp_path, monkeypatch):
    root = tmp_path / "pkb"
    (root / "notes").mkdir(parents=True)
    (root / "notes" / "a.md").write_text("# Alpha\nphotosynthesis basics")
    (root / "notes" / "b.md").write_text("# Beta\nmore notes")
    # both compiled_kb and its config resolver must see this root
    monkeypatch.setattr(ckb, "_pkb_root", lambda: root)
    return root


def test_review_promote_flow(pkb):
    with TestClient(app) as c:
        r = c.get("/api/pkb/review")
        assert r.status_code == 200
        data = r.json()
        assert data["gate_enabled"] is True
        pending = {p["path"] for p in data["pending"]}
        assert {"notes/a.md", "notes/b.md"} <= pending

        r = c.post("/api/pkb/promote", json={"paths": ["notes/a.md"]}, headers=CSRF)
        assert r.status_code == 200 and r.json()["count"] == 1

        data = c.get("/api/pkb/review").json()
        assert {p["path"] for p in data["approved"]} == {"notes/a.md"}
        assert "notes/a.md" not in {p["path"] for p in data["pending"]}


def test_reject_then_revoke(pkb):
    with TestClient(app) as c:
        c.post("/api/pkb/reject", json={"paths": ["notes/b.md"]}, headers=CSRF)
        data = c.get("/api/pkb/review").json()
        assert "notes/b.md" not in {p["path"] for p in data["pending"]}

        c.post("/api/pkb/promote", json={"paths": ["notes/a.md"]}, headers=CSRF)
        r = c.post("/api/pkb/revoke", json={"paths": ["notes/a.md"]}, headers=CSRF)
        assert r.json()["revoked"] == 1
        assert not ckb.approved_paths(pkb)


def test_writes_require_csrf(pkb):
    with TestClient(app) as c:
        for ep in ("/api/pkb/promote", "/api/pkb/reject", "/api/pkb/revoke"):
            r = c.post(ep, json={"paths": ["notes/a.md"]},
                       headers={"sec-fetch-site": "cross-site"})
            assert r.status_code == 403, ep
        assert not ckb.approved_paths(pkb)
