# Build log: SSE health-stream tier filtering

**Architecture:** [ARCHITECTURE.md](./ARCHITECTURE.md) at 88fb7de
**Started:** 2026-05-15

## Plan

| # | Files | Change | Test | Commit ref |
|---|---|---|---|---|
| 1 | `sprints/2026-05-15-health-stream-tier-filter/BUILD_LOG.md` | Skeleton (this file) | — | pending |
| 2 | `src/arail/portal/app.py` lines ~6847-6866 | Replace `checks = [...]` with `checks_all = [...]` (3-tuple with `service_id`), add `_check_visible()` filter, derive `checks`, recompute `total` | — | pending |
| 3 | `tests/test_system_health_stream_tier_filter.py` | New file: 8 tests covering min/max tier filtering, done.total parity, snapshot alignment, security bypass, registry integrity, latency bound | — | pending |
| 4 | `sprints/2026-05-14-platform-foundation/REVIEW.md` | Append one-line closure note under Required actions | — | pending (same commit as #2 and #3 per ARCHITECTURE.md §"Recommended implementation order") |

Steps 2–4 ship as one atomic commit (per ARCHITECTURE.md §"Recommended implementation order").

## Execution

### Step 1 — BUILD_LOG.md skeleton
Committed this file. Contract with reviewer established.
Commit: pending

### Step 2+3+4 — Tier-filter stream checks + tests + carryover close-out

**app.py change (lines ~6868-6905):** Replaced the flat `checks = [...]` 2-tuple list with
`checks_all` 3-tuple list (display_name, async_fn, service_id|None). Added `_check_visible()`
inline filter and derived `checks` via comprehension. Recomputed `total = len(checks)` after
filter. Change: +21 lines in app.py (within the ≤40-line ceiling).

**Test file:** `tests/test_system_health_stream_tier_filter.py` — 8 tests covering:

1. min-tier hides Marimo / Open Notebook / Neo4j Bolt; always-on checks present
2. max-tier includes all three max-only names
3. done.total == emitted check count (parametrized min + max)
4. stream and snapshot service keysets align on min tier (Notebook also caught as max-only)
5. registry integrity: every tier-gated name maps to a known _OPTIONAL_SERVICES key
6. security: query-param bypass ignored
7. latency: min-tier stream completes < 2 s with mocked ports

**Deviations from plan:** None. Architecture followed exactly. No helper extracted.

**REVIEW.md closure:** One-paragraph note appended to
`sprints/2026-05-14-platform-foundation/REVIEW.md` under "Required actions before merge".

Commit: pending (final commit this step)

## Architect feedback required

None.

## Final state

- 8 new tests — all passing
- 7 pre-existing failures in unrelated test files — confirmed pre-existing (not introduced)
- 7 platform-foundation tier-gating tests — still green
- 1279 other tests — still passing
- app.py lines changed: +21 (ceiling was 40)
- Files touched: `src/arail/portal/app.py`, `tests/test_system_health_stream_tier_filter.py`,
  `sprints/2026-05-15-health-stream-tier-filter/BUILD_LOG.md`,
  `sprints/2026-05-14-platform-foundation/REVIEW.md`
