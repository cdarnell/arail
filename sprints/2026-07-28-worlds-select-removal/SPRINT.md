# Sprint: worlds-select-removal

**ID:** 2026-07-28-worlds-select-removal
**Started:** 2026-07-28 (evening)
**Product:** arail
**Branch:** `qukaizen/arail-worlds-select-removal-fac7c2` (off merged main `022a711`)

## Task

Execute the deprecation announced by sprint `2026-07-28-concurrent-worlds`
(merged as PR #151): remove **in-place World switching** from the portal. Per
that sprint's VISION.md §2 (binding ruling): `POST /api/worlds/select` survives
**only** for the two non-destructive degenerate cases — the *first* bind of a
World into a root with no World mounted, and unbind-to-default. Mounting a
different World while one is mounted (the destructive path that
`_sweep_other_worlds` makes an rmtree of the other World's staged KB) is
removed; the UI routes that intent to instances (`./arailctl start --world`).
The nav dropdown finishes its conversion to a roster/viewer; the deprecation
notice comes down.

Operator directive (2026-07-28): "Go for the next release — need to get this on
the road to begin testing."

## Phases

| Phase | Subagent | Artifact | Status | Started | Finished | Verdict |
|---|---|---|---|---|---|---|
| plan | architect (design) | ARCHITECTURE.md | DONE | 2026-07-28 | 2026-07-28 | complete (3 WPs) |
| build | builder | BUILD_LOG.md | DONE | 2026-07-28 | 2026-07-28 | WP1–3 + review-fix pass; 169 passed/0 failed |
| review | architect (review) | REVIEW.md | DONE | 2026-07-28 | 2026-07-28 | PASS after fix loop (BLOCK-1 import-zip guard + 3 ASKs closed) |
| test | qa | TEST_REPORT.md | DONE | 2026-07-28 | 2026-07-28 | WEAK_PASS after fix loop (QA-1 forge door + QA-2/3 impostor exemption closed; QA-4 LOW closed post-verdict by orchestrator, one line + test flip) |
| ship | — | PR | DONE | 2026-07-28 | 2026-07-28 | pushed; PR to main (link in Notes) |

## Decisions log

| Date | Decision | Rationale |
|---|---|---|
| 2026-07-28 | Removal semantics are fixed by `sprints/2026-07-28-concurrent-worlds/VISION.md` §2 — select survives only for first-bind and unbind-to-default; anything else is refused with guidance toward instances. | The prior sprint's operator-ratified ruling; this sprint executes, not re-litigates. |

## Skipped phases

| Phase | Reason |
|---|---|
| think (visionary) | The win condition and ruling were produced by the concurrent-worlds sprint's visionary pass and ratified; this sprint is the planned execution of that deprecation. |

## Notes

- Prior artifacts: `sprints/2026-07-28-concurrent-worlds/{VISION,ARCHITECTURE,REVIEW,TEST_REPORT}.md`.
  ARCHITECTURE §5.3 defines the shipped transitional button matrix; §11 pinned
  "Do not remove POST /api/worlds/select — deprecation executed next" — that
  "next" is now.
- QA gating (arail): tilt regression-heavy — the risk here is breaking the
  surviving first-bind/unbind path and the fresh-lab welcome flow.
