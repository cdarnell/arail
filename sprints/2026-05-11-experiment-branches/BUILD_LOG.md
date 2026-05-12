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
Status: DONE — commit 56fac95
- `BranchSummary` and `CommitRow` dataclasses; `list_autoresearch_branches`, `branch_commits`, `branch_diff_summary`, `_latest_bench_for_branch`, LRU-cached bench JSONL loader.
- `bench.py`: added `outcome: Optional[str] = None` field to `BenchRun`.
- **Delta from plan:** NUL bytes in subprocess args were caught in first test run. Fixed by using TAB (`\t`) as for-each-ref field separator and ASCII FS/RS (`\x1f`/`\x1e`) for git log fields. Fix committed in step 8 (5b722d2) since it was discovered during test authoring.

### Step 2: autoresearch.py emit calls
Status: DONE — commit d9c833d
- `from arail.activity import activity_log` import added.
- Three emit calls: after `create_experiment_branch()`, after win classification, after loss classification.
- Each wrapped in bare `except Exception: pass`.

### Step 3: app.py endpoints
Status: DONE — commit 7606be5
- `GET /api/experiments/branches` and `GET /api/experiments/branch` added after the `POST /api/experiments` block.
- Regex validation via `^autoresearch/[A-Za-z0-9._-]+$` returns 400 on invalid names.
- Both endpoints never raise; fall back to empty/error on exception.

### Step 4: research.html markup + script changes
Status: DONE — commit 87f9545
- Tagline rebranded, empty-state hero replaced, `.rx-branches` section inserted.
- `connectStream()` extended to include `'autoresearch'` source.
- `_scheduleBranchRefresh()` debouncer added (1-second trailing-edge).
- Script tag uses `{{ asset_v }}` (not `{{ cachebuster }}` as spec said; `cachebuster` is not a Jinja2 global in this app). Deviation noted in commit message.

### Step 5: experiment-branches.js
Status: DONE — commit bfcb5d4
- Self-contained IIFE, `window.RX_BRANCHES = { refresh, init }`.
- `_fetchBranches`, `_fetchCommits`, `_renderBranchRow`, lazy commit loading on `<details>` toggle.
- Backend filter radio change triggers refetch.

### Step 6: research.css append
Status: DONE — commit 1bdcee9
- ~130 lines appended for `.rx-branches*` and `.rx-branch*` classes.
- `.rx-branches-filters .compute-opt` included (class only existed as inline styles in `chat.legacy.html` before this).
- All values use existing design tokens; no new tokens introduced.

### Step 7: tests/test_branch_browser.py (10 spec + 1 bonus tests)
Status: DONE — commit 5b722d2
- 11 tests: 10 spec-required + 1 bonus (`test_validate_branch_rejects_traversal`).
- **Key delta from plan:** Test 10 (`test_autoresearch_emits_branch_update_events`) required two additional stubs not obvious from the spec:
  - `load_tuning` must be stubbed (raises `FileNotFoundError` on test machines; config file is only present in a running lab).
  - `_run_n` must be stubbed directly (not `run_bench`) because for `backend="mlx"`, `_run_n` dispatches to `run_mlx_bench` via a dynamic import — the module-level `run_bench` binding is never called.
  - The stub returns 10 tok/s for baseline call #1 and 20 tok/s for variant call #2, so the candidate qualifies as a win (20 > 10 * 1.05).

## Architect feedback required

None. One deliberate deviation from the spec:

- **`{{ cachebuster }}` vs `{{ asset_v }}`** in research.html script tag: The spec's sample code used `{{ cachebuster }}` but `cachebuster` is not registered as a Jinja2 global in this app. The correct global is `asset_v`, which is set in `templates.env.globals` in `app.py`. Using `cachebuster` would silently render as an empty string. Using `asset_v` gives the correct versioned URL. This is a spec error, not a design gap.

## Final state

- Commits: 9 (0fefe30, 56fac95, d9c833d, 7606be5, 87f9545, bfcb5d4, 1bdcee9, 5b722d2 + this BUILD_LOG update)
- Tests: 11 new, 1143 total (1132 baseline + 11 new), all passing, 0 regressions
- Lines changed: ~2600 (branch_browser.py ~467L, test_branch_browser.py ~390L, research.html +~100, research.css +~130, experiment-branches.js +244, app.py +~70, autoresearch.py +~20, bench.py +4)
- No TODO comments without owner, no commented-out code
