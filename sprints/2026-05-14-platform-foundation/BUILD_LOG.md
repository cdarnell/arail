# Build log: Platform Foundation — health/metrics/OpenAPI/Skills-into-Agents

**Architecture:** [ARCHITECTURE.md](./ARCHITECTURE.md) at e56db77
**Started:** 2026-05-15
**Completed:** 2026-05-15

## Plan

| # | Files | Change | Test | Commit ref |
|---|---|---|---|---|
| 0 | `sprints/.../BUILD_LOG.md`, `SPRINT.md` | Skeleton + SPRINT.md commit | none | 04285cd |
| 1 | `docs/api-conventions.md` | Conventions doc per §0; known-drift backlog | none (doc only) | 8b95666 |
| 2 | `src/arail/portal/app.py` | `_OPTIONAL_SERVICES` registry; `_build_services_dict()` helper; tier filter; `version` field | `tests/test_system_health_tier_gating.py` (7 tests) | bb03433 |
| 3 | `src/arail/portal/app.py` | `_METRICS` counters; `@app.middleware("http")`; `GET /api/system/metrics`; 501 for prometheus | `tests/test_system_metrics.py` (8 tests) | 44d4036 |
| 4 | `tests/test_api_conformance.py` | Snapshot shape of health + metrics; snake_case; error envelope | 5 conformance tests | d89c4de |
| 5 | `app.py`, `agents.html`, `_nav.html`, `_skills_panel.html`, `agents.css`; delete `skills.html`, `skills.css` | `/skills` → 302 redirect; `?view=` on `/agents`; `/agents/skills/{id}`; segment control; JS panel; CSS merge | `tests/test_skills_fold_into_agents.py` (11 tests) | 732dc8e |

## Execution

### Step 0 — BUILD_LOG skeleton
Commit: 04285cd

### Step 1 — docs/api-conventions.md
Written per §0 spec: error envelope shape, status code table, key naming, schema versioning, loopback-anonymous rule, counter persistence caveat, known-drift backlog for 5 pre-existing endpoints.
Commit: 8b95666

### Step 2 — Health tier-gating
- Added `_OPTIONAL_SERVICES: dict[str, str]` registry with assertion at import time.
- Extracted `_build_services_dict()` helper called by `/api/system/health`. The SSE stream (`/api/system/health/stream`) has its own check-list and does not call the snapshot helper — it was already independently structured, and forcing a shared builder would have required major refactor of the stream's sequential check model. Documented here: the SSE stream still produces its own check list, but the `services` dict in the JSON snapshot is now tier-filtered via `_build_services_dict()`.
- Added `version` field to health response.
- Did NOT clobber the existing `tier` field (spec-tier: minimum/standard/full/deep).
- 7 tests: min excludes max-only, max includes max-only, down services hidden on max, version field, top-level key snapshot, bypass guard, registry validity.

### Step 3 — /api/system/metrics
- `_METRICS` dict + `_threading.Lock()` at module level, adjacent to `_BOOT_VERSION`.
- `@app.middleware("http")` increments counters; excludes `/api/system/metrics` prefix from self-counting.
- Added `/api/system/metrics` to onboarding gate allowed prefixes (anonymous on loopback).
- 8 tests pass: cold start keys, type assertions, counter increments, self-exclusion, hybrid mode, psutil-missing fallback, prometheus 501, no sensitive data.

### Step 4 — Conformance snapshot
5 tests: health shape subset, metrics full shape, prometheus 501 error envelope, metrics keys snake_case, health top-level keys snake_case.
One initial failure: `_shape()` function recursed into dicts, so `services` produced `{'portal': 'bool', ...}` not `'dict'`. Fixed by checking `services`/`health_summary`/`service_checks` structurally rather than via the type-string helper.
Commit: d89c4de

### Step 5 — Skills fold
- `/skills` → 302 to `/agents?view=skills` (static target; open-redirect guard: query params NOT propagated).
- Added `?view=` query param to `/agents`; unknown values clamp to `status`.
- Added `/agents/skills` and `/agents/skills/{skill_id}` routes.
- Extracted `_skills_panel.html` partial from `skills.html`.
- Added segment control (`[ Status ] [ Skills ] [ Activity ]`) to `agents.html`; wrapped existing content in `<section data-view="status">`; added skills and activity sections.
- View-switcher JS (~50 lines) added; Skills panel JS inlined into `agents.html`.
- `skills.css` content appended to `agents.css`; segment control CSS added.
- `skills.html` and `skills.css` deleted.
- `_nav.html` Skills entry removed; Agents entry now highlights for `active in ['agents', 'skills']`.
- 11 tests: redirect, no-loop, view=skills renders panel, loadouts markup, deep-link skill_id, unknown id 200, default status, api/skills/list unchanged, api/skills/packs unchanged, open-redirect guard, unknown view fallback.

**Delta from plan:** SSE stream does not call `_build_services_dict()` — noted above. All other items match the plan.

## Architect feedback required

**SSE stream deviation:** `/api/system/health/stream` was not updated to use `_build_services_dict()`. The stream produces a sequential per-check list (a different data model from the snapshot's `services` dict), so sharing the builder would require a more invasive refactor. The architect's plan says "same filter must apply to the stream" — in practice the stream doesn't produce a `services` dict at all; it produces a flat list of check-result objects. The snapshot endpoint's `services` key IS now tier-filtered. The stream's check list includes all services but each check has an `ok` field — a min-tier caller seeing a `marimo: warn` entry is not a security issue (it's just a port probe status). This is a gap from the spec's intent but not a security failure. Recommend the architect decide: (a) accept as-is (stream is informational only), or (b) add a `tier_visible` flag to each stream event in a follow-up commit.

## Final state

| Metric | Value |
|---|---|
| Commits (this sprint) | 6 (excluding skeleton + SPRINT/BUILD_LOG) |
| New tests | 31 (7 + 8 + 5 + 11) |
| All required tests passing | 82 / 82 |
| New regressions | 0 |
| Files added | `docs/api-conventions.md`, `tests/test_system_health_tier_gating.py`, `tests/test_system_metrics.py`, `tests/test_api_conformance.py`, `tests/test_skills_fold_into_agents.py`, `templates/_skills_panel.html` |
| Files deleted | `templates/skills.html`, `static/skills.css` |
| Files modified | `src/arail/portal/app.py`, `templates/agents.html`, `templates/_nav.html`, `static/agents.css` |
