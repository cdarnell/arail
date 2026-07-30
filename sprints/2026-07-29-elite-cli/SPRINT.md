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
| build | builder | BUILD_LOG.md | pending | — | — | — |
| review | architect (review) | REVIEW.md | pending | — | — | — |
| test | qa | TEST_REPORT.md | pending | — | — | — |
| ship | — | PR | pending | — | — | — |

## Decisions log

| Date | Decision | Rationale |
|---|---|---|
| 2026-07-29 | Start at plan, skip think | Win condition is explicit and operator-authored: PROMPT-elite-cli.md was written from a live review the operator requested, and the operator added the `install` verb requirement directly. A visionary pass would restate that file. |
| 2026-07-29 | Verb consolidation (architect ruling 1) | `setup`=provision, `install`=refresh (new; `update` aliases to it), `tier`=feature-set (canonical; `upgrade` aliases to it). Aliases permanent — ARAIL is a forked blueprint. |
| 2026-07-29 | Exit codes additive only | 0/1/2 keep today's meanings; new 3 (degraded) and 4 (nothing running). Renumbering would break the protected baseline. |
| 2026-07-29 | Build in chunks, review once | 8 WPs exceed one builder context. Builder invoked in chunks (WP1–2, WP3–5, WP6–8), each WP an atomic commit; single architect review after all land. |

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
