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
| think | visionary | VISION.md | done | 2026-08-08T18:56:52Z | 2026-08-08T19:03Z | **proceed (narrowed)** |
| plan | architect (design) | ARCHITECTURE.md | done | 2026-08-08T19:06Z | 2026-08-08T19:13Z | complete (W0–W10) |
| build | builder | BUILD_LOG.md | in_progress (W0–W5 only) | 2026-08-08T19:15Z | — | — |
| review | architect (review) | REVIEW.md | pending | — | — | — |
| test | qa | TEST_REPORT.md | pending | — | — | — |
| ship | — | PR | pending | — | — | — |

## Decisions log

| Date | Decision | Rationale |
|---|---|---|
| 2026-08-08 | Start at `think`, not `plan` | The orchestrator's own evidence for Tier 1.2 is thin: prefixed nomic widened the relevant/irrelevant margin only +0.053, and the scoped-query demo was ambiguous. The contamination severity was also overstated twice and corrected (7% of rows, not "stuffed"). A visionary pass that demands disconfirming evidence is warranted before touching the agent-facing search path. |
| 2026-08-08 | Cutover is in scope, but sequenced last | Embeddings and scoping are only useful together; cutover before them gains nothing. The predecessor migration wrote to a temp dir, so the live lab is untouched and cutover remains an unmade decision. |
| 2026-08-08 | **Visionary narrows scope: Tier 1.2 as a measurement; Tier 1.1 deferred; cutover rejected.** | Verified by the orchestrator: `pkb._vector_db_path()` (pkb.py:414) derives the LanceDB path from the env-frozen per-instance PKB root, so in 1.x a running World already cannot see another World's rows — five physically separate `pkb_pages.lance` datasets. Tier 1.1 is therefore the *precondition of consolidation*, not value delivered by it. The orchestrator's "same file from four worlds" demo was **circular**: it ran against the consolidated store the migration had just created, demonstrating a problem the migration introduced rather than one that exists in 1.x. |
| 2026-08-08 | **Operator accepted the narrowing.** Sprint scope is now: measure nomic vs `hash_embedding` against a committed labelled fixture with the >=15pp recall@5 kill criterion. Tier 1.1 deferred, cutover dropped. A25/A26 explicitly NOT in scope this sprint (offered, not taken). | Answers the open question with data instead of assumption, and does not spend the install-burden of a hard Ollama dependency on an unmeasured improvement. |
| 2026-08-08 | Architect raised the fixture floor to >=30 queries and added a paired-bootstrap 95% CI on the delta | 15pp over 20 queries is 3 queries — a coin flip wearing a percentage sign. Floor raised to >=6 per world x 5 stores. A point estimate clearing 15pp with a CI crossing zero yields `PASS_INCONCLUSIVE`, which publishes and stops for operator sign-off rather than auto-integrating. |
| 2026-08-08 | Build is scoped to W0–W5 (through the measurement), not the full W0–W10 | W5 is the gate. Whether the conditional integration (W6–W10) happens depends on a number that does not exist yet. The builder publishes the number and stops; the orchestrator re-gates. |
| 2026-08-08 | The `+0.053` number measured the wrong thing | It compared nomic-with-prefixes vs nomic-without. The decision actually on the table — nomic vs `hash_embedding` — has never been measured. Hence Tier 1.2 ships as an A/B with a kill criterion, not as an assumed improvement. |

## Skipped phases

| Phase | Reason |
|---|---|
| — | none skipped; scope narrowed rather than phases dropped |

## Visionary verdict (2026-08-08)

**proceed**, narrowed to roughly one third of the original proposal:

- **Tier 1.2 — proceed, as a measurement.** Build a committed labelled fixture
  (>=20 questions, >=4 per world, hand-labelled against the live 716-row
  corpus) and an A/B harness. nomic must beat `hash_embedding` by **>=15pp
  pooled recall@5** with zero rank-1 losses on an exact-token fixture. Below
  the bar we do not ship the dependency, and we file an ADR recording hash
  embeddings as a *measured* choice.
- **Tier 1.1 — defer.** No query path exists to leak through today.
- **Cutover — reject.** Consolidating five isolated stores into one buys
  cross-world queryability this operator does not want (he runs Worlds one at
  a time) and pays for it by demoting isolation from a directory boundary to
  a WHERE clause that audit finding A31 says no production caller has ever
  passed.
- **Separately:** the surviving real defect is A25/A26 —
  `unmount(remove_staged=False)` as the default on the root-lab mount path.
  It is a stop-and-switch bug, it is cheap, and it needs no database.

### Concerns the architect must address at design time

1. **The fail-loud guarantee dies in the plumbing.** `embed.py` never
   substitutes an embedding — but `pkb_index.py` has **15** `_log.warning`
   swallow points, including three around `index_all`
   (`pkb_index.py:178, 326, 347, 403`). An embedding outage would surface as a
   silently empty index, which is worse than the old behaviour.
2. **Re-embedding must be explicit and resumable.** The 128 -> 768 change hits
   the drop-and-rebuild path (`pkb_index.py:329-347`), and `_semantic_search`
   (`pkb.py:579-583`) calls `index_all` lazily when the table is empty — so a
   user typing in the search box would trigger hundreds of synchronous Ollama
   round trips.

Orchestrator verified claims 1 and 2 and the per-instance isolation finding
directly against the source before accepting the verdict.

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
