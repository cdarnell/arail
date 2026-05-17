# Sprint: docs-hub-sprint-2

**ID:** 2026-05-16-docs-hub-sprint-2
**Started:** 2026-05-16
**Product:** arail
**Reference plan:** /Users/netsushi/.claude/plans/huge-miss-the-docs-elegant-gem.md (approved)
**Predecessor:** [../2026-05-16-docs-hub-sprint-1/SPRINT.md](../2026-05-16-docs-hub-sprint-1/SPRINT.md) (PASS review; QA in progress)
**Target branch:** qukaizen/arail-docs-hub-sprint-2-bundle

## Task

Sprint 2 of the Docs Hub effort. Wires the Sprint-1 `docs_registry`
into the user-visible portal surface. Scope is **Phase B + Phase C** of
the approved plan, plus two carry-overs the architect surfaced during
Sprint 1 review:

- **Hub landing** (`/docs`): new `docs_hub.html` rendered from
  `docs_registry.by_category()` — hero, featured strip (Agents-explained,
  Buddy, API conventions), category sections, client-side search filter.
  Replaces the `RedirectResponse(/docs/INDEX.md)` redirect at
  `app.py:1812-1814`.
- **Viewer overhaul** (`/docs/{path}`): new `doc_viewer.html` with
  left rail (siblings in category), right TOC (H2/H3), footer strip
  (prev/next + related + "Ask Buddy about this" CTA stub).
- **Tier awareness at the render boundary** (Sprint 1 carry-over): the
  registry currently returns every doc to every caller. The Hub and
  viewer should filter by audience vs `LAB_TIER` so that `architect`-
  audience docs are hidden on `min` unless the user upgrades. Implement
  as a thin filter at the route boundary — not inside the registry —
  so the registry remains the unfiltered source of truth.
- **Slug-collision aftermath** (Sprint 1 carry-over): `docs/design.md`
  is currently denylisted in the registry to avoid colliding with the
  root `design.md`. Sprint 2 either (a) renames `docs/design.md` to
  something content-descriptive (e.g. `docs/portal-design.md`) and
  removes it from the denylist, or (b) deletes it if the content is
  obsolete. Architect's call: **rename**, do not delete — content
  audit is Sprint 3.

**Out of scope** (Sprint 3):
- LanceDB ingest of `docs/` into the wiki index.
- `/api/pkb/search` unification (docs + pkb scopes).
- Full cross-link audit / orphan-doc fix.
- Deletion of `docs/INDEX.md` (kept for one release as a fallback;
  Sprint 3 deletes once the Hub has shipped and stuck).
- Real Buddy chat seeding via `?seed=` (Sprint 2 stubs the CTA as a
  link that opens chat with the prompt query param; chat consumes it
  next sprint).

## Phases

| Phase | Subagent | Artifact | Status | Started | Finished | Verdict |
|---|---|---|---|---|---|---|
| think | visionary | VISION.md | **skipped** | — | — | scope inherits from approved plan |
| plan | architect (design) | ARCHITECTURE.md | done | 2026-05-16 | 2026-05-16 | proceed |
| build | builder | BUILD_LOG.md | done | 2026-05-16 | 2026-05-16 | done |
| review | architect (review) | REVIEW.md | done | 2026-05-16 | 2026-05-16 | PASS |
| test | qa | TEST_REPORT.md | done | 2026-05-16 | 2026-05-16 | WEAK_PASS |
| ship | — | PR | in-progress | 2026-05-16 | — | bundling with sprint-1 carry-overs |

## Decisions log

| Date | Decision | Rationale |
|---|---|---|
| 2026-05-16 | Skip visionary | Approved master plan covers Phase B+C goals verbatim; this is execution of a pre-agreed slice. |
| 2026-05-16 | Tier filter at route boundary, not in registry | Registry stays a pure catalog; UI policy stays in the UI layer. Easier to test, easier to change tier rules later. |
| 2026-05-16 | Rename `docs/design.md` rather than delete | Content may still be referenced by external bookmarks; rename is reversible, deletion is not. |
| 2026-05-16 | Keep `docs/INDEX.md` for one release | Reduces blast radius if the Hub regresses; Sprint 3 deletes it after the Hub is proven. |
| 2026-05-16 | "Ask Buddy" CTA is a stub in Sprint 2 | The chat-side seeding logic is a separate change; ship the link, wire it next sprint. |

## Skipped phases

| Phase | Reason |
|---|---|
| think (visionary) | Plan-driven sprint; win condition is in the master plan + Sprint 1 ARCHITECTURE.md §2 (out-of-scope list naming these deliverables). |

## ARAIL gating (per arail/CLAUDE.md)

- **QA allocation for this sprint:** 10% setup / 20% Buddy / 15%
  security / 35% happy (the Hub *is* the happy path now) / 20%
  regression. Justification: Phase B+C are visible UI; happy and
  regression dominate. Buddy slice covers the CTA stub voice and the
  `buddy_prompt` rendering.
- **Paranoid review checklist watches:**
  - The viewer must not regress markdown rendering for any existing
    doc that worked in Sprint 1.
  - Path traversal at `/docs/{path}` route already mitigated; reuse
    that guard — do not weaken it.
  - The Hub must not crash when the registry is empty (Sprint 1 F13
    failure mode).
  - Tier filter must not leak `architect`-audience docs into a min-
    tier user's Hub.
  - Large doc render perf (REPOSITORY_LAYOUT.md, ROADMAP.md) must
    not regress — TOC extraction adds work to the render path.

## Scope ceiling

Hard ceiling. Builder must stop and escalate before exceeding any:

- **LOC budget:** ~700 lines added net (templates + python + tests).
  - `docs_hub.html`: ~180 lines (template + scoped CSS).
  - `doc_viewer.html` rewrite: ~250 lines (template + CSS; net add
    ~170 over current 82 lines).
  - `app.py` changes: ~80 lines (new hub handler, registry import,
    tier filter helper, TOC extraction, viewer context expansion).
  - `tests/test_docs_routes.py` (NEW): ~250 lines.
- **Files touched:**
  - NEW: `src/arail/portal/templates/docs_hub.html`
  - NEW: `tests/test_docs_routes.py`
  - MODIFIED: `src/arail/portal/templates/doc_viewer.html`
  - MODIFIED: `src/arail/portal/app.py` (hub handler + viewer context)
  - RENAMED: `docs/design.md` → `docs/portal-design.md` and remove
    `design.md` from `_DOCS_DENYLIST` in `docs_registry.py`
  - MODIFIED: frontmatter on the renamed file (add proper `title`,
    `category`, `audience`)
- **No changes** to: `docs_registry.py` public API (additions only if
  strictly required — e.g. a `featured()` helper is allowed if it stays
  side-effect-free); `wiki.py`; `pkb.py`; `_nav.html`.

## Pre-sprint state

- Branch at start: `qukaizen/arail-docs-hub-sprint-2-bundle` (already
  checked out per task).
- Untracked / WIP: `tests/test_system_health_stream_tier_filter.py`
  and modifications under `lab/pkb/compiled/docs/guides/` from prior
  work. **Builder must NOT include these in this sprint's PR** —
  start clean from current branch HEAD; reset/stash any unrelated WIP
  before the first commit.

## Notes
