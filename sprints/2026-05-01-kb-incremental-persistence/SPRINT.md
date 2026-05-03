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
| plan | architect (design) | ARCHITECTURE.md | completed | 2026-05-01 | 2026-05-02 | n/a |
| build | builder | BUILD_LOG.md | completed | 2026-05-02 | 2026-05-02 | n/a |
| review | architect (review) | REVIEW.md | completed | 2026-05-02 | 2026-05-02 | PASS |
| test | qa | TEST_REPORT.md | completed | 2026-05-02 | 2026-05-03 | PASS |
| ship | — | PR | in_progress | 2026-05-03 | — | — |

## Decisions log

| Date | Decision | Rationale |
|---|---|---|
| 2026-05-01 | Branched `qukaizen/arail-kb-incremental-persistence` from `qukaizen/arail-prod-readiness` HEAD. | Prod-readiness sprint had uncommitted work; branched at last commit so working-tree files travel but new commits only carry KB-persistence artifacts. |
| 2026-05-01 | QA allocation re-weighted: 40% correctness / 25% setup / 20% security / 15% regression. | Standard arail allocation is UX-focused (Buddy 30%); this sprint is KB infrastructure, so correctness dominates. Documented in sprint task. |
| 2026-05-01 | Visionary recommended **proceed**. Win condition: 10s write→retrieve latency, durable across restart, end-to-end witness scenario, no new long-lived service. | VISION.md commit `4b617f2`. Architect must address visionary's displacement concern (draft/published flag for agent-written pages — in scope here, or follow-up?). |
| 2026-05-01 | Stray `72b222f` commit (prod-readiness BUILD_LOG.md skeleton) landed on this branch during the visionary's run from a parallel sprint session. | Commit only adds a prod-readiness sprint file with no overlap; leaving in place rather than rebasing during an active sprint. Will resolve naturally at merge to main. |
| 2026-05-01 | Polluted commit `0e18790` (SPRINT.md scaffold + 2 SRE files) left as-is. | SRE additions later landed in main via prod-readiness PR #28 merge. Cleanup adds rebase complexity for zero correctness gain — kb-incremental→main merge will treat the SRE files as identical no-ops. |
| 2026-05-02 | Architect (design) verdict: schema widens to `{path, name, vector, mtime, source_kind}`; trigger is explicit `pkb_index.schedule_upsert(path)` shim with `threading.Timer` debouncer (2s); upsert uses LanceDB `merge_insert` with delete+add fallback. Draft/published flag DEFERRED (no producers today; `source_kind` preserves the option). | Wedge stays small. Threading.Timer chosen over wiki.py's asyncio debouncer because write helpers are sync and called from sync portal endpoints / CLI. ARCHITECTURE.md commit `4de4de1`. |
| 2026-05-02 | Pip wiring: Buddy writes `dreams/<date>.md` directly via `target.write_text` at `_builtin_buddy.py:1151` — bypasses helper layer. New helper `pkb.write_buddy_dream` to be added by builder so Buddy's chat-shaped output reaches the index. SRE intentionally deferred (writes JSON `state.json`, not chat-shaped content). | Visionary's disconfirming-evidence test depends on agents producing chat-shaped content; Buddy's dreams qualify, SRE state does not. |
| 2026-05-02 | Builder shipped 8 atomic commits: new `pkb_index.py` module (454 lines), schema widening, write-helper wiring, Buddy integration, portal startup hook, 19 new tests across 3 test files. No spec deviations; added `path.resolve()` for symlink-escape safety beyond spec. | BUILD_LOG.md commit `07ed251`. Pre-existing 5 test failures in chat_ui/drafter/toast_ui/buddy_suggesters predate sprint and are not regressions. |
| 2026-05-02 | Architect review verdict: **PASS**. 10/10 mandatory checks passed; 8/12 design-time failure modes have explicit test coverage; 3 minor non-blocking findings (merge_insert-absent fallback uncovered by test, lock released before merge_insert call, staleness-sweep cap=200 boundary uncovered). | REVIEW.md commit `2b83c11`. QA may close the 3 gaps if cheap; otherwise documented as known-uncovered-but-correct paths. |
| 2026-05-03 | QA verdict: **PASS**. 36 new tests in `tests/test_pkb_index_qa.py` (1414 lines); 12/12 design-time failure modes now covered (was 8/12); all 4 win-condition thresholds met (10s round-trip, restart durability, end-to-end witness, no new service); 0 bugs found; 0 regressions; airgapped strict mode verified by patching `socket.socket` to refuse INET. | TEST_REPORT.md commit `8440b2e`. Architect's Finding #2 (lock-release timing) intentionally not converted to test — flagged as optional doc-fix or lock-widen follow-up. 3 optional follow-ups recorded: (1) Finding #2 doc/code drift, (2) decorator promotion if 7th write helper appears, (3) separate sprint for 5 pre-existing test failures in chat_ui/drafter/toast_ui/buddy_suggesters. |

## Skipped phases

| Phase | Reason |
|---|---|
| (none yet) | |

## Notes

- Existing LanceDB on disk: `lab/pkb/.cache/lancedb/pkb_pages.lance/` (verified, 44KB data file, transactions + version manifest present).
- Wiki LanceDB also present: `lab/pkb/.wiki-cache/lancedb/wiki_nodes.lance/`. This sprint focuses on `pkb_pages` (the chat-RAG index). Wiki nodes are out of scope unless they share the same write path.
- Researcher already calls write helpers ([src/arail/agents/researcher.py:735](../../src/arail/agents/researcher.py#L735)). Pip and SRE write paths to be inspected by architect.
