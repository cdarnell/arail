# Architecture: Platform Foundation — health/metrics/OpenAPI/Skills-into-Agents

**Date:** 2026-05-15
**Sprint:** 2026-05-14-platform-foundation
**Branch:** qukaizen/arail-platform-foundation (cut from main @ 4923522)
**Spec:** [VISION.md](./VISION.md) @ fde72da (binding)

## Restatement

This sprint hardens ARAIL's `/api/*` surface as a *platform contract* that
survives forker renames. Four independently revertable changes: (1) tier-gate
`/api/system/health` so min-tier callers no longer see `marimo`/`open-notebook`/
`neo4j`/`opencode` keys; (2) ship a new airgapped-pure JSON `/api/system/metrics`
endpoint with a small documented set of gauges/counters; (3) write
`docs/api-conventions.md` once and *apply it to the new endpoints added in
this sprint only* — pre-existing drift is captured as a backlog; (4) execute
the pre-approved Sprint-3 plan that folds Skills into Agents in the UI while
preserving `/api/skills/*` and `lab/pkb/skills/` code paths. The win condition
is `curl`-observable per VISION.md §"Win condition" — three concrete shapes
the forker can script against without reading `app.py` source.

## Assumptions

- `LAB_TIER` env var is the single canonical tier source (`_current_tier()`
  in `app.py:90`). The `tier` field already on `/api/system/health` is a
  *spec-tier* (`minimum`/`standard`/`full`/`deep`) — different concept, must
  not be conflated or clobbered.
- `psutil` may be absent on minimal installs (existing fallback at
  `app.py:6223`); metrics endpoint must degrade the same way.
- The portal is loopback-bound by default (`BIND_ADDR=127.0.0.1`), so
  anonymous access to `/api/system/metrics` is acceptable as platform
  contract per VISION §"Tensions resolved" #1.
- Counter state is in-process only — restart resets to zero. Persisted
  metrics are an explicit non-goal for v1.
- The existing health-stream consumer (`/api/system/health/stream`,
  `app.py:6538`) shares the same builder shape; whichever way we filter
  must apply uniformly so SSE doesn't drift from the snapshot endpoint.
- Skills-fold plan in `~/.claude/plans/also-want-to-consider-synthetic-wreath.md`
  Sprint 3 is current — the listed line numbers may have shifted since
  authoring; builder uses grep, not absolute line numbers.

## Data flow

```
                ┌───────────── /api/system/health ─────────────┐
caller ──▶ FastAPI ──▶ build_services_dict()
                          │
                          ├─ always-on core (portal, knowledge-canvas)
                          └─ optional registry:
                              [{id, tier, probe_fn}, …]
                              │
                              └─▶ filter: keep if probe_fn() AND
                                          tier in _visible_surfaces()
                          ▼
                       JSON {services:{…tier-filtered…}, version, …}

                ┌───────────── /api/system/metrics ────────────┐
caller ──▶ FastAPI ──▶ build_metrics() ──▶ flat JSON dict
                          │                  {ram_used_bytes, …}
                          ├─ psutil (or fallback)
                          ├─ _METRICS counters/gauges (in-process)
                          ├─ os.getenv("ARAIL_MODE")
                          └─ _CHAT_MODEL_LOAD_STATE

                ┌─────── /skills → /agents?view=skills ────────┐
caller ──▶ /skills ──▶ 302 RedirectResponse
caller ──▶ /agents?view=<v> ──▶ agents.html (bootstrap JSON)
                              └─▶ view-switcher JS toggles [hidden]
caller ──▶ /agents/skills/{id} ──▶ same template, deep-linked
```

## Interface contracts

### Shared (all new endpoints)

- **Promises:** snake_case JSON keys; `Content-Type: application/json`;
  loopback-safe; stable shape across LAB_NAME rebrand.
- **Requires:** GET method; no auth on loopback bind; no request body.
- **On bad input:** 400 with `{"error": "invalid_query", "message": …}`;
  unknown query params ignored (forward-compat).

### `/api/system/health` (modified)

- **Postcondition:** `services` is a dict keyed by service id; each id is
  visible iff (a) the service is up AND (b) the service's declared tier
  is `min` OR matches `_current_tier()`. Always-on `portal` and
  `knowledge-canvas` keep current semantics.
- **New top-level field:** `version` (string, currently
  `arail.__version__` or `"unknown"`).
- **Unchanged:** all existing top-level fields (`platform`, `arch`,
  `ram_*`, `disk_*`, `tier`, `deep_enabled`, `service_checks`,
  `health_summary`, `mode`, `local_inference`).
- **Tier registry:** introduce module-level `_OPTIONAL_SERVICES` mapping
  id → tier (`"min"|"max"`). Source of truth for both the filter and
  any future docs. Tier assignments:
  - `min`: `ttyd`, `lance-memory`, `ollama` (all available on min)
  - `max`: `notebook`, `marimo`, `open-notebook`, `neo4j`, `opencode`
- **Same filter must apply to `/api/system/health/stream`** — extract
  the services-dict builder so both call sites share it.

### `/api/system/metrics` (new)

- **Method/path:** `GET /api/system/metrics` (optionally
  `?format=json` — default; `?format=prometheus` reserved, returns
  `501 {"error":"not_implemented","message":"prometheus format reserved for future"}`).
- **Response shape:** flat JSON, snake_case, Prometheus-translatable
  (label-free gauges/counters at top level):

  ```json
  {
    "process_uptime_seconds": 1234.5,
    "ram_used_bytes": 8589934592,
    "ram_total_bytes": 34359738368,
    "disk_free_bytes": 123456789012,
    "chat_model_loaded": 1,
    "active_provider": "my_machine",
    "lab_mode": "airgapped",
    "lab_tier": "min",
    "active_agents": 3,
    "kb_doc_count": 42,
    "http_requests_total": 187,
    "http_errors_total": 4,
    "last_provider_change_unix": 1715731200,
    "schema_version": 1
  }
  ```

- **Storage:** in-process module-level `_METRICS` dict + lock. Counters
  reset on portal restart (documented in api-conventions). No disk
  persistence in v1.
- **Counter increment:** middleware on FastAPI (`@app.middleware("http")`)
  bumps `http_requests_total` always, `http_errors_total` when
  `response.status_code >= 500`. Excluded routes: `/api/system/metrics`
  itself (would self-pollute) and SSE streams.
- **Auth:** anonymous (loopback only via BIND_ADDR). Per VISION §"Tensions
  resolved" #1: platform contract → anonymous.
- **Fallbacks:** missing psutil → byte fields = 0 (same convention as
  health); missing KB → `kb_doc_count = 0`; never raises.

### Skills-fold routes

- `GET /skills` → 302 `RedirectResponse(url="/agents?view=skills")`.
- `GET /agents?view={status|skills|activity}` → renders `agents.html`;
  unknown `view` falls back to `status` (no 400 — forward-compat).
- `GET /agents/skills` → equivalent to `?view=skills`.
- `GET /agents/skills/{skill_id}` → renders Skills view with
  `default_skill_id` in bootstrap JSON. Unknown id: renders Skills view,
  no editor pre-opened, no 404 (the panel itself shows "skill not
  found" inline — matches existing slide-out failure mode).
- **Preserved:** `/api/skills/*` and `lab/pkb/skills/` untouched.

## Failure modes

### Item 1 — Health tier-gating

| Failure | Detection | Recovery |
|---|---|---|
| `LAB_TIER` unset | `_current_tier()` returns `"min"` (existing default) | Use min-tier filter; no error |
| `LAB_TIER` invalid string | `_current_tier()` clamps to `"min"` (existing) | Same as above |
| Service registry typo (id without tier) | New unit test asserts every id in `_OPTIONAL_SERVICES` has a tier in {min,max} | Builder caught at import time via assert |
| Probe times out | `asyncio.gather` returns False for that port | Service hidden (same as today) |
| Stream and snapshot diverge | Shared builder extracted; one regression test calls both and diffs `services` keys | Single source of truth function |

### Item 2 — Metrics endpoint

| Failure | Detection | Recovery |
|---|---|---|
| psutil missing | Try/except ImportError | Byte fields → 0; emit `schema_version` regardless |
| `_CHAT_MODEL_LOAD_STATE` not initialised | hasattr check | `chat_model_loaded = 0` |
| KB index missing/corrupt | Try/except around count call | `kb_doc_count = 0`, log once |
| Middleware double-counts self-call | Path-prefix exclusion | Skip `/api/system/metrics` in middleware |

### Item 3 — OpenAPI conventions

| Failure | Detection | Recovery |
|---|---|---|
| New endpoint omits `version`/`schema_version` | Snapshot test diff against committed fixture | Builder re-adds field before merge |
| Existing endpoint accidentally "fixed" | Diff review; conventions doc explicitly lists endpoints in-scope | Architect review blocks the commit |
| Convention doc and code disagree | One conformance test parses `docs/api-conventions.md` error shape, calls a deliberately-broken endpoint, asserts match | Update whichever is wrong |

### Item 4 — Skills-fold

| Failure | Detection | Recovery |
|---|---|---|
| Deep-link `/agents/skills/<unknown-id>` | Backend renders skills view; frontend shows "skill not found" | No 404 — matches Vision §1 forker-friendly |
| JS disabled — view-switcher no-op | Initial render uses `default_view` server-side; all sections marked `[hidden]` except matching one in HTML | Server-rendered initial view; JS is enhancement |
| Stale bookmark to `/skills/<id>` | Today's `/skills` had no sub-paths; only `/skills` root needs redirect | Single redirect covers it |
| Redirect loop (`/skills` → `/agents?view=skills` somehow re-redirects) | Integration test follows redirect with `allow_redirects=False`, asserts single 302 | Static `RedirectResponse`, no conditional logic |
| Orphan template references (`active='skills'` in `_nav.html`) | `grep -r "active.*skills\|view.*skills" templates/` during review | Builder cleans before commit |
| `static/skills.css` referenced by other templates after deletion | `grep -r "skills.css" templates/` before delete | Inline into `agents.css` per plan |

## Test strategy

### Item 1 — Health tier-gating (≥3 tests)
- **Unit:** `LAB_TIER=min` → `services` keys ⊆ {`portal`, `knowledge-canvas`, `ttyd`, `lance-memory`, `ollama`} (no `marimo`, `open-notebook`, `neo4j`, `opencode`).
- **Unit:** `LAB_TIER=max` → all-services dict potentially includes max-only ids when running.
- **Regression:** Snapshot of `/api/system/health` JSON keys (top level) — guards against accidental key removal.
- **Integration:** `/api/system/health` and `/api/system/health/stream` first event report the same `services` keyset for both tier values.

### Item 2 — Metrics (≥4 tests)
- **Unit:** Cold-start: `GET /api/system/metrics` returns all documented keys with `http_requests_total == 1` (this request itself excluded) or `0` if middleware excludes it; assert exact contract.
- **Unit:** After N other endpoint hits, `http_requests_total == N`.
- **Unit:** `ARAIL_MODE=hybrid` reflected in `lab_mode` field.
- **Unit:** psutil-missing branch (monkeypatch ImportError) → byte fields == 0, response 200.
- **Negative:** `?format=prometheus` → 501 with conventions-compliant error envelope.

### Item 3 — OpenAPI conformance (≥1 test)
- **Snapshot:** `tests/test_api_conventions.py` calls the three new/touched endpoints (`/api/system/health`, `/api/system/metrics`, one Skills-fold route), asserts: snake_case keys (regex), JSON content-type, `version` or `schema_version` present, error envelope shape on a deliberately-broken request.

### Item 4 — Skills-fold (≥5 tests)
- **Redirect:** `GET /skills` → 302, `Location: /agents?view=skills`.
- **View=skills:** `GET /agents?view=skills` → 200, body contains `data-view="skills"` and the Loadouts markup from `_skills_panel.html`.
- **Deep-link:** `GET /agents/skills/some_id` → 200, bootstrap JSON contains `default_skill_id: "some_id"`.
- **Unknown id:** `GET /agents/skills/__nope__` → 200 (no 404), renders Skills view.
- **Regression:** `GET /agents` (no query) → 200, Status view active (`data-view="status"` not hidden), confirms default unchanged.
- **Regression:** `/api/skills/*` endpoints unchanged (one smoke test per: list, get, install pack).

### Security tests (per QA allocation, 20%)
- **Tier-gating bypass attempt:** `LAB_TIER=min` with crafted `?show_all=true` style params → still filtered.
- **Metrics info disclosure:** assert no provider-token, no file paths beyond `disk_*_bytes` aggregates, no env-var dump.
- **Redirect open-redirect:** `/skills?foo=bar` → 302 to fixed `/agents?view=skills`, query is not propagated as a target.

### Setup tests (per QA allocation, 30%)
- Fresh checkout, `LAB_TIER=min`: `/api/system/metrics` returns 200 within 500ms.
- Same on `LAB_TIER=max` after `arailctl upgrade max`.

## Tech debt

**Added:**
- In-process counters with no persistence (documented as v1 limitation in api-conventions).
- `_OPTIONAL_SERVICES` registry duplicates implicit knowledge currently spread across the health handler; one source of truth is a win, but it's a *new* abstraction the builder must keep in sync if a new service lands.
- Three view sections in `agents.html` increase its size — partial-extract of `_skills_panel.html` mitigates.

**Repaid:**
- `/api/system/health` services dict now has documented tier semantics (was ad-hoc).
- `docs/api-conventions.md` becomes the canonical answer to "what should my new endpoint return?" — replaces tribal knowledge.
- Skills-as-separate-nav vestige removed; mental model and code organisation align.
- Drift backlog list captured (item 3) — debt is *named* even if not paid.

**Net:** Negative (good). The added registries are small and load-bearing in the right direction.

## Recommended implementation order

Each step = one atomic commit. Diffs in `app.py` are partitioned so reverts compose.

1. **`docs/api-conventions.md`** + the `_OPTIONAL_SERVICES` registry + extract shared `_build_services_dict()` (no behavior change yet). One commit. *Foundation only — passes existing tests unchanged.*
2. **Item 1:** Apply tier filter in `_build_services_dict()`. Add `version` field. New tests. One commit.
3. **Item 2:** New `/api/system/metrics` endpoint + middleware + `_METRICS` module + tests. One commit.
4. **Item 3:** Snapshot conformance test against (1)+(2)+(4) outputs; backlog entries in `docs/api-conventions.md`. One commit.
5. **Item 4a:** Extract `_skills_panel.html`; add segment control to `agents.html`; view-switcher JS; agents.css absorbs skills.css. One commit (template-only).
6. **Item 4b:** `app.py` route changes (`/skills` redirect, `?view=` param, `/agents/skills/{id}`); delete `skills.html` + `skills.css`; `_nav.html` collapse; tests. One commit.

Items 1, 2, 3 share `app.py` but in disjoint regions (top-of-file registry vs new endpoint vs new middleware vs new doc file) — reverts compose. Item 4 is touch-isolated to nav/agents/skills templates plus two route handlers.

## Cross-item concerns

- **No order-coupling:** items 2, 3, 4 do not depend on each other functionally. Item 1 should land first because the conventions doc + extracted services builder make item 3's conformance test cleaner. Item 4 is the largest diff — last to minimise rebase pain.
- **Health-stream parity:** the shared `_build_services_dict()` MUST be called by both `/api/system/health` and `/api/system/health/stream`. Builder: do not forget the SSE path.
- **`tier` field collision:** existing `/api/system/health` has a `tier` field that means *spec-tier* (`minimum/standard/full/deep`), NOT `LAB_TIER`. We add `lab_tier` separately if needed (already in metrics); do not rename the existing `tier` field.
- **VISION pushback (none material):** VISION's `disk_free_bytes` and `ram_used_bytes` names map cleanly; only addition is `ram_total_bytes` (Prometheus-style gauges always pair total+used). VISION's `active_provider` is a *label* (string) inside a flat JSON; in Prometheus translation this becomes a label on a constant-1 gauge — call out in api-conventions.
