# Build log: Surface autoresearch git branches in Research tab

**Architecture:** [ARCHITECTURE.md](./ARCHITECTURE.md) at bdfd825
**Started:** 2026-05-11

## Plan

| # | Files | Change | Test | Commit ref |
|---|---|---|---|---|
| 1 | `src/arail/experiments/branch_browser.py` | NEW — BranchSummary, CommitRow dataclasses; list_autoresearch_branches, branch_commits, branch_diff_summary, _latest_bench_for_branch | Minimal smoke test in test_branch_browser.py step 1 | TBD |
| 2 | `src/arail/experiments/bench.py` | CONDITIONAL — add `outcome` field to BenchRun (git_branch/git_sha already present) | tests/test_experiments.py must still pass | TBD |
| 3 | `src/arail/experiments/autoresearch.py` | Add `from arail.activity import activity_log`. Three emit calls (branch-created, win, loss), each wrapped in try/except | test_autoresearch_emits_branch_update_events monkeypatch test | TBD |
| 4 | `src/arail/portal/app.py` | Add GET /api/experiments/branches + GET /api/experiments/branch after POST /api/experiments block (~line 2346). Import branch_browser. | test_endpoint_rejects_non_autoresearch_branch, test_endpoint_rejects_traversal | TBD |
| 5 | `src/arail/portal/templates/research.html` | Rebrand tagline (lines 14-22). Rebrand empty-state hero (~lines 226-237). Insert rx-branches section between lines 222 and 224. Add script tag near line 1430. Extend connectStream source filter (line 1160). | Manual / integration | TBD |
| 6 | `src/arail/portal/static/js/experiment-branches.js` | NEW — IIFE, window.RX_BRANCHES = {refresh, init}, fetch + render, lazy commits, SSE debounce | None (JS, no test harness) | TBD |
| 7 | `src/arail/portal/static/research.css` | Append ~120 lines for .rx-branches* and .rx-branch* classes | None | TBD |
| 8 | `tests/test_branch_browser.py` | NEW — 10 tests covering all spec test cases | All 10 must pass | TBD |

**Observations before build:**
- `BenchRun` already has `git_branch` and `git_sha` fields. Missing: `outcome` field. Need to add it.
- `POST /api/experiments` block ends at line 2345. New endpoints go after that.
- `connectStream()` source filter is at line 1160, currently `['researcher', 'goal', 'pkb', 'system']`.
- No `js/` subdirectory under `static/` — need to create it.
- research.html lines 14-22: current tagline block. lines 222-224: boundary for section insert. lines 226-237: empty-state hero.
- Script tags near line 1430 (actual last script tag is at line 1430: nav.js).

## Execution

### Step 1: branch_browser.py + bench.py outcome field
Status: PENDING

### Step 2: autoresearch.py emit calls
Status: PENDING

### Step 3: app.py endpoints
Status: PENDING

### Step 4: research.html markup + script changes
Status: PENDING

### Step 5: experiment-branches.js
Status: PENDING

### Step 6: research.css append
Status: PENDING

### Step 7: tests/test_branch_browser.py (10 tests)
Status: PENDING

## Architect feedback required

None at this time.

## Final state

TBD
