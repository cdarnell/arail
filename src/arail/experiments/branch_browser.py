"""arail.experiments.branch_browser — Read-only enumeration of
autoresearch git branches.

Kept separate from git_ops.py deliberately: that module's small
ALLOWED_WRITABLE_FILES whitelist is load-bearing for the safety
model and is asserted by tests. This module is read-only throughout.

Public API:

    list_autoresearch_branches(backend="all", limit=100) -> List[BranchSummary]
    branch_commits(branch: str) -> List[CommitRow]
    branch_diff_summary(branch: str) -> dict

Safety:
    - Every public function validates branch with _validate_branch().
    - subprocess.run([...]) only — never shell=True.
    - No write ops, no checkout, no push, no delete.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional


# ── Constants ────────────────────────────────────────────────────

BRANCH_PREFIX = "autoresearch/"

# Strict regex: only alphanumeric, dot, underscore, hyphen after the prefix.
# Blocks path traversal (../) and shell metacharacters.
_BRANCH_RE = re.compile(r"^autoresearch/[A-Za-z0-9._-]+$")

# Outcome classification from the commit subject line produced by
# git_ops.commit_experiment via autoresearch._build_commit_message.
# Subject format: "tune(<backend>): <label> from token 0 — +15.1% tok/s vs baseline"
_WIN_RE = re.compile(
    r"^tune\((\w+)\):\s+(.+?)\s+(?:from token \d+\s+)?[—\-]+\s+([+-][\d.]+)%",
    re.IGNORECASE,
)
# "bench(<backend>): capture baseline"
_BASELINE_RE = re.compile(r"^bench\((\w+)\):\s+capture baseline", re.IGNORECASE)

_BENCH_FILES = {
    "aerollm": "lab/data/aerollm-bench.jsonl",
    "mlx": "lab/data/mlx-bench.jsonl",
}


# ── Dataclasses ──────────────────────────────────────────────────

@dataclass
class BranchSummary:
    """One autoresearch/* branch, enriched with status and headline metric."""
    branch: str            # "autoresearch/20260507-094312-kv-8bit"
    exp_id: str
    backend: str           # "aerollm" | "mlx" | "unknown"
    base_short_sha: str
    head_short_sha: str
    commit_count: int
    status: str            # "win" | "loss" | "running" | "baseline" | "unknown"
    headline: Optional[Dict[str, Any]]  # {label, tok_per_sec, baseline_tok_per_sec, delta_pct, ttft_ms}
    when_created: str      # ISO-8601
    diff_url: Optional[str]


@dataclass
class CommitRow:
    """One commit in a branch's log."""
    sha: str
    short_sha: str
    subject: str
    body: str
    author: str
    when: str
    diff_url: Optional[str]


# ── Internal helpers ─────────────────────────────────────────────

def _repo_root() -> Path:
    """Resolve the repo root from this file's location."""
    return Path(__file__).resolve().parent.parent.parent.parent


def _run(args: List[str], *, check: bool = False) -> subprocess.CompletedProcess:
    """Run git with args from the repo root. Never shell=True."""
    return subprocess.run(
        ["git"] + args,
        cwd=_repo_root(),
        capture_output=True,
        text=True,
        check=check,
    )


def _validate_branch(branch: str) -> None:
    """Raise ValueError if the branch name is not a safe autoresearch/ name."""
    if not _BRANCH_RE.match(branch):
        raise ValueError(
            f"invalid branch name {branch!r}: must match "
            r"^autoresearch/[A-Za-z0-9._-]+$"
        )


def _diff_url_for_sha(sha: str) -> Optional[str]:
    """Best-effort GitHub diff URL for a SHA. Returns None if remote not GitHub."""
    try:
        url = _run(["remote", "get-url", "origin"]).stdout.strip()
    except Exception:
        return None
    if not url:
        return None
    repo_part: Optional[str] = None
    if url.startswith("git@github.com:"):
        repo_part = url[len("git@github.com:"):]
    elif url.startswith("https://github.com/"):
        repo_part = url[len("https://github.com/"):]
    if not repo_part:
        return None
    if repo_part.endswith(".git"):
        repo_part = repo_part[:-4]
    return f"https://github.com/{repo_part}/commit/{sha}"


def _base_sha(branch: str) -> str:
    """Compute the merge-base SHA between main and branch.

    Fallback chain:
      1. git merge-base main <branch>
      2. git merge-base origin/HEAD <branch>
      3. git rev-list --max-parents=0 HEAD  (root commit)
    """
    for base_ref in ("main", "origin/HEAD"):
        r = _run(["merge-base", base_ref, branch])
        if r.returncode == 0:
            sha = r.stdout.strip()
            if sha:
                return sha
    # Last resort: repo root commit
    r = _run(["rev-list", "--max-parents=0", "HEAD"])
    return r.stdout.strip() or ""


def _classify_head_commit(
    subject: str,
) -> tuple[str, str, Optional[Dict[str, Any]]]:
    """Return (status, backend, headline_dict) from a head commit subject.

    status: "win" | "baseline" | "loss" | "unknown"
    """
    # Win: tune(<backend>): <label> — +/-delta%
    m = _WIN_RE.match(subject)
    if m:
        backend = m.group(1)
        label = m.group(2).strip()
        try:
            delta_pct = float(m.group(3))
        except ValueError:
            delta_pct = 0.0
        status = "win" if delta_pct >= 0 else "loss"
        headline: Dict[str, Any] = {
            "label": label,
            "delta_pct": delta_pct,
        }
        return status, backend, headline

    # Baseline capture
    m2 = _BASELINE_RE.match(subject)
    if m2:
        backend = m2.group(1)
        return "baseline", backend, None

    return "unknown", "unknown", None


@lru_cache(maxsize=64)
def _load_bench_file_cached(path_str: str, mtime: float) -> List[Dict[str, Any]]:
    """Load a bench JSONL into a list, keyed by (path, mtime) for LRU invalidation.

    The mtime parameter is intentionally part of the cache key so that
    new rows written to disk automatically bust the cache on next access.
    """
    rows: List[Dict[str, Any]] = []
    p = Path(path_str)
    if not p.exists():
        return rows
    try:
        text = p.read_text()
    except OSError:
        return rows
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def _latest_bench_for_branch(branch: str) -> Optional[Dict[str, Any]]:
    """Tail-scan both bench JSONL files; return first row matching git_branch == branch.

    Scans in reverse (newest first) and returns on first match.
    LRU-cached by (path, mtime).
    """
    root = _repo_root()
    for _backend, rel_path in _BENCH_FILES.items():
        p = root / rel_path
        if not p.exists():
            continue
        try:
            mtime = p.stat().st_mtime
        except OSError:
            continue
        rows = _load_bench_file_cached(str(p), mtime)
        for row in reversed(rows):
            if row.get("git_branch") == branch:
                return row
    return None


def _enrich_with_bench(
    summary: BranchSummary,
) -> BranchSummary:
    """Fill in headline metrics from bench JSONL if the head commit didn't give them."""
    if summary.headline is not None:
        return summary
    row = _latest_bench_for_branch(summary.branch)
    if row is None:
        return summary
    tps = row.get("decode_tok_per_sec")
    ttft = row.get("ttft_ms")
    outcome = row.get("outcome") or row.get("status")
    if tps is not None:
        summary.headline = {
            "label": row.get("variant_label") or summary.exp_id,
            "tok_per_sec": tps,
            "ttft_ms": ttft,
            "delta_pct": None,
        }
    if outcome in ("win", "loss", "baseline", "running"):
        summary.status = outcome
    return summary


def _count_commits(branch: str, base_sha: str) -> int:
    """Count commits on branch since base_sha."""
    if not base_sha:
        r = _run(["rev-list", "--count", branch])
    else:
        r = _run(["rev-list", "--count", f"{base_sha}..{branch}"])
    if r.returncode != 0:
        return 0
    try:
        return int(r.stdout.strip())
    except ValueError:
        return 0


def _current_branch_name() -> str:
    r = _run(["rev-parse", "--abbrev-ref", "HEAD"])
    return r.stdout.strip()


# ── Public API ───────────────────────────────────────────────────

def list_autoresearch_branches(
    backend: str = "all",
    limit: int = 100,
) -> List[BranchSummary]:
    """Enumerate autoresearch/* branches, newest first.

    Args:
        backend: "all" | "aerollm" | "mlx" — filter by detected backend.
        limit: max branches to return.

    Returns:
        List of BranchSummary, sorted by committerdate descending.
    """
    # Tab-delimited fields per ref: refname:short, objectname:short, committerdate:iso-strict
    # Using TAB as separator — safe because none of these git format tokens
    # produce output containing TABs.
    sep = "\t"
    fmt = f"%(refname:short){sep}%(objectname:short){sep}%(committerdate:iso-strict)"
    r = _run([
        "for-each-ref",
        "--sort=-committerdate",
        f"--count={limit}",
        f"--format={fmt}",
        "refs/heads/autoresearch/*",
    ])
    if r.returncode != 0:
        return []

    results: List[BranchSummary] = []

    for line in r.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(sep)
        if len(parts) != 3:
            continue
        branch_name, head_short, when_created = parts

        # Safety: only process valid branch names
        if not _BRANCH_RE.match(branch_name):
            continue

        exp_id = branch_name[len(BRANCH_PREFIX):]

        # Get head commit subject to classify outcome
        r_log = _run([
            "log", "-1",
            "--format=%s",
            branch_name,
        ])
        head_subject = r_log.stdout.strip() if r_log.returncode == 0 else ""

        status, detected_backend, headline = _classify_head_commit(head_subject)

        # Backend filter
        if backend != "all" and detected_backend != "unknown":
            if detected_backend != backend:
                continue

        base_sha = _base_sha(branch_name)
        base_short = base_sha[:7] if base_sha else "unknown"
        commit_count = _count_commits(branch_name, base_sha)

        diff_url = _diff_url_for_sha(head_short)

        summary = BranchSummary(
            branch=branch_name,
            exp_id=exp_id,
            backend=detected_backend,
            base_short_sha=base_short,
            head_short_sha=head_short,
            commit_count=commit_count,
            status=status,
            headline=headline,
            when_created=when_created,
            diff_url=diff_url,
        )

        # Try to enrich with bench JSONL data
        summary = _enrich_with_bench(summary)

        results.append(summary)

    return results


def branch_commits(branch: str) -> List[CommitRow]:
    """Return the commit log for a branch (since its merge-base from main).

    Args:
        branch: must match ^autoresearch/[A-Za-z0-9._-]+$

    Raises:
        ValueError: if branch name is invalid.
    """
    _validate_branch(branch)

    base_sha = _base_sha(branch)
    if base_sha:
        rev_range = f"{base_sha}..{branch}"
    else:
        rev_range = branch

    # Field separator: ASCII Unit Separator (0x1F) — safe in subprocess args.
    # Record separator: ASCII Record Separator (0x1E) — one per commit.
    # Neither appears in git output (SHAs, author names, ISO dates, typical commit text).
    FS = "\x1f"
    RS = "\x1e"
    fmt = f"%H{FS}%h{FS}%an{FS}%aI{FS}%s{FS}%b{RS}"

    r = _run([
        "log",
        rev_range,
        f"--format={fmt}",
    ])
    if r.returncode != 0:
        return []

    rows: List[CommitRow] = []
    for record in r.stdout.split(RS):
        record = record.strip()
        if not record:
            continue
        parts = record.split(FS)
        if len(parts) < 5:
            continue
        sha = parts[0].strip()
        short_sha = parts[1].strip()
        author = parts[2].strip()
        when = parts[3].strip()
        subject = parts[4].strip()
        body = parts[5].strip() if len(parts) > 5 else ""

        rows.append(CommitRow(
            sha=sha,
            short_sha=short_sha,
            subject=subject,
            body=body,
            author=author,
            when=when,
            diff_url=_diff_url_for_sha(short_sha),
        ))

    return rows


def branch_diff_summary(branch: str) -> Dict[str, Any]:
    """Return a diff summary for a branch vs its merge-base.

    Returns:
        {files_changed: int, insertions: int, deletions: int, files: List[str]}

    Raises:
        ValueError: if branch name is invalid.
    """
    _validate_branch(branch)

    base_sha = _base_sha(branch)
    if not base_sha:
        return {"files_changed": 0, "insertions": 0, "deletions": 0, "files": []}

    # --numstat gives: additions TAB deletions TAB filename per line
    r = _run(["diff", "--numstat", base_sha, branch])
    if r.returncode != 0:
        return {"files_changed": 0, "insertions": 0, "deletions": 0, "files": []}

    total_ins = 0
    total_del = 0
    files: List[str] = []

    for line in r.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        ins_str, del_str, fname = parts[0], parts[1], parts[2]
        # Binary files show "-" instead of a number
        try:
            total_ins += int(ins_str)
        except ValueError:
            pass
        try:
            total_del += int(del_str)
        except ValueError:
            pass
        files.append(fname.strip())

    return {
        "files_changed": len(files),
        "insertions": total_ins,
        "deletions": total_del,
        "files": files,
    }
