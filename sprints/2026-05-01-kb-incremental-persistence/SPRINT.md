# Sprint: kb-incremental-persistence

**ID:** 2026-05-01-kb-incremental-persistence
**Started:** 2026-05-01
**Product:** arail
**Branch:** qukaizen/arail-kb-incremental-persistence

## Task

Close the Chat ↔ KB loop with durable, incremental LanceDB persistence. Today the
chat surface retrieves from LanceDB (`pkb.search()` at
[src/arail/pkb.py:498](../../src/arail/pkb.py#L498)) but agent write helpers
(`write_agent_research`, `write_agent_experiment`,
`write_agent_experiment_rollup` at
[src/arail/pkb.py:534-556](../../src/arail/pkb.py#L534)) write to disk without
updating the vector index. Agent output is invisible to chat retrieval until a
manual full rebuild. This sprint makes those writes flow into LanceDB
incrementally, persistently, and without introducing any new long-lived service.

## Win condition

1. Agent writes (or any code path writing into pkb) become searchable in chat
   within seconds — no manual rebuild.
2. Index is durable across process restarts. Cold start with an existing,
   schema-compatible index does not re-derive everything.
3. Zero new heavyweight infrastructure (no Kafka, Redis, broker, daemon).
   Embedded LanceDB only; in-process debounce/coalescer allowed.
4. Pip and SRE wired to write helpers if missing.
5. Backwards compatible with cold/missing index path.

## Constraints (non-negotiable)

- Local-first; `LAB_MODE=airgapped` honored. Reuse existing embedder; no
  cloud-only embedder.
- No new long-lived services.
- Internal package name stays `arail`.
- LanceDB path stays `lab/pkb/.cache/lancedb/`.
- MIT license preserved.

## Out of scope

- KB → fine-tune dataset / system-prompt preamble / context-cache "compile".
  Separate sprint.
- UI changes to /knowledge or /chat.
- Wiki rebuild rewrite.

## Phases

| Phase | Subagent | Artifact | Status | Started | Finished | Verdict |
|---|---|---|---|---|---|---|
| think | visionary | VISION.md | completed | 2026-05-01 | 2026-05-01 | proceed |
| plan | architect (design) | ARCHITECTURE.md | in_progress | 2026-05-01 | — | — |
| build | builder | BUILD_LOG.md | pending | — | — | — |
| review | architect (review) | REVIEW.md | pending | — | — | — |
| test | qa | TEST_REPORT.md | pending | — | — | — |
| ship | — | PR | pending | — | — | — |

## Decisions log

| Date | Decision | Rationale |
|---|---|---|
| 2026-05-01 | Branched `qukaizen/arail-kb-incremental-persistence` from `qukaizen/arail-prod-readiness` HEAD. | Prod-readiness sprint had uncommitted work; branched at last commit so working-tree files travel but new commits only carry KB-persistence artifacts. |
| 2026-05-01 | QA allocation re-weighted: 40% correctness / 25% setup / 20% security / 15% regression. | Standard arail allocation is UX-focused (Buddy 30%); this sprint is KB infrastructure, so correctness dominates. Documented in sprint task. |
| 2026-05-01 | Visionary recommended **proceed**. Win condition: 10s write→retrieve latency, durable across restart, end-to-end witness scenario, no new long-lived service. | VISION.md commit `4b617f2`. Architect must address visionary's displacement concern (draft/published flag for agent-written pages — in scope here, or follow-up?). |
| 2026-05-01 | Stray `72b222f` commit (prod-readiness BUILD_LOG.md skeleton) landed on this branch during the visionary's run from a parallel sprint session. | Commit only adds a prod-readiness sprint file with no overlap; leaving in place rather than rebasing during an active sprint. Will resolve naturally at merge to main. |

## Skipped phases

| Phase | Reason |
|---|---|
| (none yet) | |

## Notes

- Existing LanceDB on disk: `lab/pkb/.cache/lancedb/pkb_pages.lance/` (verified, 44KB data file, transactions + version manifest present).
- Wiki LanceDB also present: `lab/pkb/.wiki-cache/lancedb/wiki_nodes.lance/`. This sprint focuses on `pkb_pages` (the chat-RAG index). Wiki nodes are out of scope unless they share the same write path.
- Researcher already calls write helpers ([src/arail/agents/researcher.py:735](../../src/arail/agents/researcher.py#L735)). Pip and SRE write paths to be inspected by architect.
