# Sprint: platform-foundation

**ID:** 2026-05-14-platform-foundation
**Started:** 2026-05-15T02:18:18Z
**Product:** arail
**Branch:** qukaizen/arail-platform-foundation (cut from main @ 4923522)

## Task

Platform foundation sprint. User framing: *"This is a platform and OpenAPI
foundation and consistency. I expect /health and /metrics."* Combines two
coupled work items because the Skills→Agents refactor reshapes
`/api/agents` and must conform to whatever API conventions the platform
foundation establishes — splitting them across sprints would let the
second drift from the first.

### Scope

1. **`/api/system/health` tier-gating** — Filter optional services
   (`marimo`, `open-notebook`, `neo4j`, `opencode`) by `min` vs `max`
   tier rather than exposing them to all callers. Origin:
   `sprints/2026-05-04-opencode-in-workbench/SPRINT.md` carryover #1
   (QA INFO #1).
2. **`/api/system/metrics` (new)** — Decide shape (Prometheus text vs
   JSON), choose counters/gauges, define interaction with airgapped
   mode (no remote scraping needed; local-only).
3. **OpenAPI consistency** — Error response shape, status-code
   conventions, naming (snake_case vs camelCase). Audit all `/api/*`
   endpoints; fix the worst drift.
4. **Skills folded into Agents** — Origin:
   `sprints/2026-05-04-opencode-in-workbench/SPRINT.md` "Sprint 2 —
   Skills folded into Agents". The approved plan is in that sprint's
   intake notes; visionary should re-read.

## Phases

| Phase | Subagent | Artifact | Status | Started | Finished | Verdict |
|---|---|---|---|---|---|---|
| think | visionary | VISION.md | done | 2026-05-15T02:18Z | 2026-05-15T02:48Z | proceed (fde72da) |
| plan | architect (design) | ARCHITECTURE.md | done | 2026-05-15T02:48Z | 2026-05-15T02:51Z | proceed (e56db77) |
| build | builder | BUILD_LOG.md | done | 2026-05-15T02:51Z | 2026-05-15T03:24Z | 7 commits, 82/82 tests pass; 1 spec gap surfaced (stream tier-gating) |
| review | architect (review) | REVIEW.md | done | 2026-05-15T03:24Z | 2026-05-15T03:32Z | WEAK_PASS (stream tier-filter accepted with carryover) |
| test | qa | TEST_REPORT.md | done | 2026-05-15T03:32Z | 2026-05-15T03:38Z | PASS (121/121, +39 paranoid; all architect probes clean) |
| ship | — | PR | pending | — | — | — |

## Decisions log

| Date | Decision | Rationale |
|---|---|---|
| 2026-05-14 | Run visionary first | Strategic framing (platform contract, longer-lived than a bug fix). API surface decisions made here will outlive the sprint. |
| 2026-05-14 | Bundle health + metrics + OpenAPI + Skills-into-Agents | Skills→Agents refactor changes `/api/agents` shape; if platform conventions aren't fixed first, the new surface lands inconsistent. Splitting across sprints would let the second drift. |

## Carryovers (deferred to follow-up sprint)

| Item | Estimate | Rationale |
|---|---|---|
| Tier-filter `/api/system/health/stream` events (Marimo/Open Notebook/Neo4j hardcoded checks at app.py:6855-6857) | ~30 min | Architect WEAK_PASS accepted stream deviation as informational diagnostic dump, not platform contract. Structural refactor (per-check list vs services-dict mismatch) was out of scope this sprint. Same info-class as QA INFO #1 in a different shape — needs filtering in the next platform sprint. |

## Skipped phases

| Phase | Reason |
|---|---|

## Notes

- Per `arail/CLAUDE.md` QA allocation: 30% setup / 30% Buddy / 20%
  security / 10% happy / 10% regression. Setup-on-clean-machine matters
  for `/api/system/health` (tier detection) and `/api/system/metrics`
  (file creation, permissions).
- Visionary should NOT design — only set win condition, wedge, and
  rejection criteria. If the visionary thinks the scope is too large,
  they should recommend defer/split and stop the sprint.
- Architect partition expectation: four items, four subsections in
  ARCHITECTURE.md, each independently revertable, BUT shared API
  conventions (error shape, naming) defined once and reused across all four.
- Prior-sprint artifacts the visionary + architect should read:
  - `sprints/2026-05-04-opencode-in-workbench/SPRINT.md` (carryover #1 +
    Sprint 2 intake notes)
  - `sprints/2026-05-04-opencode-in-workbench/REVIEW.md` (QA INFO #1
    rationale)
  - The opencode-in-workbench plan file referenced from that sprint
- Likely affected code surfaces:
  - `src/arail/portal/app.py` — `/api/system/health`, new
    `/api/system/metrics`, `/api/agents/*`
  - `src/arail/portal/services/` — service-registry pattern (tier
    metadata per service)
  - `src/arail/tier.py` or wherever tier is currently read
  - `lab/pkb/agents/` — agent loader contract (Skills folded in)

## How to resume this sprint

```
git checkout qukaizen/arail-platform-foundation
cat sprints/2026-05-14-platform-foundation/SPRINT.md
```

Then continue from the next pending phase row.
