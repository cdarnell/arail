# Build log: aerollm-72b-lift

**Architecture:** SPRINT.md + /Users/netsushi/.claude/plans/pure-forging-pizza.md § Phase 3
**Started:** 2026-05-20

## Plan

| # | Files | Change | Test | Commit ref |
|---|---|---|---|---|
| 1 | `pyproject.toml`, `scripts/setup.sh` | (a) lift `aerollm_maximus` 7B→72B; (b) add `aerollm_minimalist`=7B; (c) keep `aerollm` legacy alias=7B; (d) fix MIN_ID stomp in `load_pyproject_metadata`; (e) add per-tier `case` in `capture_tier`; (f) lift `AEROLLM_MODEL_MAX_ID` shell default to 72B; (g) update comments; (h) add RAM-headroom warn for maximus 72B selection | — | — |
| 2 | `tests/test_aerollm_tier_resolution.py` | New test file: pyproject keys correct, MIN_ID→7B / MAX_ID→72B, tier resolution minimalist→7B / maximus→72B, no MIN_ID stomp | ✓ test-first | — |

## Execution

### Step 1 — pyproject.toml + scripts/setup.sh
No deltas from plan. Four sub-changes in one commit:

1. **pyproject.toml `[tool.arail.models]`:** `aerollm_maximus` lifted to
   `mlx-community/Qwen2.5-72B-Instruct-4bit`; `aerollm_minimalist` added
   at `mlx-community/Qwen2.5-7B-Instruct-4bit`; `aerollm` legacy alias
   kept at 7B; comment block rewritten to document the per-tier split and
   ~40 GB resident / 48 GB+ requirement.

2. **setup.sh shell defaults (~lines 73-81):** `AEROLLM_MODEL_MAX_ID`
   lifted to `mlx-community/Qwen2.5-72B-Instruct-4bit` (was Llama-3.1-70B
   placeholder); comment updated to Qwen2.5-72B.

3. **setup.sh `load_pyproject_metadata` line 115 — Bug 1 fix (MIN_ID
   stomp):** Changed `AEROLLM_MODEL_MIN_ID` lookup from leading with
   `aerollm_maximus` to leading with `aerollm_minimalist`. Previously,
   the moment `aerollm_maximus` was lifted to 72B, every minimalist
   install would have resolved MIN_ID to 72B → OOM on 16 GB Macs.

4. **setup.sh `capture_tier` — Bug 2 fix (no per-tier resolution) +
   RAM warning:** Replaced the flat `AEROLLM_MODEL_ID="${AEROLLM_MODEL_ID:-...}"`
   with a `case "$LAB_TIER"` block mirroring the AirLLM pattern:
   `maximus` picks MAX_ID (72B), `*` picks MIN_ID (7B). Added a
   RAM-headroom `warn` (non-fatal) for maximus when detected system RAM
   is below 48 GB, using `sysctl hw.memsize` on macOS and `/proc/meminfo`
   on Linux. The `AEROLLM_MODEL` .env override at line ~1140 is untouched.

`bash -n scripts/setup.sh` confirmed syntax OK.

Commit: 919daa1

### Step 2 — tests/test_aerollm_tier_resolution.py
No deltas from plan. 12 tests across three groups:

- **pyproject.toml key assertions (4 tests):** direct key checks for
  `aerollm_maximus`, `aerollm_minimalist`, `aerollm` legacy alias, and
  a sanity check that maximus != minimalist.

- **Loader resolution chain (3 tests):** Python simulation of the exact
  `models.get(...)` fallback chain from `load_pyproject_metadata`. Proves
  MIN_ID→7B, MAX_ID→72B, and explicit guard that MIN_ID is not the 72B
  (belt-and-suspenders lock for Bug 1).

- **Tier case simulation (5 tests):** Python simulation of the corrected
  `capture_tier` case block. Proves maximus→72B, minimalist→7B,
  unknown_tier→7B (wildcard arm), and both legacy min/max aliases.

The shell-level `capture_tier` is shell-only; rather than inventing a
bespoke bash test harness, the loader and tier logic are tested by
mirroring the exact Python dict-lookup chain in Python. This approach
matches the existing `test_setup_extras.py` pattern (reads pyproject
directly via Path).

All 12 tests pass. Full suite: 14 pre-existing failures unchanged,
1922 passed (vs 1910 baseline — 12 new tests added, all green).

Commit: fec456e

## Architect feedback required

None.

## Final state

- Tests: 12 new, all passing; 14 pre-existing failures unchanged (unrelated).
- Full suite: 14 failed / 1922 passed / 1 xfailed (baseline was 14/1910/1).
- Lines changed: pyproject.toml +19/-7; scripts/setup.sh +33/-7;
  tests/test_aerollm_tier_resolution.py +212 new.
- `bash -n scripts/setup.sh`: syntax OK.
- Minimalist → 7B: confirmed by test_tier_minimalist_selects_7b and
  test_loader_min_id_resolves_to_7b.
- Maximus → 72B: confirmed by test_tier_maximus_selects_72b and
  test_aerollm_maximus_is_72b.
- MIN_ID stomp fixed: confirmed by test_loader_min_id_is_not_72b and
  test_loader_min_id_resolves_to_7b.
- .env AEROLLM_MODEL override path: untouched (verified by reading
  scripts/setup.sh ~line 1140).

## Fix-loop (post-review)

Addressed all three carryovers from REVIEW.md WEAK_PASS. 3 atomic commits.

### CO-2 — stale src/ comments (commit 1085844)

Comment-only edits. No logic changed.

- `src/arail/portal/app.py:6306`: description string updated from
  "max tier ships Llama-3.1-70B-4bit" to "max tier ships
  Qwen2.5-72B-Instruct-4bit, ~40 GB resident, requires 48 GB+".
- `src/arail/router/backends.py:1132`: comment block updated from
  "Llama-3.1-70B-Instruct-4bit" to "Qwen2.5-72B-Instruct-4bit,
  ~40 GB resident, requires 48 GB+; populated by setup.sh capture_tier".

### CO-3 — retire obsolete deferral guard (commit dad8726)

Deleted `test_sprint_did_not_touch_setup_or_catalog_files` from
`tests/test_build_ai_eng_dry_run_works_on_lowram.py`. The guard was a
deferral sentinel for commits 3a/3b of sprint 2026-05-18-ai-eng-v2.1.
Commit 3b (this sprint) has landed; the guard was satisfied-by-completion
and already red on origin/main. Remaining 15 tests in that file: all pass.
Full-suite failure count dropped from 14 → 13 (exactly 1 retired case).

### CO-1 — shell-source guards for setup.sh (commit 4a3325a)

Added 2 tests to `tests/test_aerollm_tier_resolution.py` (now 14 total):

- `test_setup_sh_min_id_loader_leads_with_aerollm_minimalist`: reads
  setup.sh as text; asserts the AEROLLM_MODEL_MIN_ID loader line leads
  with `models.get("aerollm_minimalist", ...)`. A shell-only revert to
  aerollm_maximus-first fails this test before deployment.
- `test_setup_sh_capture_tier_has_aerollm_case_block`: reads setup.sh
  as text; asserts the capture_tier case block has both
  `maximus)→AEROLLM_MODEL_MAX_ID` and `*)→AEROLLM_MODEL_MIN_ID` arms
  via regex. Replacing the case block with a flat assignment re-introduces
  Bug 2 and fails this test.

Both tests pass (confirmed against current setup.sh).

### New full-suite state

- 13 failed / 1924 passed / 1 xfailed (was 14/1922/1 after initial build).
- Failure count decreased by 1 (CO-3 retired). No new failures introduced.
- All 13 remaining failures are pre-existing, unrelated to this sprint
  (docs routes, airgap order-sensitivity, swarm surfaces, metrics hybrid).
