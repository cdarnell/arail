"""World-generic horizon scouting (agenda_watch): inert in airgapped mode,
consent-gated per feed in hybrid, URLs verbatim from the sealed agenda,
change findings staged as PENDING review items — never auto-approved.
"""

from __future__ import annotations

import json
from pathlib import Path

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


def test_finding_history_retained_up_to_cap(tmp_path, monkeypatch):
    """Unlike the original single-slot behavior, unreviewed findings for the
    same feed are now RETAINED up to a cap (oldest pruned first) rather than
    collapsed to just the latest — a person checking in weekly shouldn't
    lose every intermediate change."""
    monkeypatch.setenv("LAB_MODE", "hybrid")
    content = {"v": "one"}
    monkeypatch.setattr(aw, "_fetch_text", lambda url: content["v"])
    _tick(tmp_path, now=1000.0)
    _approve_all_pending()
    interval = aw._watch_interval_sec()
    _tick(tmp_path, now=1000.0 + interval + 1)            # baseline

    n_changes = aw._MAX_UNREVIEWED_PER_FEED + 2  # deliberately exceed the cap
    for i in range(2, n_changes + 2):
        content["v"] = f"revision {i}"
        _tick(tmp_path, now=1000.0 + i * (interval + 1))

    scout_dir = tmp_path / "pkb" / aw.SCOUT_SUBDIR
    per_feed: dict[str, int] = {}
    for f in scout_dir.glob("*.md"):
        stem = f.name.rsplit("-", 1)[0]
        per_feed[stem] = per_feed.get(stem, 0) + 1
    assert per_feed
    # capped, but not collapsed to one — real history survives
    assert all(n == aw._MAX_UNREVIEWED_PER_FEED for n in per_feed.values())


def test_approved_findings_are_never_pruned(tmp_path, monkeypatch):
    monkeypatch.setenv("LAB_MODE", "hybrid")
    content = {"v": "one"}
    monkeypatch.setattr(aw, "_fetch_text", lambda url: content["v"])
    _tick(tmp_path, now=1000.0)
    _approve_all_pending()
    interval = aw._watch_interval_sec()
    _tick(tmp_path, now=1000.0 + interval + 1)            # baseline
    content["v"] = "two"
    out = _tick(tmp_path, now=1000.0 + 2 * (interval + 1))
    assert out["findings"] > 0
    from arail import compiled_kb
    compiled_kb.approve(out["finding_paths"], tmp_path / "pkb")
    approved_before = set(compiled_kb.approved_paths(tmp_path / "pkb"))
    assert approved_before

    for i in range(3, aw._MAX_UNREVIEWED_PER_FEED + 5):
        content["v"] = f"revision {i}"
        _tick(tmp_path, now=1000.0 + i * (interval + 1))

    scout_dir = tmp_path / "pkb" / aw.SCOUT_SUBDIR
    still_present = {
        f.relative_to(tmp_path / "pkb").as_posix() for f in scout_dir.glob("*.md")
    }
    assert approved_before <= still_present


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


# ── visible-text extraction (generic) ───────────────────────────────

def test_visible_text_strips_script_style_head():
    html = (
        "<html><head><title>t</title><style>.x{color:red}</style></head>"
        "<body><script>var x = 1;</script>"
        "<p>Real balance-transfer rate: 7.99% APR</p></body></html>"
    )
    text = aw._visible_text(html)
    assert "7.99% APR" in text
    assert "var x" not in text
    assert ".x{color:red}" not in text
    assert "<title>t</title>" not in text  # head is stripped wholesale


def test_visible_text_passes_plain_text_through_unchanged():
    plain = "driver 101.0 available"
    assert aw._visible_text(plain) == plain


def test_visible_text_never_raises_on_malformed_markup():
    broken = "<div><p>unterminated tags <span>oops"
    # must not raise; content is still recoverable
    assert "oops" in aw._visible_text(broken)


# ── diff instead of head-of-document excerpt ────────────────────────

def test_finding_shows_diff_once_a_prior_snapshot_exists(tmp_path, monkeypatch):
    monkeypatch.setenv("LAB_MODE", "hybrid")
    content = {"v": "<html><body><p>Rate: 8.99% APR</p></body></html>"}
    monkeypatch.setattr(aw, "_fetch_text", lambda url: content["v"])
    _tick(tmp_path, now=1000.0)
    _approve_all_pending()
    interval = aw._watch_interval_sec()
    _tick(tmp_path, now=1000.0 + interval + 1)  # baseline — no finding yet

    content["v"] = "<html><body><p>Rate: 7.49% APR</p></body></html>"
    out = _tick(tmp_path, now=1000.0 + 2 * (interval + 1))
    assert out["findings"] > 0
    path = tmp_path / "pkb" / out["finding_paths"][0]
    body = path.read_text()
    assert "## Change (unified diff" in body
    assert "7.49% APR" in body
    assert "<html>" not in body  # markup stripped before diffing/rendering


def test_first_change_with_no_snapshot_falls_back_to_excerpt(tmp_path, monkeypatch):
    # Baseline write happens on first successful fetch, so this specifically
    # exercises the excerpt fallback path via a fresh feed with no snapshot.
    body = aw._finding_markdown(
        "testworld", aw.WatchFeed(node="n", url="https://feeds.example/a",
                                   cadence="occasional"),
        text="some fresh content here", old_sha="a" * 8, new_sha="b" * 8,
        old_text=None, candidates={})
    assert "## Excerpt" in body
    assert "some fresh content here" in body


# ── World-declared extraction patterns (generic mechanism) ──────────

def _write_patterns(staged_dir, patterns):
    (staged_dir / aw.SCOUT_PATTERNS_FILE).write_text(json.dumps({
        "schema": "arail.scout-patterns/v1",
        "patterns": patterns,
    }))


def test_candidate_values_extracted_and_rendered(tmp_path, monkeypatch):
    _write_patterns(tmp_path / "staged", [
        {"label": "apr_percent", "regex": r"\b\d{1,2}\.\d{2}%\s*APR\b",
         "max_matches": 5},
    ])
    monkeypatch.setenv("LAB_MODE", "hybrid")
    content = {"v": "Intro rate 0.00% APR then 24.99% APR after 18 months"}
    monkeypatch.setattr(aw, "_fetch_text", lambda url: content["v"])
    _tick(tmp_path, now=1000.0)
    _approve_all_pending()
    interval = aw._watch_interval_sec()
    _tick(tmp_path, now=1000.0 + interval + 1)  # baseline
    content["v"] = "Intro rate 0.00% APR then 19.99% APR after 18 months"
    out = _tick(tmp_path, now=1000.0 + 2 * (interval + 1))
    assert out["findings"] > 0
    body = (tmp_path / "pkb" / out["finding_paths"][0]).read_text()
    assert "Candidate values (code-extracted, unverified)" in body
    assert "0.00% APR" in body and "19.99% APR" in body
    assert "not verified" in body


def test_works_identically_for_a_non_finance_pattern(tmp_path, monkeypatch):
    """The same mechanism, with a driver-version-shaped pattern instead of an
    APR one — proves the module has no finance-specific knowledge baked in."""
    _write_patterns(tmp_path / "staged", [
        {"label": "driver_version", "regex": r"\b\d{3}\.\d{2}\b",
         "max_matches": 3},
    ])
    monkeypatch.setenv("LAB_MODE", "hybrid")
    content = {"v": "Latest driver: 551.23"}
    monkeypatch.setattr(aw, "_fetch_text", lambda url: content["v"])
    _tick(tmp_path, now=1000.0)
    _approve_all_pending()
    interval = aw._watch_interval_sec()
    _tick(tmp_path, now=1000.0 + interval + 1)  # baseline
    content["v"] = "Latest driver: 560.45"
    out = _tick(tmp_path, now=1000.0 + 2 * (interval + 1))
    body = (tmp_path / "pkb" / out["finding_paths"][0]).read_text()
    assert "560.45" in body
    assert "driver_version" in body


def test_missing_scout_patterns_file_changes_nothing():
    # Absent sidecar (the common case for most Worlds) → empty pattern list,
    # not an error.
    assert aw._load_scout_patterns(Path("/nonexistent/staged/dir")) == []


def test_malformed_scout_patterns_file_ignored_not_crashed(tmp_path, caplog):
    staged = tmp_path / "staged"  # already created by the autouse _iso fixture
    (staged / aw.SCOUT_PATTERNS_FILE).write_text("not valid json {{{")
    assert aw._load_scout_patterns(staged) == []

    (staged / aw.SCOUT_PATTERNS_FILE).write_text(json.dumps({
        "schema": "arail.scout-patterns/v1",
        "patterns": [{"label": "bad", "regex": "("}],  # invalid regex
    }))
    assert aw._load_scout_patterns(staged) == []


def test_oversized_pattern_regex_rejected(tmp_path):
    staged = tmp_path / "staged"  # already created by the autouse _iso fixture
    _write_patterns(staged, [
        {"label": "too_long", "regex": "x" * (aw._MAX_PATTERN_LEN + 1)},
    ])
    assert aw._load_scout_patterns(staged) == []


def test_pattern_match_count_is_bounded(tmp_path):
    staged = tmp_path / "staged"  # already created by the autouse _iso fixture
    _write_patterns(staged, [
        {"label": "digits", "regex": r"\d", "max_matches": 1000},
    ])
    patterns = aw._load_scout_patterns(staged)
    assert patterns[0]["max_matches"] == aw._MAX_PATTERN_MATCHES
    candidates = aw._extract_candidates("1234567890" * 5, patterns)
    assert len(candidates["digits"]) == aw._MAX_PATTERN_MATCHES
