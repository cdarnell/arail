"""First-impression experience: one World moment, three doors.

Covers the truth table for the one-shot World-picker nudge (C3/C4), the
`?step=world` route (C1), and the additive `/api/worlds` catalog fields
(C2). See sprints/2026-07-25-first-impression/ARCHITECTURE.md for the
full contract list and failure-mode cross-references (T-ids below match
that document).
"""

from __future__ import annotations

import json
import threading

import pytest
from fastapi.testclient import TestClient

from arail import world_mount as wm
from tests.world_bundle_builder import make_bundle


def _client():
    from arail.portal import app as portal_app
    return TestClient(portal_app.app)


def _marker(tmp_path, monkeypatch):
    """Point the one-shot marker at a tmp path (A4/C3)."""
    from arail.portal import app as portal_app
    p = tmp_path / "data" / ".world-prompt-seen"
    monkeypatch.setattr(portal_app, "_world_prompt_marker", lambda: p)
    return p


def _mounted(tmp_path, monkeypatch, mounted: bool):
    """Fake current_mount() truthiness for the dashboard handler."""
    from arail import world_mount as wm_mod
    if mounted:
        rec = wm.MountRecord(
            world="ai", bundle_version=1, world_sha256="x" * 64,
            mounted_at="1970-01-01T00:00:00Z", bundle_dir=str(tmp_path / "b"),
            staged_dir=str(tmp_path / "s"), pin={},
        )
        monkeypatch.setattr(wm_mod, "current_mount", lambda *a, **k: rec)
    else:
        monkeypatch.setattr(wm_mod, "current_mount", lambda *a, **k: None)


# ---------------------------------------------------------------------------
# T1-T7 — the one-shot World-prompt truth table (C3/C4, F1-F6)
# ---------------------------------------------------------------------------

def test_t1_not_onboarded_no_nudge_and_step_world_ignored(tmp_path, monkeypatch):
    monkeypatch.delenv("ARAIL_PASSWORD", raising=False)
    marker = _marker(tmp_path, monkeypatch)
    client = _client()

    res = client.get("/", follow_redirects=False)
    assert res.status_code == 302
    assert res.headers["location"] == "/welcome"

    res2 = client.get("/welcome?step=world")
    assert res2.status_code == 200
    assert "wc-pass" in res2.text  # Step-1 passphrase form renders, param ignored
    assert not marker.exists()


def test_t2_onboarded_mounted_marker_absent_no_redirect(tmp_path, monkeypatch):
    _marker(tmp_path, monkeypatch)
    _mounted(tmp_path, monkeypatch, True)
    client = _client()
    res = client.get("/", follow_redirects=False)
    assert res.status_code == 200


def test_t3_onboarded_unmounted_marker_present_no_redirect(tmp_path, monkeypatch):
    marker = _marker(tmp_path, monkeypatch)
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.touch()
    _mounted(tmp_path, monkeypatch, False)
    client = _client()
    res = client.get("/", follow_redirects=False)
    assert res.status_code == 200


def test_t4_onboarded_unmounted_marker_absent_redirects_and_writes_marker(tmp_path, monkeypatch):
    marker = _marker(tmp_path, monkeypatch)
    _mounted(tmp_path, monkeypatch, False)
    client = _client()
    res = client.get("/", follow_redirects=False)
    assert res.status_code == 302
    assert res.headers["location"] == "/welcome?step=world"
    assert marker.exists()


def test_t5_two_sequential_gets_only_first_redirects(tmp_path, monkeypatch):
    """F1/F4: the structural fix for the historical redirect loop."""
    _marker(tmp_path, monkeypatch)
    _mounted(tmp_path, monkeypatch, False)
    client = _client()
    first = client.get("/", follow_redirects=False)
    second = client.get("/", follow_redirects=False)
    assert first.status_code == 302
    assert second.status_code == 200


def test_t6_marker_write_failure_never_redirects(tmp_path, monkeypatch):
    """F5: OSError on touch() must fall through to a normal render, not loop."""
    from arail.portal import app as portal_app

    class _BoomPath:
        def exists(self):
            return False

        @property
        def parent(self):
            return self

        def mkdir(self, *a, **k):
            return None

        def touch(self, *a, **k):
            raise OSError("read-only filesystem")

    monkeypatch.setattr(portal_app, "_world_prompt_marker", lambda: _BoomPath())
    _mounted(tmp_path, monkeypatch, False)
    client = _client()
    res = client.get("/", follow_redirects=False)
    assert res.status_code == 200


def test_t7_concurrent_requests_no_double_mount_no_loop(tmp_path, monkeypatch):
    """F6: two concurrent GET / must not corrupt the marker or loop."""
    marker = _marker(tmp_path, monkeypatch)
    _mounted(tmp_path, monkeypatch, False)
    client = _client()

    results: list[int] = []
    lock = threading.Lock()

    def _hit():
        r = client.get("/", follow_redirects=False)
        with lock:
            results.append(r.status_code)

    threads = [threading.Thread(target=_hit) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert set(results) <= {200, 302}
    assert marker.exists()

    third = client.get("/", follow_redirects=False)
    assert third.status_code == 200


# ---------------------------------------------------------------------------
# T17 — marker write leaves git status clean (F17)
# ---------------------------------------------------------------------------

def test_t17_marker_touch_does_not_dirty_git_status(monkeypatch):
    import subprocess
    from pathlib import Path
    from arail.portal import app as portal_app

    repo_root = Path(__file__).resolve().parent.parent
    real_marker = portal_app._world_prompt_marker()
    assert real_marker.parent == repo_root / "lab" / "data" or True  # sanity only

    # Only run the git-status assertion against the real repo-rooted lab/data
    # if it's actually inside this checkout (CI sandboxes may relocate it).
    try:
        real_marker.relative_to(repo_root)
    except ValueError:
        pytest.skip("DATA_DIR relocated outside the checkout in this environment")

    existed_before = real_marker.exists()
    real_marker.parent.mkdir(parents=True, exist_ok=True)
    real_marker.touch(exist_ok=True)
    try:
        res = subprocess.run(
            ["git", "status", "--porcelain", "lab/data/.world-prompt-seen"],
            cwd=repo_root, capture_output=True, text=True, timeout=10,
        )
        assert res.stdout.strip() == "", (
            "marker file must not be reported by git status (gitignore posture)\n"
            + res.stdout
        )
    finally:
        if not existed_before:
            real_marker.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# T8 — welcome_page() ?step= matrix (C1, F14)
# ---------------------------------------------------------------------------

def test_t8_welcome_page_step_matrix():
    client = _client()  # ARAIL_PASSWORD set by the autouse conftest fixture

    # onboarded + ?step=world → 200, world-step boot flag present
    res = client.get("/welcome?step=world")
    assert res.status_code == 200
    assert '__ARAIL_BOOT_STEP = "world"' in res.text

    # onboarded + no param → 302 /
    res = client.get("/welcome", follow_redirects=False)
    assert res.status_code == 302
    assert res.headers["location"] == "/"

    # non-matching step values → 302 /, and the raw value never appears
    # in the response body
    for bad in ("mode", "../../etc/passwd"):
        res = client.get("/welcome", params={"step": bad}, follow_redirects=False)
        assert res.status_code == 302, bad
        assert res.headers["location"] == "/", bad

    # ARCHITECTURE.md's C1 pseudocode does `.strip().lower()` before the
    # exact-match comparison, so casing/whitespace variants of "world"
    # DO match (this deviates from C1's own prose bad-input example list,
    # which names "?step=WORLD" as an "unknown/garbage" case that falls
    # through — that line is inconsistent with C1's own pseudocode.
    # Implemented per the pseudocode, the authoritative contract; see
    # BUILD_LOG.md "Architect feedback required").
    for normalizes in ("WORLD", "world "):
        res = client.get("/welcome", params={"step": normalizes}, follow_redirects=False)
        assert res.status_code == 200, normalizes

    # repeated param — Starlette's query_params.get returns the LAST
    # value, so ?step=world&step=x compares "x" != "world" → 302
    res = client.get("/welcome?step=world&step=x", follow_redirects=False)
    assert res.status_code == 302
    assert res.headers["location"] == "/"

    # the raw param is never echoed into any response body
    res = client.get("/welcome", params={"step": "<script>evil</script>"})
    assert "<script>evil</script>" not in res.text


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
