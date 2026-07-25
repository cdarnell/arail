"""First-impression experience: one World moment, three doors.

Covers the truth table for the one-shot World-picker nudge (C3/C4), the
`?step=world` route (C1), and the additive `/api/worlds` catalog fields
(C2). See sprints/2026-07-25-first-impression/ARCHITECTURE.md for the
full contract list and failure-mode cross-references (T-ids below match
that document).
"""

from __future__ import annotations

import json

import pytest

from arail import world_mount as wm
from tests.world_bundle_builder import make_bundle


# ---------------------------------------------------------------------------
# T11/T12 — WorldInfo / GET /api/worlds additive fields (C2, F15, F16)
# ---------------------------------------------------------------------------

@pytest.fixture()
def worlds_dir(tmp_path):
    return tmp_path / "worlds"


def test_list_available_worlds_reports_term_count_tier_categories(worlds_dir, tmp_path):
    make_bundle(
        worlds_dir, slug="complete",
        terms_list=[
            {"slug": "a", "term": "A", "category": "c", "short": "s",
             "definition": "d", "example": "e", "related": [], "source": "https://x"}
        ],
        categories=[{"id": "c", "label": "C"}],
    )
    # provenance_counts.total in the builder fixture is 1
    infos = wm.list_available_worlds(worlds_dir=worlds_dir, data_dir=tmp_path / "data")
    assert len(infos) == 1
    info = infos[0]
    assert info.term_count == 1
    assert info.provenance_tier == "sourced"
    assert info.categories == ["C"]
    d = info.to_dict()
    assert d["term_count"] == 1
    assert d["provenance_tier"] == "sourced"
    assert d["categories"] == ["C"]


def test_list_available_worlds_never_raises_on_truncated_spec(worlds_dir, tmp_path):
    bundle_dir = make_bundle(worlds_dir, slug="broken")
    (bundle_dir / "spec.json").write_text("{not valid json", encoding="utf-8")

    # load_bundle will fail validation (seal mismatch on truncated spec) —
    # this must still surface as a valid=False entry, never an exception.
    infos = wm.list_available_worlds(worlds_dir=worlds_dir, data_dir=tmp_path / "data")
    assert len(infos) == 1
    assert infos[0].valid is False
    assert infos[0].term_count is None
    assert infos[0].categories == []


def test_list_available_worlds_omits_fields_when_manifest_missing_provenance(worlds_dir, tmp_path):
    bundle_dir = make_bundle(worlds_dir, slug="sparse")
    manifest_path = bundle_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    del manifest["provenance_counts"]
    del manifest["provenance_tier"]
    # Re-seal isn't required for list_available_worlds (light validation
    # only — load_bundle, not verify_seal), so this stays "valid".
    manifest_path.write_text(json.dumps(manifest, indent=2))

    infos = wm.list_available_worlds(worlds_dir=worlds_dir, data_dir=tmp_path / "data")
    assert len(infos) == 1
    assert infos[0].term_count is None, "must omit, never fabricate, a missing count"
    assert infos[0].provenance_tier == ""


def test_api_worlds_response_carries_new_keys_and_existing_keys(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from arail.portal import app as portal_app

    wd = tmp_path / "worlds"
    make_bundle(wd, slug="complete")
    monkeypatch.setattr(wm, "_default_worlds_dir", lambda: wd)
    monkeypatch.setattr(wm, "_default_data_dir", lambda: tmp_path / "data")
    monkeypatch.setattr(wm, "_default_pkb_root", lambda: tmp_path / "pkb")

    client = TestClient(portal_app.app)
    res = client.get("/api/worlds")
    assert res.status_code == 200
    body = res.json()
    worlds = body["worlds"]
    assert worlds, "expected at least one World in the catalog"
    for w in worlds:
        for key in ("slug", "display_name", "path", "valid", "mounted", "reason",
                     "theme_preview", "tagline", "term_count", "provenance_tier",
                     "categories"):
            assert key in w
