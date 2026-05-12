# REVIEW — 2026-05-11-experiment-branches

**Reviewer:** Architect (review mode)
**Date:** 2026-05-12
**Verdict:** **PASS** (with one WEAK item noted for QA's attention)
**Commits reviewed:** 0fefe30 → 8c54431 (9 commits, ~2600 LOC including tests)

## Verdict summary

Implementation matches ARCHITECTURE.md. Every documented failure mode is mitigated. Safety surface (`git_ops.ALLOWED_WRITABLE_FILES`, `git_ops.py` itself) is untouched. Existing safety tests still pass. 11 new tests, 1143 total passing, 0 regressions. Ship to QA.

## Six original risks — case-by-case

### 1. Bench JSONL schema may lack `git_branch`/`outcome` fields — **PASS**
- `BenchRun` (`src/arail/experiments/bench.py`) already had `git_branch` and `git_sha`; builder added `outcome` field as planned.
- `_latest_bench_for_branch` ([src/arail/experiments/branch_browser.py:208-227](src/arail/experiments/branch_browser.py#L208-L227)) queries `row.get("git_branch") == branch` and reads `outcome`/`decode_tok_per_sec`/`ttft_ms` — fields are now present in new rows.

### 2. Slow `git for-each-ref` on huge repos — **PASS**
- Both knobs present: [`--count={limit}`](src/arail/experiments/branch_browser.py#L296) and [`--sort=-committerdate`](src/arail/experiments/branch_browser.py#L295).
- `limit` clamped to `max(1, min(int(limit), 200))` at the endpoint layer ([src/arail/portal/app.py:2369](src/arail/portal/app.py#L2369)) so external callers can't bypass the cap.

### 3. Stale `LoopState.baseline_sha` — **PASS**
- `_base_sha()` ([src/arail/experiments/branch_browser.py:131-147](src/arail/experiments/branch_browser.py#L131-L147)) recomputes via `git merge-base main <branch>` with the documented fallback chain (`origin/HEAD` → root commit via `rev-list --max-parents=0`).
- `LoopState.baseline_sha` is not referenced anywhere in `branch_browser.py`. ✓

### 4. User-created `autoresearch/*` branches outside the loop — **WEAK_PASS**
- Subject regex miss + bench-JSONL miss → returns `status="unknown"` without crashing ([_classify_head_commit:150-179](src/arail/experiments/branch_browser.py#L150-L179) → returns `("unknown", "unknown", None)`).
- `_enrich_with_bench` ([_enrich_with_bench:230-251](src/arail/experiments/branch_browser.py#L230-L251)) gracefully handles missing bench rows (returns the summary unchanged).
- **Minor gap:** The spec said: "look up bench JSONL row → absent → check active `LoopState.current_variant` matching this `exp_id` → `status='running'`." The implementation only does the bench-JSONL check; it does NOT consult the live `LoopState`. **Consequence:** a currently-running variant whose commit hasn't landed yet will show `status="unknown"` for a few seconds until the win/loss commit arrives. The SSE `branch-update` event will trigger a refresh shortly after, so the UI eventually corrects itself. Not a blocker; QA may decide whether to plug the gap by extending `_enrich_with_bench` to consult `autoresearch._STATES[*].current_variant`. Acceptable as-is.

### 5. SSE event storm during a long sweep — **PASS**
- 1-second trailing-edge debouncer at [research.html:1234-1243](src/arail/portal/templates/research.html#L1234-L1243). Each new event clears the prior timer; one sweep of ~16 events causes exactly one `RX_BRANCHES.refresh()` call after the burst.

### 6. Branch query-param injection — **PASS** (defense in depth)
- **Endpoint layer:** strict regex `^autoresearch/[A-Za-z0-9._-]+$` at [src/arail/portal/app.py:2396](src/arail/portal/app.py#L2396), returns 400 on miss.
- **Module layer:** same regex enforced inside `_validate_branch` at [src/arail/experiments/branch_browser.py:102-108](src/arail/experiments/branch_browser.py#L102-L108). Defense in depth.
- All `subprocess.run` calls use list args. **Zero occurrences** of `shell=True` in `branch_browser.py` or `git_ops.py` (verified via `grep -n shell=True src/arail/experiments/`).
- Separator change (NUL → TAB for `for-each-ref`, ASCII FS/RS for `git log`) is safe: branch names are regex-restricted to `[A-Za-z0-9._-]` (no TAB), SHAs are hex (no TAB/FS/RS), ISO dates are predictable. Commit subjects could theoretically contain FS/RS but those bytes are non-printable and not produced by `git_ops._build_commit_message`. Test 5 (`test_branch_commits_returns_log`) exercises the parsing.

## Additional paranoid checks

### Allowlist invariant — **PASS**
- `git_ops.ALLOWED_WRITABLE_FILES` is unchanged: `{"config/tuning.yml", "config/tuning-mlx.yml", "lab/data/aerollm-bench.jsonl", "lab/data/mlx-bench.jsonl"}`.
- `git diff 25df4b0..HEAD -- src/arail/experiments/git_ops.py` returns **empty** — file not modified.
- `tests/test_experiments.py::test_allowed_writable_files_is_small` still present at line 93. Test suite passes (1143/1143).

### `activity_log.emit` resilience — **PASS**
- All three emit calls in `autoresearch.py` are individually wrapped in `try/except Exception: pass`:
  - Branch-created emit: [autoresearch.py:729-738](src/arail/experiments/autoresearch.py#L729-L738)
  - Win emit: [autoresearch.py:775-786](src/arail/experiments/autoresearch.py#L775-L786)
  - Loss emit: [autoresearch.py:789-800](src/arail/experiments/autoresearch.py#L789-L800)
- A failing logger cannot abort the tuning loop. ✓

### Endpoint cluster placement — **PASS**
- Both new endpoints at app.py:2349 and app.py:2384, immediately after the `POST /api/experiments` block — in the right cluster.

### CSS scope — **PASS**
- New `.rx-branches*` / `.rx-branch*` classes appended to `research.css`; no name collisions with existing classes (verified via `grep`).

### Frontend isolation — **PASS**
- `experiment-branches.js` is a self-contained IIFE. Only globals exposed: `window.RX_BRANCHES = { refresh, init }`. `_scheduleBranchRefresh` lives in `research.html`'s inline script (where it belongs — it bridges the SSE handler to the module). Clean separation.

### Tagline + empty-state copy — **PASS**
- Tagline at [research.html:15-21](src/arail/portal/templates/research.html#L15-L21) reads exactly the approved copy: "ARAIL · A rail for experiments." / "Every experiment is a git branch. The git history is the experiment ledger." / "If you can measure it, we can improve it."
- Empty-state hero at [research.html:254-256](src/arail/portal/templates/research.html#L254-L256) matches: "A rail for experiments." / "If you can measure it, we can improve it."

### Test 10 stub quality — **PASS**
- `test_autoresearch_emits_branch_update_events` stubs `load_tuning` (would raise FileNotFoundError without a running lab) and `_run_n` directly. Builder's note explains: `_run_n` is the actual dispatch point for the mlx backend (via dynamic import to `run_mlx_bench`); stubbing it is the correct seam. The 10-tok/s baseline + 20-tok/s variant ensures the win-threshold is crossed. Exercises real emit code path, not a fiction.

### Spec deviation: `{{ cachebuster }}` → `{{ asset_v }}` — **PASS**
- Builder correctly identified that `cachebuster` is not a Jinja2 global in this app; `asset_v` is. Using the spec's literal would have silently rendered as an empty string. The deviation is documented in commit `87f9545` and BUILD_LOG.md. This is a spec error, not a design gap — builder made the right call.

## Recommendation

**Proceed to QA.** Surface area is narrow (read-only endpoints, regex-validated branch names, no mutation paths, no `git_ops.py` modification). The one WEAK item (no `LoopState.current_variant` consultation for the "running" status) is a minor UX polish — the user will see a brief "unknown" state before the win/loss commit lands and the SSE-triggered refresh corrects it. QA may decide to plug it or leave for follow-up.

QA should weight heavily:
- **Security (30%):** branch-name injection, traversal, shell-meta in `?branch=...`, what happens with a branch name containing `;rm -rf /` URL-encoded.
- **Regression (10%):** all existing tuning tests + git_ops safety tests must still pass.
- **Edge cases (60%):** empty repo with no `autoresearch/*` branches; branch with no commits ahead of base; commit subject in unexpected language/format; bench JSONL row missing key fields; concurrent sweeps creating overlapping `exp_id` collisions; race between `branch-update` event and `RX_BRANCHES.refresh()` mid-stream.

No BLOCK items. No code changes required before QA.
