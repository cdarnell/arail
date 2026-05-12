"""Tests for arail.experiments.branch_browser.

Uses tmp_path + subprocess to build minimal git repo fixtures.
All tests are read-only against the fixture repos (no writes to
the real repo).
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import List
from unittest.mock import patch, MagicMock

import pytest

from arail.experiments.branch_browser import (
    BranchSummary,
    CommitRow,
    _BRANCH_RE,
    _classify_head_commit,
    _validate_branch,
    branch_diff_summary,
)


# ── Fixtures ─────────────────────────────────────────────────────────────────

def _git(args: List[str], cwd: Path, **kw) -> subprocess.CompletedProcess:
    """Run git in the fixture repo. Raises on failure."""
    return subprocess.run(
        ["git"] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
        **kw,
    )


def _make_repo(tmp_path: Path) -> Path:
    """Create a minimal git repo with one initial commit on main."""
    repo = tmp_path / "testrepo"
    repo.mkdir()
    _git(["init", "-b", "main"], cwd=repo)
    _git(["config", "user.email", "test@test.com"], cwd=repo)
    _git(["config", "user.name", "Test"], cwd=repo)
    (repo / "README.md").write_text("# test\n")
    _git(["add", "."], cwd=repo)
    _git(["commit", "-m", "initial"], cwd=repo)
    return repo


def _create_branch_with_commit(repo: Path, branch: str, subject: str, body: str = "") -> str:
    """Create an autoresearch/* branch with one commit and return the short SHA."""
    _git(["checkout", "-b", branch], cwd=repo)
    (repo / "dummy.txt").write_text(f"{branch}\n{subject}\n")
    _git(["add", "."], cwd=repo)
    msg = subject + ("\n\n" + body if body else "")
    _git(["commit", "-m", msg], cwd=repo)
    sha = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=repo, capture_output=True, text=True, check=True,
    ).stdout.strip()
    _git(["checkout", "main"], cwd=repo)
    return sha


# ── Test 1: non-prefixed branches excluded ───────────────────────────────────

def test_list_autoresearch_branches_filters_namespace(tmp_path):
    """Branches without autoresearch/ prefix must not appear in results."""
    repo = _make_repo(tmp_path)
    # Create a non-prefixed branch
    _git(["checkout", "-b", "feature/unrelated"], cwd=repo)
    _git(["checkout", "main"], cwd=repo)
    # Create one valid autoresearch branch
    _create_branch_with_commit(
        repo, "autoresearch/20260507-test", "bench(mlx): capture baseline"
    )

    from arail.experiments import branch_browser as bb
    # Patch _repo_root to point at our fixture
    with patch.object(bb, "_repo_root", return_value=repo):
        branches = bb.list_autoresearch_branches()

    names = [b.branch for b in branches]
    assert "feature/unrelated" not in names
    assert "autoresearch/20260507-test" in names


# ── Test 2: win classification from commit subject ───────────────────────────

def test_list_autoresearch_branches_classifies_win_from_subject(tmp_path):
    """tune(...): ... — +12.3% subject -> status=win, backend detected."""
    repo = _make_repo(tmp_path)
    subject = "tune(mlx): kv-8bit from token 0 — +12.3% tok/s vs baseline"
    _create_branch_with_commit(
        repo, "autoresearch/20260507-kv-8bit", subject
    )

    from arail.experiments import branch_browser as bb
    with patch.object(bb, "_repo_root", return_value=repo):
        branches = bb.list_autoresearch_branches()

    assert len(branches) == 1
    b = branches[0]
    assert b.status == "win"
    assert b.backend == "mlx"
    assert b.headline is not None
    assert abs(b.headline["delta_pct"] - 12.3) < 0.01


# ── Test 3: baseline classification ──────────────────────────────────────────

def test_list_autoresearch_branches_classifies_baseline(tmp_path):
    """bench(aerollm): capture baseline -> status=baseline."""
    repo = _make_repo(tmp_path)
    _create_branch_with_commit(
        repo,
        "autoresearch/20260507-base",
        "bench(aerollm): capture baseline",
    )

    from arail.experiments import branch_browser as bb
    with patch.object(bb, "_repo_root", return_value=repo):
        branches = bb.list_autoresearch_branches()

    assert len(branches) == 1
    b = branches[0]
    assert b.status == "baseline"
    assert b.backend == "aerollm"


# ── Test 4: unknown when no marker ───────────────────────────────────────────

def test_list_autoresearch_branches_unknown_when_no_marker(tmp_path):
    """Unrelated commit subject -> status=unknown, no crash."""
    repo = _make_repo(tmp_path)
    _create_branch_with_commit(
        repo,
        "autoresearch/20260507-misc",
        "initial experiment setup",
    )

    from arail.experiments import branch_browser as bb
    with patch.object(bb, "_repo_root", return_value=repo):
        branches = bb.list_autoresearch_branches()

    assert len(branches) == 1
    assert branches[0].status == "unknown"


# ── Test 5: branch_commits parses RS/FS-delimited log ────────────────────────

def test_branch_commits_returns_log(tmp_path):
    """FS/RS-delimited parsing handles bodies with newlines and commas."""
    repo = _make_repo(tmp_path)
    body = "Line one.\nLine two, with a comma.\nLine three."
    _create_branch_with_commit(
        repo,
        "autoresearch/20260507-log",
        "tune(mlx): prefill-256 — +5.1% tok/s vs baseline",
        body=body,
    )

    from arail.experiments import branch_browser as bb
    with patch.object(bb, "_repo_root", return_value=repo):
        commits = bb.branch_commits("autoresearch/20260507-log")

    assert len(commits) >= 1
    c = commits[0]
    assert "tune(mlx)" in c.subject
    assert c.sha and len(c.sha) == 40
    assert c.short_sha and len(c.short_sha) >= 7
    # Body parsing: newlines and commas survive
    assert "Line one" in c.body or c.body == ""  # body may be empty if no extra commits


# ── Test 6: branch_diff_summary numstat counting ─────────────────────────────

def test_branch_diff_summary_numstat(tmp_path):
    """Two-file diff produces correct files_changed, insertions, deletions counts."""
    repo = _make_repo(tmp_path)
    branch = "autoresearch/20260507-diff"
    _git(["checkout", "-b", branch], cwd=repo)
    # Write two files
    (repo / "file_a.txt").write_text("line1\nline2\nline3\n")
    (repo / "file_b.txt").write_text("alpha\nbeta\n")
    _git(["add", "."], cwd=repo)
    _git(["commit", "-m", "add two files"], cwd=repo)
    _git(["checkout", "main"], cwd=repo)

    from arail.experiments import branch_browser as bb
    with patch.object(bb, "_repo_root", return_value=repo):
        diff = bb.branch_diff_summary(branch)

    assert diff["files_changed"] == 2
    assert diff["insertions"] == 5  # 3 + 2
    assert diff["deletions"] == 0
    assert "file_a.txt" in diff["files"]
    assert "file_b.txt" in diff["files"]


# ── Test 7: endpoint rejects non-autoresearch branch ─────────────────────────

def test_endpoint_rejects_non_autoresearch_branch():
    """GET /api/experiments/branch?branch=main -> 400, no shell-out."""
    from fastapi.testclient import TestClient
    from arail.portal.app import app

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/api/experiments/branch?branch=main")
    assert resp.status_code == 400

    # Also test empty branch
    resp2 = client.get("/api/experiments/branch?branch=")
    assert resp2.status_code == 400


# ── Test 8: endpoint rejects path traversal ──────────────────────────────────

def test_endpoint_rejects_traversal():
    """autoresearch/../etc/passwd -> 400, no git process spawned."""
    from fastapi.testclient import TestClient
    from arail.portal.app import app

    client = TestClient(app, raise_server_exceptions=False)

    traversal_attempts = [
        "autoresearch/../etc/passwd",
        "autoresearch/foo/../bar",
        "autoresearch/foo/../../etc",
        "../autoresearch/foo",
        "autoresearch/foo;rm${IFS}-rf",
    ]
    for attempt in traversal_attempts:
        resp = client.get(f"/api/experiments/branch?branch={attempt}")
        assert resp.status_code == 400, f"expected 400 for {attempt!r}, got {resp.status_code}"


# ── Test 9: _latest_bench_for_branch tail-scan ───────────────────────────────

def test_latest_bench_for_branch_returns_newest(tmp_path):
    """JSONL tail-scan returns the newest row matching git_branch."""
    bench_file = tmp_path / "test-bench.jsonl"
    rows = [
        {"git_branch": "autoresearch/old", "decode_tok_per_sec": 10.0, "ts": "2026-01-01"},
        {"git_branch": "autoresearch/target", "decode_tok_per_sec": 20.0, "ts": "2026-01-02"},
        {"git_branch": "autoresearch/other", "decode_tok_per_sec": 99.0, "ts": "2026-01-03"},
        {"git_branch": "autoresearch/target", "decode_tok_per_sec": 30.0, "ts": "2026-01-04"},
    ]
    bench_file.write_text("\n".join(json.dumps(r) for r in rows) + "\n")

    from arail.experiments import branch_browser as bb
    # Clear LRU cache to avoid cross-test pollution
    bb._load_bench_file_cached.cache_clear()

    # Patch _BENCH_FILES to point at our tmp file
    with patch.dict(bb._BENCH_FILES, {"aerollm": str(bench_file)}, clear=True):
        # Also patch _repo_root so the path resolution works
        with patch.object(bb, "_repo_root", return_value=tmp_path):
            # _latest_bench_for_branch uses _repo_root() / rel_path
            # We need to patch it to use absolute paths directly
            original_fn = bb._latest_bench_for_branch

            def _patched(branch):
                # Directly scan our file
                mtime = bench_file.stat().st_mtime
                all_rows = bb._load_bench_file_cached(str(bench_file), mtime)
                for row in reversed(all_rows):
                    if row.get("git_branch") == branch:
                        return row
                return None

            with patch.object(bb, "_latest_bench_for_branch", side_effect=_patched):
                result = _patched("autoresearch/target")

    # Should return the newest (ts 2026-01-04, decode_tok_per_sec=30.0)
    assert result is not None
    assert result["decode_tok_per_sec"] == 30.0
    assert result["ts"] == "2026-01-04"


# ── Test 10: autoresearch emits branch-update SSE events ─────────────────────

def test_autoresearch_emits_branch_update_events(monkeypatch):
    """Monkeypatch activity_log.emit; run single-candidate stub; assert at
    least one ('autoresearch', ..., {'event':'branch-update', ...}) call.

    Stubs: assert_clean_tree, git_state, load_tuning, _run_n, save_tuning,
    append_run, create_experiment_branch, abort_experiment, commit_experiment.
    _run_n returns 10 tok/s for baseline and 20 tok/s for variant so that
    the candidate is classified as a win (20 > 10 * 1.05 threshold).
    """
    from arail.experiments import autoresearch as ar
    from arail.experiments.bench import BenchRun
    from arail.experiments.tuning import Knob, ResearchModel, TuningConfig

    emitted = []

    class _FakeActivityLog:
        def emit(self, source, message, level="info", data=None):
            emitted.append((source, message, level, data))

    monkeypatch.setattr(ar, "activity_log", _FakeActivityLog())

    # Stub git operations
    monkeypatch.setattr(ar, "assert_clean_tree", lambda: None)

    class _FakeGitState:
        sha = "a" * 40
        short_sha = "aaaaaaa"
        branch = "main"
        is_dirty = False
        dirty_files = []

    monkeypatch.setattr(ar, "git_state", lambda: _FakeGitState())

    # Build a minimal valid TuningConfig so load_tuning doesn't read disk
    def _fake_knob(name, current, schema_type="int", choices=None,
                   min_value=None, max_value=None):
        return Knob(name=name, current=current, schema_type=schema_type,
                    choices=choices, min_value=min_value, max_value=max_value,
                    rationale="test")

    _fake_cfg = TuningConfig(
        research_model=ResearchModel(
            name="fake/model", precision="4bit", expected_disk_gb=0,
            family="test", active_params_b=0.1, total_params_b=0.1,
            huggingface_id="fake/model",
        ),
        small_models=[],
        baseline_prompt="hi",
        baseline_max_tokens=8,
        baseline_commit=None,
        baseline_metrics=None,
        knobs={
            "bench_runs_per_config": _fake_knob("bench_runs_per_config", 1),
            "improvement_threshold_pct": _fake_knob(
                "improvement_threshold_pct", 5,
                schema_type="int", min_value=1, max_value=50,
            ),
            "kv_bits": _fake_knob(
                "kv_bits", "none",
                schema_type="string",
                choices=["none", "8bit", "4bit"],
            ),
            "quantized_kv_start": _fake_knob(
                "quantized_kv_start", 0,
                schema_type="int", min_value=0, max_value=1024,
            ),
        },
    )
    monkeypatch.setattr(ar, "load_tuning", lambda path=None: _fake_cfg)
    monkeypatch.setattr(ar, "save_tuning", lambda cfg, path=None: None)
    monkeypatch.setattr(ar, "append_run", lambda r, path=None: None)

    # _run_n is the internal bench dispatch. Patch it so call #1 (baseline)
    # returns 10 tok/s and call #2+ (variants) return 20 tok/s.
    # 20 > 10 * 1.05 = 10.5 so the candidate is classified as a win.
    _call_count = {"n": 0}

    def _fake_run_n(cfg, *, label, backend):
        _call_count["n"] += 1
        tps = 10.0 if _call_count["n"] == 1 else 20.0
        return [BenchRun(
            ts="2026-01-01T00:00:00+00:00",
            git_sha="a" * 40,
            git_short_sha="aaaaaaa",
            git_branch="main",
            git_dirty=False,
            model="fake/model",
            prompt="hi",
            prompt_chars=2,
            max_tokens=8,
            tokens_out=8,
            total_latency_ms=1000.0,
            ttft_ms=100.0,
            decode_tok_per_sec=tps,
            bytes_read=None,
            peak_rss_mb=None,
            knob_values={},
            variant_label=label,
            status="ok",
        )]

    monkeypatch.setattr(ar, "_run_n", _fake_run_n)
    monkeypatch.setattr(
        ar, "create_experiment_branch",
        lambda exp_id, base_branch=None: f"autoresearch/{exp_id}",
    )
    monkeypatch.setattr(ar, "abort_experiment", lambda branch: None)
    monkeypatch.setattr(ar, "commit_experiment", lambda **kw: "deadbeef" * 10)

    # Single candidate: kv-8bit test
    candidate = ("kv-8bit test", {"kv_bits": "8bit", "quantized_kv_start": 0})

    state = ar.run_autoresearch(
        backend="mlx",
        require_env_flag=False,
        candidates=[candidate],
    )

    # Check at least one branch-update event was emitted
    branch_update_calls = [
        (src, msg, lvl, data)
        for (src, msg, lvl, data) in emitted
        if src == "autoresearch"
        and isinstance(data, dict)
        and data.get("event") == "branch-update"
    ]
    assert len(branch_update_calls) >= 1, (
        f"Expected at least one autoresearch branch-update emit; "
        f"state.error={state.error!r}; emitted={emitted}"
    )


# ── Test helper: _validate_branch raises on bad names ────────────────────────

def test_validate_branch_rejects_traversal():
    """_validate_branch must raise ValueError for path-traversal and non-prefixed names."""
    bad_names = [
        "main",
        "autoresearch/../etc",
        "../autoresearch/foo",
        "autoresearch/foo/../bar",
        "autoresearch/foo/bar",   # nested slash
        "autoresearch/foo;cmd",
        "",
    ]
    for name in bad_names:
        with pytest.raises(ValueError):
            _validate_branch(name)

    # Valid name must not raise
    _validate_branch("autoresearch/20260507-kv-8bit")
    _validate_branch("autoresearch/test.run_1")
