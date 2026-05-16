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
| plan | architect (design) | ARCHITECTURE.md | done | 2026-05-15T23:10Z | 2026-05-15T23:24Z | proceed |
| build | builder | BUILD_LOG.md | done | 2026-05-16T00:00Z | 2026-05-16T00:00Z | done |
| review | architect (review) | REVIEW.md | done | 2026-05-16T00:00Z | 2026-05-16T00:00Z | PASS |
| test | qa | TEST_REPORT.md | done | 2026-05-16T00:00Z | 2026-05-16T00:00Z | PASS |
| ship | — | direct-to-main | done | 2026-05-16T00:00Z | 2026-05-16T00:00Z | shipped |

## Decisions log

| Date | Decision | Rationale |
|---|---|---|
| 2026-05-15 | Skip visionary phase | Bug fix shape with obvious win condition (tier-filter stream checks). Carryover from platform-foundation sprint with documented scope. |
| 2026-05-15 | Annotate checks_all with service_id + inline filter | Reuses `_OPTIONAL_SERVICES` registry; avoids extracting helper (closures capture locals). Six-line filter using public symbols. |

## Skipped phases

| Phase | Reason |
|---|---|
| think | Bug fix with obvious win condition; documented carryover from platform-foundation sprint. |

## Notes

- Affected code: `src/arail/portal/app.py` lines ~6847-6870 (stream handler)
- Design: Annotate `checks_all` with `service_id` (or None for tier-agnostic); filter during loop
- Max-only services: Marimo, Open Notebook, Neo4j, Opencode
- QA allocation: 30% setup / 30% Buddy / 20% security / 10% happy / 10% regression (per arail/CLAUDE.md)
- Scope ceiling: ≤40 lines changed in app.py, one atomic commit
- Tech debt: `check_opencode` missing entirely (gap predates sprint); `check_ide`, `check_mlx_openai` lack registry entry
