# Sprint: concurrent-worlds

**ID:** 2026-07-28-concurrent-worlds
**Started:** 2026-07-28 11:21
**Product:** arail
**Branch:** `qukaizen/arailctl-concurrent-worlds-33db65` (worktree)

## Task

Retrofit `./arailctl start` to launch multiple Worlds as genuinely independent,
concurrently-running instances — replacing (or coexisting with, if the visionary
pass concludes both earn their place) the current single-portal
"mount/unmount from a dropdown" model. Today exactly one World is mounted at a
time, live-swapped inside one portal process; the operator wants e.g. the
debt-finance World and the AI/ML World both fully up at once, in separate
places, with disjoint state/data roots, selected via a deliberate
`./arailctl start` flow (picker and/or `--world <slug>`) with visible boot
progress. Full brief with grounding facts: `BRIEF.md` (this dir).

## Phases

| Phase | Subagent | Artifact | Status | Started | Finished | Verdict |
|---|---|---|---|---|---|---|
| think | visionary | VISION.md | DONE | 2026-07-28 11:25 | 2026-07-28 11:30 | proceed |
| plan | architect (design) | ARCHITECTURE.md | pending | — | — | — |
| build | builder | BUILD_LOG.md | pending | — | — | — |
| review | architect (review) | REVIEW.md | pending | — | — | — |
| test | qa | TEST_REPORT.md | pending | — | — | — |
| ship | — | commits on branch | pending | — | — | — |

## Decisions log

| Date | Decision | Rationale |
|---|---|---|
| 2026-07-28 | Operator: run the full sprint autonomously once ARCHITECTURE.md exists; the architect's answers to the open questions (incl. the dropdown's fate) are binding. | Chosen at plan approval over a pause-after-design gate. |
| 2026-07-28 | VISION.md and ARCHITECTURE.md are produced before any code changes. | Operator instruction in the sprint request. |
| 2026-07-28 | Visionary rulings (VISION.md): L2 isolation — per-World `LAB_ROOT` (pkb/data/LanceDB/mount-pointer/secrets) + own ports, shared model weights + Ollama daemon. **Replace the dropdown**, deprecate over one release; `POST /api/worlds/select` survives only for first-bind/unbind-to-default in an empty root. Picker on bare `start` when >1 World; `--world <slug>` direct; already-running → attach, never error. Ceiling 3 concurrent, soft-warn at 4, no auto-eviction, `LAB_MAX_INSTANCES` override. `arailctl status` = one source of liveness truth. | The dropdown mount is destructive (`_sweep_other_worlds` rmtree's other worlds' staged KB) — switching was never non-destructive, so concurrency requires disjoint data roots by construction. Shared backend costs ~300 MB/instance (measured); dedicated 7B per instance would exclude the 16 GB minimalist floor. |

## Skipped phases

| Phase | Reason |
|---|---|
| (none) | |

## Notes

- Approved plan (grounding facts, phase briefs, verification):
  `/Users/netsushi/.claude/plans/design-via-sprint-scalable-alpaca.md`;
  repo-local copy of the operative content in `BRIEF.md`.
- Debt-finance sprint artifacts live on branch
  `qukaizen/modern-finance-world-plan-a34437` under
  `sprints/2026-07-26-world-of-debt-finance/` — read via `git show`.
- QA gating (arail): 30% setup / 30% Buddy / 20% security / 10% happy /
  10% regression, tilted setup+security for this sprint.
