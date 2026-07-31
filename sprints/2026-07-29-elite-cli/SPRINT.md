# Sprint: elite-cli

**ID:** 2026-07-29-elite-cli
**Started:** 2026-07-29 22:14 EDT
**Product:** arail

## Task

Make `./arailctl` an elite operator CLI, per `sprints/PROMPT-elite-cli.md`
(the frozen input for this sprint — mission, verified baseline, 10 gaps,
constraints). Headlines: a new `install` verb with an
install/update/upgrade consolidation ruling; non-interactive root-lab
start (`--root`); a scoped, registry-aware `restart`; a unified/honest
`status` with complete `--json` and a documented exit-code contract; a
readiness gate for the root-lab start path (ported from the instance
path's token/checkout probe); opt-in model warm-up; and the polish list.
The 2026-07-29 live review verified the existing baseline green — protect
it with regression tests, do not redesign it.

## Phases

| Phase | Subagent | Artifact | Status | Started | Finished | Verdict |
|---|---|---|---|---|---|---|
| think | visionary | VISION.md | skipped | — | — | — |
| plan | architect (design) | ARCHITECTURE.md | done | 2026-07-29 22:14 | 2026-07-29 22:34 | complete (42e87f4) |
| build | builder | BUILD_LOG.md | done | 2026-07-29 22:40 | 2026-07-30 03:45 | complete — WP1–WP8 in 8 atomic commits + 2 fixups (fa93992…1627c24) |
| review | architect (review) | REVIEW.md | done | 2026-07-30 04:00 | 2026-07-30 06:40 | BLOCK (70bed95) → fix pass → re-review WEAK_PASS (b69ad71); 2 trivial closes dispatched (backlog filing + F4 driver reorder), 4 follow-ups filed, none ship-blocking |
| test | qa | TEST_REPORT.md | done | 2026-07-30 06:00 | 2026-07-30 11:20 | WEAK_PASS (cc7de32) — 2 Medium (Q3 stop-parser scope escalation, Q4 F3 unimplemented), 6 Low, 1 test-gate; 45 tests added |
| ship | — | PR | done | 2026-07-30 11:30 | 2026-07-30 11:30 | PR #156 → main (https://github.com/cdarnell/qukaizen-arail/pull/156) |

## Decisions log

| Date | Decision | Rationale |
|---|---|---|
| 2026-07-29 | Start at plan, skip think | Win condition is explicit and operator-authored: PROMPT-elite-cli.md was written from a live review the operator requested, and the operator added the `install` verb requirement directly. A visionary pass would restate that file. |
| 2026-07-29 | Verb consolidation (architect ruling 1) | `setup`=provision, `install`=refresh (new; `update` aliases to it), `tier`=feature-set (canonical; `upgrade` aliases to it). Aliases permanent — ARAIL is a forked blueprint. |
| 2026-07-29 | Exit codes additive only | 0/1/2 keep today's meanings; new 3 (degraded) and 4 (nothing running). Renumbering would break the protected baseline. |
| 2026-07-29 | Build in chunks, review once | 8 WPs exceed one builder context. Builder invoked in chunks (WP1–2, WP3–5, WP6–8), each WP an atomic commit; single architect review after all land. |

## Build loop (review-fix passes)

| Pass | Trigger | Commits | Status |
|---|---|---|---|
| 1 | REVIEW.md BLOCK (B1–B3, m1–m10, dropped gates T30–T32/T35/F4) | 13461d7, 3d57749, 08dacac, 75b63aa, ca9c8aa, 189439b, a362aad | fixed; re-review WEAK_PASS (b69ad71) — each fix verified by reverting it and watching the matching test fail |
| 2 | Re-review's 2 closes (file required action #9; un-dormant m7's F4 cases) | 47e3dff | done — reviewer pre-declared this a clean PASS, no further review cycle |
| 3 | TEST_REPORT.md WEAK_PASS (Q1–Q7) | fae9769, d1a8b30, 233c05e, e465535, ae6544f, 6bb03f4, c6937c6 | all 7 fixed; every strict-xfail pin flipped to a passing test (zero XPASS); B2's 2nd residual filed to BACKLOG |

## Skipped phases

| Phase | Reason |
|---|---|
| think | PROMPT-elite-cli.md already is the vision: mission, win conditions, gaps, constraints, deliverable — operator-reviewed. |

## Notes

- Frozen input: `sprints/PROMPT-elite-cli.md`. The architect reads it
  directly (artifact handoff, no paraphrase).
- Live-review evidence (2026-07-29): fresh worktree `.venv` build → full
  8-stage `start --world ai` boot on :8090 → token/checkout probe match →
  attach-on-running → `status`/`--probe`/`--json` correct → clean
  `stop --world ai` → registry pruned. All green.
- arail ship gates apply (repo CLAUDE.md): setup-on-clean-machine,
  security (runs on others' machines), failure-mode grace. QA allocation
  30% setup / 30% Buddy / 20% security / 10% happy / 10% regression —
  Buddy share reallocated toward setup/regression for this CLI-only
  sprint (no Buddy surface touched); record in TEST_REPORT.md.
