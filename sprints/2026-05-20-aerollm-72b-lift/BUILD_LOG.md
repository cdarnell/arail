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
<what was done; deltas from plan>

Commit: <sha>

### Step 2 — test_aerollm_tier_resolution.py
<what was done; deltas from plan>

Commit: <sha>

## Architect feedback required

None.

## Final state

<numbers: tests passing, coverage delta, lines changed>
