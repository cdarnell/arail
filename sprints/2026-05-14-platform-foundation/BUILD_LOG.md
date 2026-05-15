# Build log: Platform Foundation — health/metrics/OpenAPI/Skills-into-Agents

**Architecture:** [ARCHITECTURE.md](./ARCHITECTURE.md) at e56db77
**Started:** 2026-05-15

## Plan

| # | Files | Change | Test | Commit ref |
|---|---|---|---|---|
| 1 | `docs/api-conventions.md` | Write conventions doc per §0; known-drift backlog | none (doc only) | pending |
| 2 | `src/arail/portal/app.py` | `_OPTIONAL_SERVICES` registry; `_build_services_dict()` helper; tier filter on `/api/system/health` and `/api/system/health/stream`; `version` field | `tests/test_system_health_tier_gating.py` (3+ tests) | pending |
| 3 | `src/arail/portal/app.py` | `_METRICS` module-level counters; `@app.middleware("http")`; `GET /api/system/metrics` endpoint; `?format=prometheus` → 501 | `tests/test_system_metrics.py` (4+ tests) | pending |
| 4 | `tests/test_api_conformance.py` | Snapshot shape of `/api/system/health`, `/api/system/health/stream` first frame, `/api/system/metrics` | conformance test | pending |
| 5 | `src/arail/portal/app.py`, `templates/agents.html`, `templates/_skills_panel.html`, `templates/skills.html`, `static/agents.css`, `templates/_nav.html` | `/skills` → 302 redirect; `?view=` param on `/agents`; `/agents/skills/{id}` route; extract `_skills_panel.html`; segment control UI; delete `skills.html` | `tests/test_skills_fold_into_agents.py` (5+ tests) | pending |

## Execution

(populated after each commit)

## Architect feedback required

(none yet)

## Final state

(populated after all steps complete)
