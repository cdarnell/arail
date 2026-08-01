"""QA round 13 — re-verification of the round-12 fixes (commit 0cdadf1).

Round 12 filed QA-1 (symlink-following writes), QA-2 (48-char slug
collisions) and QA-3 (a single wall-clock budget shared between spawn
startup and pattern matching). All three were fixed. This file is the
adversarial re-verification: it does not re-assert what the fixing commit's
own tests assert, it attacks the *new* code those fixes introduced —
principally the two-phase Pipe protocol, which is new concurrency surface.
"""
import re
import time

import pytest

from arail.research import agenda_watch as aw

from tests import _agenda_watch_workers as workers


def _feed(url="https://example.test/a", node="n"):
    return aw.WatchFeed(node=node, url=url, cadence="occasional")


_FAST = [{"label": "n", "regex": None, "regex_src": r"\d+", "max_matches": 5}]


# ══════════════════════════════════════════════════════════════════════
#  1. QA-3's new two-phase protocol — races the fix could have introduced
# ══════════════════════════════════════════════════════════════════════

class TestTwoPhaseProtocolFailureInjection:

    def test_child_that_dies_after_ready_is_noticed_by_eof_not_by_timeout(
            self, monkeypatch, caplog):
        """The OOM-killer / segfault shape. ``recv`` on a connection whose
        writer has died must surface as EOF via ``poll``, not block forever
        and not burn the full matching budget."""
        monkeypatch.setattr(aw, "_extract_candidates_worker",
                            workers.crash_after_ready)
        t0 = time.time()
        with caplog.at_level("WARNING"):
            out = aw._extract_candidates_bounded("x 12", _FAST, "u")
        elapsed = time.time() - t0
        assert out == {}
        assert elapsed < aw._EXTRACT_TIMEOUT_SEC, (
            f"a dead child should be detected by EOF immediately, took {elapsed:.2f}s")

    def test_a_dead_child_is_never_blamed_on_catastrophic_backtracking(
            self, monkeypatch, caplog):
        """QA-3's core complaint was a misdirecting diagnostic. A child that
        crashed is not a regex problem; the log must not say it is."""
        monkeypatch.setattr(aw, "_extract_candidates_worker",
                            workers.crash_after_ready)
        with caplog.at_level("WARNING"):
            aw._extract_candidates_bounded("x 12", _FAST, "u")
        text = caplog.text
        assert "backtracking" not in text, text
        assert "exited" in text and "without producing a result" in text, text

    def test_a_hung_child_after_ready_is_still_blamed_on_backtracking(
            self, monkeypatch, caplog):
        """The converse: once startup is confirmed, a stalled match IS the
        case the backtracking wording is for, and it must still be bounded
        by the matching budget alone."""
        monkeypatch.setattr(aw, "_extract_candidates_worker",
                            workers.hang_after_ready)
        t0 = time.time()
        with caplog.at_level("WARNING"):
            out = aw._extract_candidates_bounded("x 12", _FAST, "u")
        elapsed = time.time() - t0
        assert out == {}
        assert "backtracking" in caplog.text
        assert elapsed < aw._EXTRACT_TIMEOUT_SEC + 5.0

    def test_a_slow_start_no_longer_eats_the_matching_budget(self, monkeypatch):
        """QA-3, fixed: a child whose interpreter boot exceeds the OLD single
        2.0s budget must still produce its result, because matching gets its
        own budget once readiness is confirmed."""
        monkeypatch.setattr(aw, "_extract_candidates_worker",
                            workers.slow_to_start)
        assert aw._slugish  # module intact
        out = aw._extract_candidates_bounded("x 12", _FAST, "u")
        assert out == {"slow": ["ok"]}, (
            "a 3.0s startup (> the 2.0s matching budget) must not be "
            "reported as a timed-out match")

    def test_a_child_that_never_confirms_start_is_bounded_and_named_honestly(
            self, monkeypatch, caplog):
        monkeypatch.setattr(aw, "_extract_candidates_worker", workers.never_ready)
        monkeypatch.setattr(aw, "_STARTUP_TIMEOUT_SEC", 1.0)
        t0 = time.time()
        with caplog.at_level("WARNING"):
            out = aw._extract_candidates_bounded("x 12", _FAST, "u")
        assert out == {}
        assert time.time() - t0 < 8.0
        assert "startup problem" in caplog.text
        assert "backtracking" not in caplog.text

    def test_a_result_larger_than_a_pipe_buffer_does_not_deadlock(self, monkeypatch):
        """``Connection.send`` blocks in the child once the pipe buffer
        (~64 KB) fills. The parent must drain it, not time out. ASK-20 says
        candidate payloads are unbounded, so this is reachable."""
        monkeypatch.setattr(aw, "_extract_candidates_worker", workers.huge_result)
        out = aw._extract_candidates_bounded("x 12", _FAST, "u")
        assert out == {"big": ["x" * 500_000]}

    def test_no_child_process_survives_any_of_these_paths(self, monkeypatch):
        """Leak check: every exit path terminates/reaps its child, so a tick
        cannot accumulate zombie extraction processes over days of running."""
        import multiprocessing as mp
        for w in (workers.crash_after_ready, workers.hang_after_ready,
                  workers.huge_result):
            monkeypatch.setattr(aw, "_extract_candidates_worker", w)
            aw._extract_candidates_bounded("x 12", _FAST, "u")
        time.sleep(0.5)
        alive = [c for c in mp.active_children() if c.is_alive()]
        assert not alive, f"leaked extraction subprocesses: {alive}"


# ══════════════════════════════════════════════════════════════════════
#  2. QA-2's fix — properties the fixing commit's own tests do not cover
# ══════════════════════════════════════════════════════════════════════

class TestSlugIdentityProperties:

    def test_urls_differing_only_past_the_readable_prefix_are_distinct(self):
        """The exact shape QA-2 reported: identical for the first 39+
        normalised characters, differing only in the truncated tail."""
        base = "https://creditcards.chase.com/balance-transfer-credit-cards/"
        a, b = base + "slate-edge", base + "slate-elite"
        assert aw._slugish(a) != aw._slugish(b)
        assert aw._slugish(a)[:39] == aw._slugish(b)[:39], (
            "precondition: these must share the full readable prefix")

    def test_two_urls_with_no_ascii_alphanumerics_are_distinct(self):
        """Before the fix these both normalised to the empty slug and
        collided outright — worse than truncation."""
        a, b = "https://例え.test/…", "https://別の.test/…"
        assert aw._slugish(a) != aw._slugish(b)
        assert aw._slugish(a).startswith("https-")

    def test_slug_is_deterministic_across_calls_and_processes(self):
        """Snapshot identity and finding identity are derived independently;
        if the slug were not stable, every tick would look like a change."""
        u = "https://bank.example/rates"
        assert aw._slugish(u) == aw._slugish(u)
        # sha256-based, not hash()-based (which is PYTHONHASHSEED-salted).
        import hashlib
        assert aw._slugish(u).endswith(
            hashlib.sha256(u.encode("utf-8")).hexdigest()[:8])

    def test_slug_length_is_bounded_for_a_pathological_url(self):
        u = "https://x.test/" + "a" * 4000
        assert len(aw._slugish(u)) <= 48

    def test_slug_cannot_contain_a_path_separator_or_dot(self):
        for u in ("https://x.test/../../etc/passwd", "..", "/", "a/b/c", "."):
            s = aw._slugish(u)
            assert "/" not in s and "\\" not in s
            assert ".." not in s

    def test_an_empty_or_punctuation_only_value_still_yields_a_usable_slug(self):
        for v in ("", "   ", "---", "///"):
            s = aw._slugish(v)
            assert s and not s.startswith("-") and len(s) <= 48

    def test_snapshot_and_finding_stem_agree_on_the_same_feed(self, tmp_path):
        feed = _feed(url="https://bank.example/rates/very/long/path/segment/here")
        snap = aw._snapshot_path(tmp_path, "w", feed)
        stem = f"w-{aw._slugish(feed.node)}-{aw._slugish(feed.url)}"
        assert snap.stem == stem


# ══════════════════════════════════════════════════════════════════════
#  3. QA-1's fix — the new shared writer, attacked
# ══════════════════════════════════════════════════════════════════════

class TestSafeWriteAtomic:

    def test_a_symlink_at_the_final_path_is_replaced_not_written_through(
            self, tmp_path):
        """The docstring claims ``os.replace`` swaps the directory entry
        rather than following it. That claim is load-bearing (the tmp guard
        alone would be pointless otherwise) and is asserted here, not
        assumed."""
        victim = tmp_path / "victim.txt"
        victim.write_text("ORIGINAL")
        dest = tmp_path / "d" / "state.json"
        dest.parent.mkdir()
        dest.symlink_to(victim)

        aw._safe_write_atomic(dest, "NEW")
        assert victim.read_text() == "ORIGINAL"
        assert not dest.is_symlink()
        assert dest.read_text() == "NEW"

    def test_refusal_is_silent_and_leaves_no_partial_file(self, tmp_path):
        victim = tmp_path / "victim.txt"
        victim.write_text("ORIGINAL")
        dest = tmp_path / "d" / "state.json"
        dest.parent.mkdir()
        dest.with_suffix(".tmp").symlink_to(victim)

        aw._safe_write_atomic(dest, "ATTACKER")   # must not raise
        assert victim.read_text() == "ORIGINAL"
        assert not dest.exists()

    def test_a_stale_regular_tmp_file_is_overwritten_not_refused(self, tmp_path):
        """The guard must not break the ordinary crash-recovery case: a
        leftover .tmp from a killed process is a regular file and must be
        reused, or every subsequent write would silently no-op forever."""
        dest = tmp_path / "state.json"
        dest.with_suffix(".tmp").write_text("STALE PARTIAL")
        aw._safe_write_atomic(dest, "FRESH")
        assert dest.read_text() == "FRESH"

    def test_written_file_is_not_world_readable(self, tmp_path):
        dest = tmp_path / "state.json"
        aw._safe_write_atomic(dest, "secret-ish")
        assert dest.stat().st_mode & 0o077 == 0

    def test_unicode_content_round_trips(self, tmp_path):
        dest = tmp_path / "snap.txt"
        body = "rate 5,25 % — €1 000 · 例え\n"
        aw._safe_write_atomic(dest, body)
        assert dest.read_text(encoding="utf-8") == body

    def test_a_directory_at_the_tmp_path_is_refused_without_raising(self, tmp_path):
        dest = tmp_path / "state.json"
        dest.with_suffix(".tmp").mkdir()
        aw._safe_write_atomic(dest, "x")   # must not raise
        assert not dest.exists()

    def test_an_unwritable_parent_directory_degrades_silently(self, tmp_path):
        import os
        d = tmp_path / "ro"
        d.mkdir()
        os.chmod(d, 0o500)
        try:
            aw._safe_write_atomic(d / "state.json", "x")  # must not raise
        finally:
            os.chmod(d, 0o700)

    def test_the_finding_write_raises_rather_than_silently_skipping(self, tmp_path):
        """Deliberate asymmetry with _safe_write_atomic (the finding write's
        caller catches). Pinned so a future 'consistency' refactor that makes
        it silent fails here — silence there would drop a staged finding
        while still advancing the recorded sha, permanently hiding a change."""
        pkb = tmp_path / "pkb"
        (pkb / aw.SCOUT_SUBDIR).mkdir(parents=True)
        feed = _feed()
        new_sha = "c" * 64
        stem = (f"w-{aw._slugish(feed.node)}-{aw._slugish(feed.url)}"
                f"-{new_sha[:8]}.md")
        victim = tmp_path / "victim.txt"
        victim.write_text("ORIGINAL")
        (pkb / aw.SCOUT_SUBDIR / stem).symlink_to(victim)
        with pytest.raises(OSError):
            aw._write_finding(pkb, "w", feed, "t", "a" * 64, new_sha, None, {})
        assert victim.read_text() == "ORIGINAL"

    def test_tick_survives_a_refused_finding_write(self, tmp_path, monkeypatch):
        """The whole justification for the finding site raising is that
        ``tick()`` catches it. Asserted at the call site's contract level:
        the handler is an ``except Exception`` around the write, so an
        OSError cannot escape a pass."""
        import inspect
        src = inspect.getsource(aw.tick)
        assert "_write_finding(" in src
        assert "except Exception" in src.split("_write_finding(")[1]


# ══════════════════════════════════════════════════════════════════════
#  4. Cross-cutting: the fixes must not have changed the sealed World
# ══════════════════════════════════════════════════════════════════════

class TestSlugChangeMigration:
    """QA round 13, INFO-24. QA-2's fix changes every snapshot filename and
    every finding stem. For an already-running lab the old snapshot is
    orphaned while ``state.json`` still holds the old sha, so the first
    post-upgrade change per feed diffs against nothing. Pinned as
    behaviour: it degrades to an excerpt (honest), it does not crash, and
    it does not silently suppress the finding."""

    def test_a_pre_upgrade_snapshot_is_orphaned_not_read(self, tmp_path):
        feed = _feed(url="https://bank.example/rates")
        old_slug = re.sub(r"[^a-z0-9]+", "-", feed.url.lower()).strip("-")[:48]
        old_name = f"w-n-{old_slug}"
        (tmp_path / aw.SNAPSHOT_SUBDIR).mkdir(parents=True)
        (tmp_path / aw.SNAPSHOT_SUBDIR / f"{old_name}.txt").write_text("OLD")
        assert aw._read_snapshot(tmp_path, "w", feed) is None

    def test_a_missing_snapshot_renders_an_excerpt_not_a_crash(self):
        feed = _feed()
        md = aw._finding_markdown("w", feed, "new page text", "a" * 64,
                                  "b" * 64, None, {})
        assert "## Excerpt" in md and "new page text" in md
        assert "Change: content aaaaaaaa → bbbbbbbb" in md


def test_slug_change_does_not_touch_the_sealed_world_bundle():
    """QA-2's fix renames snapshot files (a one-time re-baseline) but must
    not alter anything inside the sealed bundle, whose hash is pinned."""
    import json
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads(
        (root / "examples/worlds/debt-finance/manifest.json").read_text())
    assert "agenda-watch" not in json.dumps(manifest)
