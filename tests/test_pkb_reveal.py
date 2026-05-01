"""Reveal endpoint + ingest destinations.

Covers the /knowledge UX additions:
  * ``pkb.ingest()`` records each moved file's post-ingest path under
    ``destinations`` so callers can offer per-file "Open" links.
  * ``POST /api/pkb/upload`` threads that map through as a top-level
    ``landed`` array of ``{src, path}`` entries.
  * ``POST /api/system/reveal`` whitelists slot names, refuses
    traversal escapes, creates dirs on demand, and respects
    ``ARAIL_HEADLESS=1`` (returns the path without spawning a file
    browser).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def _setup_env(monkeypatch, tmp_path: Path):
    """Point the lab tree at a temp dir + force headless mode.

    ARAIL_HEADLESS=1 keeps the reveal endpoint from actually spawning
    a Finder/Explorer process during the test run.

    ``arail.config.PKB_ROOT`` is computed at import time, so once
    ``arail.config`` has been loaded by *any* test the env-var
    override no longer rewrites it — we patch the module attribute
    directly so each test gets its own scratch tree regardless of
    suite ordering. ``ARAIL_MODELS_DIR`` is read fresh by the
    reveal endpoint, so the env var is enough.
    """
    monkeypatch.setenv("LAB_PKB", str(tmp_path / "pkb"))
    monkeypatch.setenv("ARAIL_MODELS_DIR", str(tmp_path / "models"))
    monkeypatch.setenv("ARAIL_HEADLESS", "1")
    monkeypatch.setenv("ARAIL_MODE", "airgapped")
    monkeypatch.setenv("LAB_WIKI_AUTO_REBUILD", "false")
    import arail.config
    monkeypatch.setattr(arail.config, "PKB_ROOT", tmp_path / "pkb")


# ── pkb.ingest destinations ────────────────────────────────────────────


def test_ingest_returns_destinations_for_moved_files(tmp_path: Path):
    from arail import pkb

    pkb.scaffold(tmp_path)
    (tmp_path / "inbox" / "paper.pdf").write_text("fake pdf")
    (tmp_path / "inbox" / "shot.png").write_bytes(b"\x89PNG stub")
    (tmp_path / "inbox" / "data.csv").write_text("a,b\n1,2\n")

    result = pkb.ingest(tmp_path)

    assert result["moved"] == 3
    dests = result["destinations"]
    assert "paper.pdf" in dests and dests["paper.pdf"].startswith("sources/papers/")
    assert "shot.png" in dests and dests["shot.png"].startswith("sources/images/")
    assert "data.csv" in dests and dests["data.csv"].startswith("sources/datasets/")
    # Path is a string, relative to PKB root, posix-formatted.
    for v in dests.values():
        assert isinstance(v, str) and not v.startswith("/")


def test_ingest_destinations_empty_when_no_inbox(tmp_path: Path):
    from arail import pkb

    # No scaffold — inbox/ doesn't exist yet.
    result = pkb.ingest(tmp_path)
    assert result["moved"] == 0
    assert result["destinations"] == {}


# ── /api/pkb/upload landed ─────────────────────────────────────────────


def test_pkb_upload_returns_landed_paths(monkeypatch, tmp_path):
    _setup_env(monkeypatch, tmp_path)
    from arail.portal.app import app

    client = TestClient(app)
    files = [
        ("files", ("notes.pdf",  b"%PDF-1.4 stub", "application/pdf")),
        ("files", ("shot.png",   b"\x89PNG stub",  "image/png")),
        ("files", ("readme.md",  b"# title\n",     "text/markdown")),
    ]
    r = client.post("/api/pkb/upload", files=files)
    assert r.status_code == 200, r.text
    data = r.json()

    assert data["uploaded"] == 3
    landed = data.get("landed")
    assert isinstance(landed, list) and len(landed) == 3
    by_src = {entry["src"]: entry["path"] for entry in landed}
    assert by_src["notes.pdf"].startswith("sources/papers/")
    assert by_src["shot.png"].startswith("sources/images/")
    assert by_src["readme.md"].startswith("sources/articles/")


def test_pkb_upload_landed_omits_path_when_auto_ingest_skipped(monkeypatch, tmp_path):
    """auto_ingest=false leaves files in inbox/. landed should not appear
    because no destinations are produced — the client falls back to
    extension-inferred folder names."""
    _setup_env(monkeypatch, tmp_path)
    from arail.portal.app import app

    client = TestClient(app)
    r = client.post(
        "/api/pkb/upload",
        files=[("files", ("x.txt", b"hi", "text/plain"))],
        data={"auto_ingest": "false"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["uploaded"] == 1
    assert "landed" not in data
    assert "ingest" not in data


# ── /api/system/reveal ────────────────────────────────────────────────


def test_reveal_inbox_returns_path_in_headless(monkeypatch, tmp_path):
    _setup_env(monkeypatch, tmp_path)
    from arail.portal.app import app

    client = TestClient(app)
    r = client.post("/api/system/reveal", json={"slot": "inbox"})
    assert r.status_code == 200
    data = r.json()
    assert data["opened"] is False
    assert data["reason"] == "headless"
    assert data["path"].endswith("/inbox")
    # Endpoint creates the dir on demand.
    assert (tmp_path / "pkb" / "inbox").is_dir()


def test_reveal_models_returns_path_in_headless(monkeypatch, tmp_path):
    _setup_env(monkeypatch, tmp_path)
    from arail.portal.app import app

    client = TestClient(app)
    r = client.post("/api/system/reveal", json={"slot": "models"})
    assert r.status_code == 200
    data = r.json()
    assert data["opened"] is False
    assert data["path"].endswith("/models")
    assert (tmp_path / "models").is_dir()


def test_reveal_subpath_legitimate(monkeypatch, tmp_path):
    _setup_env(monkeypatch, tmp_path)
    from arail.portal.app import app

    client = TestClient(app)
    r = client.post(
        "/api/system/reveal",
        json={"slot": "sources", "subpath": "papers"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["path"].endswith("/sources/papers")


def test_reveal_subpath_traversal_rejected(monkeypatch, tmp_path):
    _setup_env(monkeypatch, tmp_path)
    from arail.portal.app import app

    client = TestClient(app)
    r = client.post(
        "/api/system/reveal",
        json={"slot": "sources", "subpath": "../../../etc"},
    )
    assert r.status_code == 400
    assert "escapes" in r.json()["error"].lower()


def test_reveal_unknown_slot_rejected(monkeypatch, tmp_path):
    _setup_env(monkeypatch, tmp_path)
    from arail.portal.app import app

    client = TestClient(app)
    r = client.post("/api/system/reveal", json={"slot": "etc"})
    assert r.status_code == 400
    body = r.json()
    assert "unknown slot" in body["error"]
    # The error response advertises the valid slot list so a
    # confused caller can self-correct.
    assert "inbox" in body["valid"]
    assert "models" in body["valid"]
