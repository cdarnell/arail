# Sprint: arail2-tier1-integration

**ID:** 2026-08-08-arail2-tier1-integration
**Started:** 2026-08-08T18:56:52Z
**Product:** arail
**Branch:** `qukaizen/arail-2-declarative-persistence-819030`

## Task

Make the ARAIL 2.0 persistence layer load-bearing. Two changes plus a cutover:
replace the 128-dim SHA1 `hash_embedding` with the spec-declared
nomic-embed-text provider (`arail.dbspec.embed`) at the PKB ingest path
(INTEGRATION.md Tier 1.2); thread `world_id` through `pkb.search` /
`search_for_agents` so retrieval is scoped by a WHERE clause instead of by
`rm -rf` of other worlds' files (Tier 1.1); then point the running lab at the
2.0 store. Until one of these lands, the persistence layer is a rehearsal —
nothing in the running lab reads it.

## Predecessor sprint

`sprints/2026-08-08-arail2-declarative-persistence/` — the layer itself:
PHASE1_AUDIT.md (the evidence), INTEGRATION.md (Tier 1.1 / 1.2 rationale),
SPRINT.md (what shipped, known debt). 107 tests, verified end-to-end on real
data. Nothing in `pkb.py`, `vector_index.py`, `world_mount.py`, or
`scripts/start.sh` has been modified yet.

## Phases

| Phase | Subagent | Artifact | Status | Started | Finished | Verdict |
|---|---|---|---|---|---|---|
| think | visionary | VISION.md | in_progress | 2026-08-08T18:56:52Z | — | — |
| plan | architect (design) | ARCHITECTURE.md | pending | — | — | — |
| build | builder | BUILD_LOG.md | pending | — | — | — |
| review | architect (review) | REVIEW.md | pending | — | — | — |
| test | qa | TEST_REPORT.md | pending | — | — | — |
| ship | — | PR | pending | — | — | — |

## Decisions log

| Date | Decision | Rationale |
|---|---|---|
| 2026-08-08 | Start at `think`, not `plan` | The orchestrator's own evidence for Tier 1.2 is thin: prefixed nomic widened the relevant/irrelevant margin only +0.053, and the scoped-query demo was ambiguous. The contamination severity was also overstated twice and corrected (7% of rows, not "stuffed"). A visionary pass that demands disconfirming evidence is warranted before touching the agent-facing search path. |
| 2026-08-08 | Cutover is in scope, but sequenced last | Embeddings and scoping are only useful together; cutover before them gains nothing. The predecessor migration wrote to a temp dir, so the live lab is untouched and cutover remains an unmade decision. |

## Skipped phases

| Phase | Reason |
|---|---|

## Product gating (arail)

Per `CLAUDE.md`: setup-on-clean-machine, Buddy quality, security (it runs on
other people's machines), onboarding clarity, failure-mode grace. QA
allocation shifts to 30% setup / 30% Buddy / 20% security / 10% happy /
10% regression.

Specific to this sprint:
- Ollama + `nomic-embed-text` becomes a hard requirement of PKB ingest. The
  clean-machine path must either pull it during setup or degrade with an
  actionable message — never silently write hash vectors.
- `LAB_MODE=airgapped` must still hold: the embedding provider is local-only.

## Notes

Baseline for regression comparison: 28 pre-existing failures over the 21
suspect test files at commit `8cb5760` (see predecessor SPRINT.md). Any new
failure against that baseline is a regression introduced by this sprint.
