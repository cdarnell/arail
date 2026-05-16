# Sprint: docs-hub-sprint-1

**ID:** 2026-05-16-docs-hub-sprint-1
**Started:** 2026-05-16
**Product:** arail
**Reference plan:** /Users/netsushi/.claude/plans/huge-miss-the-docs-elegant-gem.md (approved by user)
**Target branch:** qukaizen/arail-docs-hub-sprint-1

## Task

Sprint 1 of the Docs Hub + Knowledge Base unification effort. Scope is **Phase F + Phase A** of the approved plan:

- **Phase F (regression fix + Knowledge cross-link):** Restore the `Docs` link in [src/arail/portal/templates/_nav.html](../../src/arail/portal/templates/_nav.html) that was accidentally trimmed in commit `732dc8e` (skills refactor). Promote `'docs'` from max-only to **min tier** in `tier_surfaces` (~[app.py:100](../../src/arail/portal/app.py#L100)) so learners on the minimal tier — the audience that needs docs most — can see them. **Also add a prominent `📖 Official Docs` card or banner inside the Knowledge tab** ([src/arail/portal/templates/knowledge.html](../../src/arail/portal/templates/knowledge.html)) linking to `/docs` — Knowledge and Docs are siblings in the lab's "learning" surface and the Knowledge tab today gives zero signal that `/docs` exists. (Scope added 2026-05-16 mid-sprint after user said "another miss — Docs has to be referenced easily from the Knowledge tab.")
- **Phase A (frontmatter + registry foundation):** Add YAML frontmatter to every user-facing doc in `docs/` (24 files in scope; exclude 5 internal). Build a new `src/arail/portal/docs_registry.py` module (~120 lines) that parses frontmatter and exposes `all_docs()`, `by_category()`, `get(slug)`, `siblings(slug)`, `related(slug)`. Tests in `tests/test_docs_registry.py`.

**Why this slice:** Ships the regression fix in <1 day, unblocks Sprint 2 (Hub landing + viewer overhaul), and produces no visible UI churn beyond the restored nav link. Low risk, high signal.

**Out of scope** (deferred to Sprint 2/3): `docs_hub.html` landing template, `doc_viewer.html` sidebar/TOC rewrite, "Ask Buddy about this" CTA, LanceDB ingest of `docs/`, cross-link audit, deletion of `docs/INDEX.md`.

## Phases

| Phase | Subagent | Artifact | Status | Finished | Verdict |
|---|---|---|---|---|---|
| think | visionary | VISION.md | **skipped** | — | see decisions log |
| plan | architect (design) | ARCHITECTURE.md | done | 2026-05-16 | — |
| build | builder | BUILD_LOG.md | done | 2026-05-16 | 36/36 tests pass |
| review | architect (review) | REVIEW.md | done | 2026-05-16 | **PASS** (after BLOCK → git hygiene fix → re-review) |
| test | qa | TEST_REPORT.md | done | 2026-05-16 | **PASS** (20 new edge-case tests, no CRITICAL findings) |
| ship | — | PR #56 | done | 2026-05-16 | merged to main as part of "Close health-stream-tier-filter sprint + docs-hub-sprint-1 scaffold" |

## Decisions log

| Date | Decision | Rationale |
|---|---|---|
| 2026-05-16 | Skip visionary phase | The user's approved plan file at `~/.claude/plans/huge-miss-the-docs-elegant-gem.md` already contains a full Context + Goals section equivalent to a VISION.md. User explicitly framed "learning AI is what this lab is all about" and approved the win-condition framing inline. Per the /sprint skill's "Skipping phases" guidance, a bug-fix-plus-foundation sprint with an obvious win condition can skip visionary. |
| 2026-05-16 | Sprint 1 scope = Phase F + Phase A only | The approved plan splits into 3 sprints. Sprint 1 ships regression fix + frontmatter foundation. Sprint 2 ships the visible Hub + viewer. Sprint 3 ships the Knowledge Base unification. This phasing was approved by the user via AskUserQuestion. |
| 2026-05-16 | Default audience for missing frontmatter | When a doc lacks an explicit `audience`, treat as `beginner` (the lab is learning-first). Architect to confirm. |

## Skipped phases

| Phase | Reason |
|---|---|
| think (visionary) | Approved plan file serves as VISION.md — user explicitly approved win-condition framing inline; this is regression+foundation, not a strategic question. |

## ARAIL gating (per arail/CLAUDE.md)

- **QA allocation:** 30% setup / 30% Buddy / 20% security / 10% happy / 10% regression. QA pass should especially watch:
  - (a) The nav regression doesn't reappear — add a test that the Docs link renders on min tier.
  - (b) Frontmatter parsing is robust to malformed YAML — a broken doc must not crash the portal.
  - (c) The registry cannot be made to leak file contents past the docs directory (path traversal).
- **Setup-on-clean-machine:** Adding `python-frontmatter` to `pyproject.toml` must not break `./arailctl setup` on a clean clone. Builder to verify.
- **Buddy quality:** No Buddy code changes in this sprint — but `buddy_prompt` strings in frontmatter must be in Buddy's voice (per `project_buddy_identity` memory: not "Pip").

## Pre-sprint state

- Branch at start: `qukaizen/arail-warmup-overlay`
- Untracked / WIP: `M lab/pkb/compiled/docs/guides/README.md`, `?? docs/decks/`
- These WIP changes must not be folded into this sprint's PR. Builder should branch off `main` (or off a clean point) and ensure `docs/decks/` and the modified compiled-docs README are excluded.

## Notes
