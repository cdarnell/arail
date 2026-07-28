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
| plan | architect (design) | ARCHITECTURE.md | DONE | 2026-07-28 11:32 | 2026-07-28 11:40 | complete (8 WPs) |
| build | builder | BUILD_LOG.md | DONE | 2026-07-28 11:45 | 2026-07-28 14:00 | WP1–8 done; zero regressions vs pre-sprint baseline (47 reds pre-existing, confirmed byte-identical) |
| review | architect (review) | REVIEW.md | DONE | 2026-07-28 14:05 | 2026-07-28 15:35 | WEAK_PASS after fix loop (B1,B2,M1–M7 closed; 3 new minors n1–n3 noted for QA) |
| test | qa | TEST_REPORT.md | DONE | 2026-07-28 15:40 | 2026-07-28 18:10 | WEAK_PASS after fix loop + re-test (live two-World cold boot green end-to-end; isolation, status<2s, legible-launch win conditions MET) |
| ship | — | commits on branch | DONE | 2026-07-28 18:15 | 2026-07-28 18:20 | All commits on `qukaizen/arailctl-concurrent-worlds-33db65`; push/PR awaits operator |

## Decisions log

| Date | Decision | Rationale |
|---|---|---|
| 2026-07-28 | Operator: run the full sprint autonomously once ARCHITECTURE.md exists; the architect's answers to the open questions (incl. the dropdown's fate) are binding. | Chosen at plan approval over a pause-after-design gate. |
| 2026-07-28 | VISION.md and ARCHITECTURE.md are produced before any code changes. | Operator instruction in the sprint request. |
| 2026-07-28 | Visionary rulings (VISION.md): L2 isolation — per-World `LAB_ROOT` (pkb/data/LanceDB/mount-pointer/secrets) + own ports, shared model weights + Ollama daemon. **Replace the dropdown**, deprecate over one release; `POST /api/worlds/select` survives only for first-bind/unbind-to-default in an empty root. Picker on bare `start` when >1 World; `--world <slug>` direct; already-running → attach, never error. Ceiling 3 concurrent, soft-warn at 4, no auto-eviction, `LAB_MAX_INSTANCES` override. `arailctl status` = one source of liveness truth. | The dropdown mount is destructive (`_sweep_other_worlds` rmtree's other worlds' staged KB) — switching was never non-destructive, so concurrency requires disjoint data roots by construction. Shared backend costs ~300 MB/instance (measured); dedicated 7B per instance would exclude the 16 GB minimalist floor. |

| 2026-07-28 | Architect refinements over VISION (ARCHITECTURE.md): instance roots at `lab/instances/<slug>/` (not repo-root `instances/`, blueprint.sh's namespace); registry = one JSON per instance in `lab/instances/registry.d/` (atomic rename, no flock); 4-step liveness predicate incl. per-boot token via new `GET /api/instance`; ports allocate-once-then-pin in 10-wide blocks from 8090 (hard stop <9100); portal **Launch button renders a copyable command, does not spawn** (closes a CSRF-reachable process-execution surface); `select` returns 409 `instance_live` when a live instance serves the slug (new-found data-loss path); per-instance secrets, never auto-copied; both latent fixes (undefined `warn`, `lab.conf` set -a) in scope. | Recorded per the operator's run-full-sprint decision — architect's answers are binding. |

| 2026-07-28 | Post-verdict hardening micro-pass (orchestrator call): QA's WEAK_PASS did not block ship, but QA-18 (a world `display_name` of `${IDE_PASSWORD}` interpolating a real secret into the displayed LAB_NAME) is a secret-exfiltration primitive in new code — closed along with QA-15 (lab.conf passphrase clobber) and QA-17 (unstoppable lab across upgrade) before closing the sprint. QA-16 (LOW, dead write) left for backlog. | Shipping a known secret-exfil path would violate the repo's never-echo-secrets discipline; fixes were bounded (<50 lines each) at QA-prescribed sites with fail-before/pass-after regression tests. |

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
