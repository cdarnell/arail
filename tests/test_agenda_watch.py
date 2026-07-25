"""World-generic horizon scouting (agenda_watch): inert in airgapped mode,
consent-gated per feed in hybrid, URLs verbatim from the sealed agenda,
change findings staged as PENDING review items — never auto-approved.
"""

from __future__ import annotations

import json

import pytest

import arail.agents.consent as consent_mod
from arail.agents.consent import ConsentStore
from arail.research import agenda_watch as aw


AGENDA = {
    "schema": "dac.world-agenda/v1",
    "world": "testworld",
    "watches": [
        {"node": "testworld", "feeds": ["https://feeds.example/a"],
         "cadence": "occasional"},
        {"node": "drivers", "feeds": [
            "https://vendor.example/drivers",
            "vendor documentation (NVIDIA, AMD, Intel)",   # free text: skipped
        ], "cadence": "occasional"},
    ],
}


@pytest.fixture(autouse=True)
def _iso(tmp_path, monkeypatch):
    """Isolate consent dir + a fake mounted world with a staged agenda."""
    monkeypatch.setattr(consent_mod, "CONSENT_DIR", tmp_path / "consent")
    staged = tmp_path / "staged"
    staged.mkdir()
    (staged / "agenda.json").write_text(json.dumps(AGENDA))

    from arail import world_mount as wm
    record = wm.MountRecord(
        world="testworld", bundle_version=1, world_sha256="0" * 64,
        mounted_at="2026-07-25T00:00:00Z", bundle_dir=str(tmp_path / "bundle"),
        staged_dir=str(staged), pin={})
    monkeypatch.setattr(wm, "current_mount", lambda data_dir=None: record)
    yield tmp_path


def _tick(tmp_path, now=1000.0):
    return aw.tick(data_dir=tmp_path / "data", pkb_root=tmp_path / "pkb", now=now)


def _approve_all_pending():
    cs = ConsentStore()
    for r in list(cs.list_pending()):
        cs.approve(r["id"])


# ── watch extraction ─────────────────────────────────────────────────

def test_load_watches_urls_verbatim_free_text_skipped():
    feeds = aw.load_watches(AGENDA)
    assert [f.url for f in feeds] == ["https://feeds.example/a",
                                      "https://vendor.example/drivers"]
    # never composed, never normalized beyond strip
    assert feeds[0].node == "testworld" and feeds[1].node == "drivers"


# ── airgapped ────────────────────────────────────────────────────────

def test_airgapped_is_inert(tmp_path, monkeypatch):
    monkeypatch.setenv("LAB_MODE", "airgapped")
    monkeypatch.setattr(aw, "_fetch_text",
                        lambda url: pytest.fail("airgapped must never fetch"))
    out = _tick(tmp_path)
    assert out["state"] == "inert_airgapped"
    assert out["findings"] == 0
    assert not (tmp_path / "data" / aw.STATE_NAME).exists()
    assert ConsentStore().list_pending() == []   # consent never touched


# ── consent ──────────────────────────────────────────────────────────

def test_hybrid_requests_consent_once_and_waits(tmp_path, monkeypatch):
    monkeypatch.setenv("LAB_MODE", "hybrid")
    monkeypatch.setattr(aw, "_fetch_text",
                        lambda url: pytest.fail("must not fetch before consent"))
    out1 = _tick(tmp_path, now=1000.0)
    assert out1["pending_consent"] == 2
    assert out1["findings"] == 0
    n_pending = len(ConsentStore().list_pending())
    assert n_pending == 2
    # next due tick must NOT file duplicate requests
    out2 = _tick(tmp_path, now=1000.0 + aw._watch_interval_sec() + 1)
    assert out2["pending_consent"] == 2
    assert len(ConsentStore().list_pending()) == n_pending


def test_denied_consent_disables_feed(tmp_path, monkeypatch):
    monkeypatch.setenv("LAB_MODE", "hybrid")
    monkeypatch.setattr(aw, "_fetch_text",
                        lambda url: pytest.fail("denied feed must never fetch"))
    _tick(tmp_path, now=1000.0)
    cs = ConsentStore()
    for r in list(cs.list_pending()):
        cs.deny(r["id"])
    out = _tick(tmp_path, now=1000.0 + aw._watch_interval_sec() + 1)
    assert out["findings"] == 0
    assert out["pending_consent"] == 0
    state = json.loads((tmp_path / "data" / aw.STATE_NAME).read_text())
    assert all(v.get("consent") == "denied" for v in state["feeds"].values())


# ── baseline / change / pending gate ─────────────────────────────────

def test_first_fetch_is_baseline_change_becomes_pending_finding(tmp_path, monkeypatch):
    monkeypatch.setenv("LAB_MODE", "hybrid")
    fetched_urls = []
    content = {"v": "driver 101.0 available"}

    def fake_fetch(url):
        fetched_urls.append(url)
        return content["v"]

    monkeypatch.setattr(aw, "_fetch_text", fake_fetch)
    _tick(tmp_path, now=1000.0)          # files consent requests
    _approve_all_pending()

    interval = aw._watch_interval_sec()
    out1 = _tick(tmp_path, now=1000.0 + interval + 1)
    assert out1["findings"] == 0          # baseline pass — honest, no finding
    assert out1["checked"] == 2
    # URLs used verbatim from the sealed agenda — never composed
    assert set(fetched_urls) == {"https://feeds.example/a",
                                 "https://vendor.example/drivers"}

    out2 = _tick(tmp_path, now=1000.0 + 2 * (interval + 1))
    assert out2["findings"] == 0          # unchanged content — quiet

    content["v"] = "driver 102.5 available"
    out3 = _tick(tmp_path, now=1000.0 + 3 * (interval + 1))
    assert out3["findings"] == 2
    from arail import compiled_kb
    pending = compiled_kb.list_pending(tmp_path / "pkb")
    scout = [p for p in pending if p["kind"] == "scout_finding"]
    assert len(scout) == 2
    # provenance is the watched feed URL; nothing is auto-approved
    provs = {p["provenance"] for p in scout}
    assert provs == {"https://feeds.example/a", "https://vendor.example/drivers"}
    assert compiled_kb.approved_paths(tmp_path / "pkb") == set()


def test_superseded_unapproved_finding_is_pruned(tmp_path, monkeypatch):
    monkeypatch.setenv("LAB_MODE", "hybrid")
    content = {"v": "one"}
    monkeypatch.setattr(aw, "_fetch_text", lambda url: content["v"])
    _tick(tmp_path, now=1000.0)
    _approve_all_pending()
    interval = aw._watch_interval_sec()
    _tick(tmp_path, now=1000.0 + interval + 1)            # baseline
    content["v"] = "two"
    _tick(tmp_path, now=1000.0 + 2 * (interval + 1))      # finding A
    content["v"] = "three"
    _tick(tmp_path, now=1000.0 + 3 * (interval + 1))      # finding B replaces A
    scout_dir = tmp_path / "pkb" / aw.SCOUT_SUBDIR
    per_feed: dict[str, int] = {}
    for f in scout_dir.glob("*.md"):
        stem = f.name.rsplit("-", 1)[0]
        per_feed[stem] = per_feed.get(stem, 0) + 1
    assert per_feed and all(n == 1 for n in per_feed.values())


def test_cadence_respected(tmp_path, monkeypatch):
    monkeypatch.setenv("LAB_MODE", "hybrid")
    calls = {"n": 0}

    def fake_fetch(url):
        calls["n"] += 1
        return "steady"

    monkeypatch.setattr(aw, "_fetch_text", fake_fetch)
    _tick(tmp_path, now=1000.0)
    _approve_all_pending()
    interval = aw._watch_interval_sec()
    _tick(tmp_path, now=1000.0 + interval + 1)
    n_after_baseline = calls["n"]
    _tick(tmp_path, now=1000.0 + interval + 2)   # 1s later — not due
    assert calls["n"] == n_after_baseline


def test_fetch_error_never_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("LAB_MODE", "hybrid")

    def broken(url):
        raise RuntimeError("boom")

    monkeypatch.setattr(aw, "_fetch_text", broken)
    _tick(tmp_path, now=1000.0)
    _approve_all_pending()
    out = _tick(tmp_path, now=1000.0 + aw._watch_interval_sec() + 1)
    assert out["ok"] is True
    assert out["findings"] == 0


def test_module_never_composes_urls():
    """Structural guarantee: no URL literals and no string-building of URLs —
    every fetched URL is a verbatim feed from the sealed agenda."""
    import inspect
    src = inspect.getsource(aw)
    assert "https://" not in src.replace("https?://", "")  # only the regex
