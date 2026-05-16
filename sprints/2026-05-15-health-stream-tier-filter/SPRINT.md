# Sprint: health-stream-tier-filter

**ID:** 2026-05-15-health-stream-tier-filter
**Started:** 2026-05-15T23:10:00Z
**Product:** arail
**Branch:** qukaizen/arail-health-stream-tier-filter (to be cut from main)

## Task

Tier-filter `/api/system/health/stream` SSE events to match the platform-foundation tier-gating conventions. The endpoint broadcasts Marimo, Open Notebook, and Neo4j availability checks without tier-gating, while the REST endpoint (`/api/system/health`) filters these as max-only services. The stream uses a different code path (per-check event list vs services-dict helper); this sprint aligns the two.

Origin: platform-foundation sprint carryover (accepted as WEAK_PASS; stream treated as informational diagnostic dump, not platform contract, but should filter for consistency).

## Phases

| Phase | Subagent | Artifact | Status | Started | Finished | Verdict |
|---|---|---|---|---|---|---|
| think | visionary | VISION.md | skipped | — | — | — |
| plan | architect (design) | ARCHITECTURE.md | pending | 2026-05-15T23:10Z | — | — |
| build | builder | BUILD_LOG.md | pending | — | — | — |
| review | architect (review) | REVIEW.md | pending | — | — | — |
| test | qa | TEST_REPORT.md | pending | — | — | — |
| ship | — | PR | pending | — | — | — |

## Decisions log

| Date | Decision | Rationale |
|---|---|---|
| 2026-05-15 | Skip visionary phase | Bug fix shape with obvious win condition (tier-filter stream checks). Carryover from platform-foundation sprint with documented scope. |

## Skipped phases

| Phase | Reason |
|---|---|
| think | Bug fix with obvious win condition; documented carryover from platform-foundation sprint. |

## Notes

- Affected code: `src/arail/portal/app.py` lines ~6855-6857 (hardcoded checks in stream handler)
- Comparison: `/api/system/health` uses `_OPTIONAL_SERVICES` registry; stream needs same filtering logic
- QA allocation: 30% setup / 30% Buddy / 20% security / 10% happy / 10% regression (per arail/CLAUDE.md)
- Risk: Low — filtering stream events doesn't affect max-tier visibility, just removes checks from min-tier subscribers
