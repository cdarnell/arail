# ARCHITECTURE — Surface autoresearch git branches in the Research tab

**Sprint ID:** 2026-05-11-experiment-branches
**Status:** Design approved by user, ready to build
**Source plan:** `/Users/netsushi/.claude/plans/we-need-to-get-staged-candy.md`

---

## Context

ARAIL's autoresearch loop already does the magic: each config knob variant runs on its own `autoresearch/<exp_id>` git branch, winners get committed, losers leave the branch as an inspection point, and the bench history persists to JSONL. The whole thing is built on [src/arail/experiments/git_ops.py](../../src/arail/experiments/git_ops.py) (safe-commit primitives) and [src/arail/experiments/autoresearch.py](../../src/arail/experiments/autoresearch.py) (the loop).

But the magic is invisible. The Research tab ([src/arail/portal/templates/research.html](../../src/arail/portal/templates/research.html)) talks about hypotheses and experiments, never about branches or commits. The branches *are* shown — on the separate `tuning.html` page — but users don't find that page, and the branding doesn't sell the thesis.

The thesis to make visible:

> **ARAIL is A-rail for experiments.** Every experiment is a git branch. The git history is the experiment ledger. **If you can measure it, we can improve it.**

This sprint surfaces what already exists. **Read-only.** **Tuning loop only** (the Researcher agent's 6-step loop will be wired to git in a follow-up sprint).

## Approach

Three deliverables:

1. **Rebrand the Research tab tagline and empty-state copy** to lean into "A rail for experiments" and "If you can measure it, we can improve it."
2. **Add a new "Experiment branches" panel** to the Research tab that lists every `autoresearch/*` branch with status, headline metric, and a click-to-expand commit log.
3. **Emit SSE events from the tuning loop** so the panel refreshes live as branches are created and outcomes land.

No mutation endpoints. No checkout. No delete. Users clean up via terminal: `git branch -D autoresearch/*`.

## Backend — new module

**New file: `src/arail/experiments/branch_browser.py`** (~300 lines). Kept separate from `git_ops.py` because that module's small whitelist surface is asserted in `tests/test_experiments.py` and intentionally minimal.

Public API:

```python
@dataclass class BranchSummary:
    branch: str            # "autoresearch/20260507-094312-kv-8bit"
    exp_id: str
    backend: str           # "aerollm" | "mlx" | "unknown"
    base_short_sha: str
    head_short_sha: str
    commit_count: int
    status: str            # "win" | "loss" | "running" | "baseline" | "unknown"
    headline: Optional[dict]  # {label, tok_per_sec, baseline_tok_per_sec, delta_pct, ttft_ms}
    when_created: str      # ISO-8601
    diff_url: Optional[str]

@dataclass class CommitRow:
    sha: str
    short_sha: str
    subject: str
    body: str
    author: str
    when: str
    diff_url: Optional[str]

def list_autoresearch_branches(backend: str = "all", limit: int = 100) -> List[BranchSummary]
def branch_commits(branch: str) -> List[CommitRow]
def branch_diff_summary(branch: str) -> dict   # {files_changed, insertions, deletions, files: [...]}
```

Implementation notes:
- Use `git for-each-ref --sort=-committerdate --count=<limit> --format='%(refname:short)%00%(objectname:short)%00%(committerdate:iso-strict)' refs/heads/autoresearch/*` — NUL-delimited (`%00`) so commit metadata survives parsing; `--count` keeps it fast on big repos.
- **Base SHA**: compute via `git merge-base main <branch>` (fall back to `origin/HEAD`, then `git rev-list --max-parents=0`). Do NOT use `LoopState.baseline_sha` — that's only available for the actively-running sweep.
- **Outcome classification**: parse the head-commit subject. The loop produces subjects like `tune(mlx): kv-8bit from token 0 — +15.1% tok/s vs baseline`. Regex `^tune\((\w+)\): (.+) — ([+-][\d.]+)%` → `status="win"`, `backend`, `label`, `delta_pct`. `bench(<backend>): capture baseline` → `status="baseline"`. No matching commit on the branch → look up bench JSONL row by `git_branch` field; absent → check active `LoopState` for a `current_variant` matching this `exp_id` → `status="running"`. Else → `status="unknown"`.
- **bench JSONL lookup** (`_latest_bench_for_branch`): tail-scan `lab/data/aerollm-bench.jsonl` and `lab/data/mlx-bench.jsonl` reversed; return first row matching `git_branch == branch`. LRU-cache by `(path, mtime)`. **⚠️ Verify the actual row schema in `src/arail/experiments/bench.py` first** — sample rows on disk are stub data without `git_branch`, so the column may need to be added in `bench.append_run` if missing.
- **Safety**: every public function validates `branch.startswith("autoresearch/")` and regex-matches `^autoresearch/[A-Za-z0-9._-]+$`. No shell expansion (always `subprocess.run([...])`, never shell=True). Path traversal blocked at the API layer too.

## Backend — endpoints

Insert in [src/arail/portal/app.py](../../src/arail/portal/app.py) immediately after the `POST /api/experiments` block (~line 2432, in the `/api/experiments/*` cluster). Use **query-param form** for the branch identifier to sidestep slash-in-path issues.

```
GET /api/experiments/branches?backend=all|aerollm|mlx&limit=50
  → { branches: BranchSummary[], count: int, current_branch: str }

GET /api/experiments/branch?branch=autoresearch/<id>
  → { branch, base_short_sha, commits: CommitRow[],
      diff_summary: {files_changed, insertions, deletions, files: [...]} }
```

Validation: reject any `branch` that doesn't match the `autoresearch/` prefix regex. Return 400.

## Backend — SSE wiring in the tuning loop

`activity_log` is **not yet imported** in [src/arail/experiments/autoresearch.py](../../src/arail/experiments/autoresearch.py) — add `from arail.activity import activity_log` at the top.

Add three emit calls, each wrapped in `try/except Exception: pass` so a logging failure can never abort a tuning pass:

1. **After `create_experiment_branch()` returns** (~line 727 in `run_autoresearch`): `activity_log.emit("autoresearch", f"Branch created: {branch}", "info", {"event":"branch-update", "branch":branch, "exp_id":exp_id, "label":label, "backend":backend})`.
2. **Win path** (~line 763, after `result.outcome = "win"` and `result.git_sha = sha`): emit with `"event":"branch-update", "outcome":"win", "delta_pct":..., "backend":backend`, level `"success"`.
3. **Loss path** (~line 765, after `result.outcome = "loss"` and `abort_experiment`): emit with `"event":"branch-update", "outcome":"loss", "delta_pct":...`, level `"info"`.

These also surface in the existing `.rx-activity` panel — exactly the "git history is the experiment ledger" vibe.

## Frontend — research.html

Insert one new `<section class="rx-branches">` between the existing 3-pane layout close (line 222) and the empty-state block (line 224). It renders independently of whether a Researcher goal is active — the tuning loop runs on its own.

Markup uses **only existing design primitives** ([static/research.css](../../src/arail/portal/static/research.css)):

| What | Reused class |
|---|---|
| Status pill (win/loss/running/baseline/unknown) | `.rx-pill` with `.completed` (win, blue), `.running` (pulsing green), `.idle` (muted, loss), `.paused` (amber, baseline), `.error` (red) |
| Branch name + base→head SHA badges | `.rx-chip` and `.rx-chip.domain` |
| Per-branch metric row | `.rx-metrics` / `.rx-metric` with `.rx-metric-val` + `.rx-metric-key` |
| Backend filter (All / MLX / AeroLLM) | `.compute-opt` radio-card pattern from `chat.legacy.html:112` |
| Commit log entries | `.rx-event` with `.success` (win), `.info` (baseline), `.warn` (loss) |
| Empty state | Style after `.rx-brief-empty` (italic, muted) |

Each row collapses to a `<details>` whose summary shows `Commits (N) · view diff ↗`. Lazy-fetch commits on first open.

Add the script tag at the bottom of research.html (~line 1424): `<script src="/static/js/experiment-branches.js?v={{ cachebuster }}"></script>`.

## Frontend — research.css

Append (~120 lines): `.rx-branches`, `.rx-branches-head`, `.rx-branches-kicker`, `.rx-branches-title`, `.rx-branches-meta`, `.rx-branches-filters`, `.rx-branches-list`, `.rx-branch`, `.rx-branch-row`, `.rx-branch-when`, `.rx-branch-headline`, `.rx-branch-commits`, `.rx-branches-empty`. No new design tokens; reuse `--green`, `--blue`, `--amber`, `--muted`, `--s-*`, `--radius`.

## Frontend — new JS module

**New file: `src/arail/portal/static/js/experiment-branches.js`** (~250 lines). Self-contained IIFE. Public surface: `window.RX_BRANCHES = { refresh, init }`.

Responsibilities:
- On `DOMContentLoaded`: fetch `/api/experiments/branches`, render the list.
- Backend filter radio change → refetch with `?backend=...`.
- `<details>` toggle on a row → lazy-fetch `/api/experiments/branch?branch=...`, render commit log inside as `.rx-event` rows.
- "Time ago" formatting locally (no external lib).

**Cross-module hook**: inside research.html's existing inline `connectStream()` (~line 1153–1198), extend the source filter (line 1160) to include `'autoresearch'`, and add: `if (ev.source === 'autoresearch' && ev.data?.event === 'branch-update') { _scheduleBranchRefresh(); }` where `_scheduleBranchRefresh` is a 1-second trailing-edge debouncer calling `window.RX_BRANCHES?.refresh()`. Debounce matters because one sweep can fire ~16 events.

## Branding copy — exact replacement text

**Tagline block** (replace research.html lines 14–22):

```html
<div class="rx-tagline">
  <span class="rx-tagline-icon">◆</span>
  <span class="rx-tagline-text">
    <strong>ARAIL · A rail for experiments.</strong>
    Every experiment is a git branch. The git history is the experiment ledger.
    If you can measure it, we can improve it.
  </span>
</div>
```

**Empty-state hero** (replace research.html ~lines 226–237):

```html
<h1>A rail for experiments.</h1>
<p class="rx-empty-motto">
  If you can measure it, we can improve it.
  <a class="rx-learn-link" href="/docs/agents-explained.md#the-research-loop"
     target="_blank" rel="noopener">📖 How the loop works</a>
</p>
<p>Set a goal and the lab drafts a swarm. Every winning variant becomes a branch —
   <code>autoresearch/&lt;id&gt;</code> — committed to your repo so you can review
   the diff, cherry-pick what works, and ignore what didn't. The ledger writes itself.</p>
```

Do not touch `_nav.html`. Do not rename the `/research` route. Internal package name stays `arail`.

## Risks / decisions to make at build time

1. **Bench JSONL schema may lack `git_branch`/`outcome` fields.** Sample rows on disk show only generic bench metrics. Builder must `Read bench.py` first; if the columns aren't written, add them in `append_run` (cheap, additive, doesn't break old rows since dict iteration handles missing keys). If they're already written but the disk samples are stale stubs, just proceed.
2. **Slow `git for-each-ref` on huge repos.** Mitigated by `--count=<limit>` and `--sort=-committerdate`. 100-default is sufficient.
3. **Stale `LoopState.baseline_sha`.** Avoided — always recompute via `git merge-base`.
4. **User-created `autoresearch/*` branches outside the loop.** Defensive parsing: regex miss + bench-jsonl miss → `status="unknown"`, no crash, just degraded row.
5. **SSE event storm during a long sweep.** Trailing-edge 1s debouncer on the frontend refresh.
6. **Branch query-param injection.** Strict regex `^autoresearch/[A-Za-z0-9._-]+$` at the API boundary; reject `..` and shell metas. Always `subprocess.run([...])`.

## Files to modify

| File | Change |
|---|---|
| `src/arail/experiments/branch_browser.py` | **NEW** — read-only branch enumeration + JSON-row helpers (~300 lines). |
| `src/arail/experiments/autoresearch.py` | Import `activity_log`. Three `emit("autoresearch", …, {"event":"branch-update", …})` calls (branch-created, win, loss). Each wrapped in `try/except: pass`. |
| `src/arail/experiments/bench.py` | **CONDITIONAL** — if `append_run` doesn't already record `git_branch`/`git_sha`/`outcome`, add those fields. Verify first. |
| `src/arail/portal/app.py` | Add two endpoints (`GET /api/experiments/branches`, `GET /api/experiments/branch`) immediately after line 2432. Import `branch_browser`. |
| `src/arail/portal/templates/research.html` | Rebrand tagline (lines 14–22). Rebrand empty-state hero (~lines 226–237). Insert `<section class="rx-branches">` between lines 222 and 224. Add `<script src="/static/js/experiment-branches.js?v={{ cachebuster }}">` near line 1424. Extend `connectStream` source filter (line 1160) to include `'autoresearch'` and dispatch `branch-update` events to a debounced `window.RX_BRANCHES.refresh`. |
| `src/arail/portal/static/research.css` | Append ~120 lines for `.rx-branches*` and `.rx-branch*` classes. Reuse existing design tokens. |
| `src/arail/portal/static/js/experiment-branches.js` | **NEW** — fetch, render, lazy-load commits, SSE-driven refresh (~250 lines). |
| `tests/test_branch_browser.py` | **NEW** — see test strategy below. |

Do not touch: `git_ops.py`, `tuning.py`, `mlx_backend.py`, `nav.js`, `_nav.html`, `tuning.html`, `style.css`. The audited safety surface stays exactly as it is.

## Test strategy

New file `tests/test_branch_browser.py`:
1. `test_list_autoresearch_branches_filters_namespace` — non-prefixed branch excluded.
2. `test_list_autoresearch_branches_classifies_win_from_subject` — `tune(mlx): … — +12.3% tok/s` → `status="win"`, `delta_pct≈12.3`.
3. `test_list_autoresearch_branches_classifies_baseline` — `bench(aerollm): capture baseline` → `status="baseline"`.
4. `test_list_autoresearch_branches_unknown_when_no_marker` — unrelated subject → `status="unknown"`, no crash.
5. `test_branch_commits_returns_log` — NUL-delimited parsing handles bodies with newlines/commas.
6. `test_branch_diff_summary_numstat` — two-file diff counts.
7. `test_endpoint_rejects_non_autoresearch_branch` — `?branch=main` → 400, no shell-out.
8. `test_endpoint_rejects_traversal` — `?branch=autoresearch/../etc` blocked.
9. `test_latest_bench_for_branch_returns_newest` — JSONL tail-scan picks newest.
10. `test_autoresearch_emits_branch_update_events` — monkeypatch `activity_log.emit`, run single-candidate stub, assert at least one `("autoresearch", …, {"event":"branch-update", …})` call.

Existing `tests/test_experiments.py::test_allowed_writable_files_is_small_and_explicit` and all `git_ops` safety tests must still pass — they will, we don't touch those modules.

## Manual verification (E2E, after builder + QA)

1. `./arailctl start` → open `http://127.0.0.1:8080/research`.
2. Verify the new tagline reads "ARAIL · A rail for experiments." with the "If you can measure it…" line.
3. Empty state: `git branch -D autoresearch/*` first, reload `/research`, verify the empty-state hero copy renders and the branches panel shows "No experiment branches yet."
4. Kick off the tuning loop (from `/tuning` or via `./arailctl benchmark_models`). Watch `/research` — branches should appear with `.rx-pill.running`, transition to `.completed` (win) or `.idle` (loss), without page reload.
5. Click a branch's `<details>` — commit log renders inside with `.rx-event` rows. If GitHub remote is set, `diff_url` links resolve.
6. Verify the activity stream below now shows `autoresearch` events.
7. Stress test: spam refreshes during a sweep — verify the debouncer keeps the panel responsive.

## Out of scope

- Wiring the Researcher agent's 6-step loop to git (deferred to follow-up sprint).
- Branch deletion / archive UI (terminal-only for now).
- Branch comparison ("diff variant A vs variant B").
- Pagination beyond the 100-default limit (call out only if it bites in dogfooding).
- New nav-bar entry; the existing `/research` route is where the panel lives.
