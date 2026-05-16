# Build log: docs-hub-sprint-2

**Architecture:** [ARCHITECTURE.md](./ARCHITECTURE.md) at 9e61dfe
**Started:** 2026-05-16

## Plan

| # | Files | Change | Test | Commit ref |
|---|---|---|---|---|
| 1 | `docs/design.md` → `docs/portal-design.md`, `docs_registry.py`, `app.py` | Rename + denylist removal + 301 redirect (F11 atomic commit) | `test_no_slug_collision_after_rename`, `test_legacy_design_redirect` | — |
| 2 | `app.py`, `templates/docs_hub.html` (NEW) | Hub handler replaces redirect; `_filter_by_tier`, `_featured_docs`, `_recently_updated` helpers | tests 1–8 in §6.1 | — |
| 3 | `app.py`, `templates/doc_viewer.html` (rewrite) | TOC extractor + 3-column viewer; widen `serve_local_doc` handler | tests 9–17, 20–21 in §6.1 | — |
| 4 | `sprints/2026-05-16-docs-hub-sprint-2/BUILD_LOG.md` | Final pass: full suite, this log update | all 21 + regression | — |

## Execution

### Step 0 — BUILD_LOG.md skeleton
Commit: (this file)

## Surfaced gaps
<none>

## Final state
<pending>
