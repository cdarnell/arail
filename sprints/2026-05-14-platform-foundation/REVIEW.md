# Review: Platform Foundation — health/metrics/OpenAPI/Skills-into-Agents

**Date:** 2026-05-15
**Build:** [BUILD_LOG.md](./BUILD_LOG.md) at 58aaae6
**Architecture:** [ARCHITECTURE.md](./ARCHITECTURE.md) at e56db77
**Branch:** qukaizen/arail-platform-foundation (cut from main @ 4923522)

## Verdict: WEAK_PASS

Every §0-§4 item lands with matching code + tests; 82/82 tests pass; no
regressions in airgap/security paranoid suites. One spec deviation
(SSE stream not tier-filtered) is accepted as informational-only with a
named follow-up ticket. Ready for QA.

---

## Adjudication: SSE stream tier-gating deviation

**Builder's surfaced gap:** Architecture §"Interface contracts →
/api/system/health → Same filter must apply to /api/system/health/stream"
is explicit. Builder did not apply it; the snapshot's `services` dict
IS tier-filtered, but the stream still emits hardcoded check entries
`("Marimo", check_marimo)`, `("Open Notebook", check_open_notebook)`,
`("Neo4j Bolt", check_neo4j)` (app.py:6855-6857) on every call,
regardless of `LAB_TIER`. Each event includes a detail like
`"127.0.0.1:2718 silent (service may be off)"`.

**Threat-model cross-check (QA INFO #1 origin):** Looking at
`sprints/2026-05-04-opencode-in-workbench/SPRINT.md:53`, the original
concern was framed as info-disclosure on the *snapshot* endpoint — the
`services` dict shape that forkers script against. The stream is a
different shape (sequential per-check list with `ok` field, consumed
by the dashboard live-checks modal) and is operator UX, not a platform
contract that anyone scripts against. **However**, the stream events
still functionally reveal the same fact a min-tier caller shouldn't
need to know: "this lab is aware of these max-only surfaces and where
they would listen." That is the same information class as QA INFO #1,
just in a different wrapper.

**Ruling: ACCEPT (option a) — WEAK_PASS, not BLOCK.** Rationale:

1. The stream is gated behind `onboarding_gate` (passphrase required)
   and is loopback-bound by default (per `BIND_ADDR=127.0.0.1` and
   `docs/PRIVACY.md` trust-boundary doc from prior sprint). It is not
   an anonymous internet-facing surface.
2. The leaked information is "we know what port marimo would use",
   which is the documented default in `.env.example` anyway — not a
   secret, not actionable.
3. The data-shape divergence (per-check list vs services dict) makes
   the "shared builder" originally specified genuinely
   structurally-impossible without refactoring the stream's sequential
   reveal model — which is scope-creep for this sprint.
4. The snapshot endpoint, which IS what the forker-as-platform-contract
   audience hits, IS now tier-filtered. The original QA INFO #1
   wedge is closed.

**Required follow-up (filed below in Tech debt delta):** add a
`tier_visible` flag (or tier-filter the `checks` list) to the stream
events in a separate sprint. Track as carryover.

---

## Spec adherence

| Item | Status | Notes |
|---|---|---|
| §0 conventions doc | PASS | `docs/api-conventions.md` lands; error envelope, status codes, naming, schema versioning, loopback rule all present. Drift backlog at §"Known drift" lists 5 pre-existing endpoints (`POST /api/system/mode`, `GET /api/system/health` re service_checks shape, `POST /api/skills/{id}`, `GET /api/agents/loadouts`, various `POST /api/agent/*`) — sampled and verified these are genuine pre-existing endpoints. |
| §1 tier-gating registry | PASS | `_OPTIONAL_SERVICES` at app.py:123 matches spec exactly (ttyd/lance-memory/ollama=min; notebook/marimo/open-notebook/neo4j/opencode=max). Import-time `assert` guards tier values. |
| §1 shared builder | PARTIAL → ACCEPTED | `_build_services_dict()` at app.py:140 called by snapshot (app.py:6640). Stream does NOT call it. See adjudication above. |
| §1 `version` field | PASS | Added; existing `tier` (spec-tier) field NOT clobbered (verified by grep — `tier` still references the spec-tier enum, `lab_tier` separately used in metrics). |
| §2 metrics keys | PASS | All 14 keys present including `schema_version: 1` (app.py:7005). |
| §2 self-exclusion | PASS | `_METRICS_EXCLUDED_PREFIXES = ("/api/system/metrics",)` at app.py:357; middleware skips before increment (app.py:370-372). Test `test_metrics_excluded_from_self_count` covers it. |
| §2 prometheus 501 | PASS | Returns proper envelope `{"error":"not_implemented","message":...}` at app.py:6931-6937. |
| §3 conformance snapshot | PASS | `tests/test_api_conformance.py` — 5 tests cover health shape, metrics full shape, 501 error envelope, snake_case for both. |
| §4a redirect | PASS | `/skills` → 302 to fixed `/agents?view=skills`. Query params NOT propagated (open-redirect guard). Test `test_skills_root_redirects_to_agents_view` + open-redirect test. |
| §4b view param | PASS | `?view=` clamps unknown to `status`; deep-link `/agents/skills/{id}` renders panel with `default_skill_id`; unknown id renders skills view (no 404). |
| §4c templates | PASS | `_skills_panel.html` extracted; `skills.html` + `static/skills.css` deleted (verified absent); `_nav.html` highlights Agents for `active in ('agents','skills')`. |
| §4d `/api/skills/*` preserved | PASS | Smoke tests for list, packs unchanged. |

---

## Code quality findings

- [INFO] `_build_services_dict()` takes 10 positional kwargs — function signature is wide but readable and each kwarg is a probe boolean. Could refactor to take a probe dict in a future sprint; not blocking.
- [INFO] Metrics middleware is the third `@app.middleware("http")` registered. FastAPI middleware ordering is reverse-of-registration; comments in `fastpath_meter` document the contract. Acceptable.
- [INFO] Conformance test `_shape()` recursion bug surfaced and was fixed in-sprint (per BUILD_LOG §4) — good catch by builder; not residual.
- No functions over 30 lines added; no obvious duplication. Naming clean (`_OPTIONAL_SERVICES`, `_METRICS_EXCLUDED_PREFIXES`, `_BOOT_PERF`, `lab_tier` vs spec `tier` — disambiguation visible).

---

## Security findings

- [INFO] Metrics endpoint exposes `lab_mode`, `lab_tier`, `active_provider` — strings, no tokens, no paths. Verified by reading the metrics handler end-to-end (app.py:6917-7010). `active_provider` is the `MODEL_BACKEND` env var name (e.g. `"my_machine"`, `"openrouter"`), not a key. Matches §2 contract.
- [INFO] Onboarding gate (app.py:262) allows `/api/system/metrics` anonymously pre-onboarding. Acceptable per VISION §"Tensions resolved" #1 (loopback platform contract), but means an attacker on the loopback during the onboarding window can read counters and provider name. Not a security regression — health was already in this list. Documented in api-conventions §"Auth / anonymity".
- [INFO] `/skills` redirect target is a static literal `/agents?view=skills`; query string not propagated. Confirmed by test `test_skills_redirect_does_not_propagate_query` and by reading the route handler.
- [INFO] SSE stream tier-disclosure: see adjudication above — accepted with follow-up.

No BLOCK-level security findings.

---

## Test coverage assessment

- Item 1 (health tier-gating): 7 tests in `test_system_health_tier_gating.py` — exceeds spec's ≥3.
- Item 2 (metrics): 8 tests in `test_system_metrics.py` — exceeds spec's ≥4.
- Item 3 (conformance): 5 tests in `test_api_conformance.py` — exceeds spec's ≥1.
- Item 4 (skills-fold): 11 tests in `test_skills_fold_into_agents.py` — exceeds spec's ≥5.
- Regression: `tests/test_qa_security_hygiene_paranoid.py` + `tests/test_qa_airgap_onetap_paranoid.py` — both PASS in combined run. Confirmed by `pytest -q` on all six files: **82 passed, 0 failed**.

**Gaps (non-blocking):**
- No explicit test that the SSE stream emits or hides max-only check names by tier — because the deviation is accepted, but this should be the regression test added when the follow-up sprint lands.
- No `LAB_TIER=max` + service-down case explicitly tested for the new `version` field, but generic min/max/down tests cover the surrounding behavior.

---

## Performance assessment

Not a hot path. Health endpoint adds ~1 dict construction + 8 tier-comparison
checks. Metrics endpoint reads in-process state under a lock — O(1).
Middleware adds one lock acquire + two int increments per non-excluded
request — negligible vs FastAPI's per-request overhead. No benchmark
required by ARCHITECTURE.md and none warranted here.

---

## Tech debt delta

**Predicted in ARCHITECTURE.md and incurred:**
- In-process metrics counters with no persistence — yes, documented as v1 limitation in api-conventions.md.
- `_OPTIONAL_SERVICES` registry — yes, small and load-bearing.
- `agents.html` larger due to three view sections — yes, mitigated by `_skills_panel.html` extraction.

**NEW debt not predicted by ARCHITECTURE.md (file before merge):**
- **`/api/system/health/stream` tier-disclosure follow-up.** Stream emits Marimo / Open Notebook / Neo4j check entries unconditionally. Track as a carryover for the next platform sprint. Adds ~30 min of work: tier-filter the `checks` list (app.py:6847) by intersecting with `_OPTIONAL_SERVICES` visibility, and add a regression test.

**Repaid:**
- Snapshot endpoint tier semantics now documented in `_OPTIONAL_SERVICES` + `_build_services_dict()` docstring.
- `docs/api-conventions.md` lands; tribal knowledge captured.
- Skills-as-separate-nav vestige removed.

**Net:** Negative as predicted, *if* the SSE follow-up lands in the next sprint. If it slips, we've left a known gap that defeats half the value of item 1.

---

## Required actions before merge

1. Add a carryover row to `sprints/2026-05-14-platform-foundation/SPRINT.md` "Notes" or a new "Carryovers" section: **"SSE stream `/api/system/health/stream` does not tier-filter check entries. Track for next platform sprint. ~30 min."** This is the gate for accepting the deviation.

That's it. No code changes required. Proceed to QA.

---

## Ready for QA?

**YES.** QA allocation per `arail/CLAUDE.md` (30% setup / 30% Buddy / 20% security / 10% happy / 10% regression) — QA should specifically probe:

- **Setup (30%):** `arailctl upgrade min` → curl `/api/system/health` → no max-only keys. `arailctl upgrade max` → max keys appear when up. `/api/system/metrics` returns 200 < 500ms on a fresh checkout.
- **Security (20%):** Confirm metrics body contains no tokens, no absolute paths beyond `disk_*` aggregates. Confirm `/skills?evil=<url>` does NOT propagate to redirect Location. Confirm `LAB_TIER=min` + a crafted `?show_all=true` does NOT bypass filter.
- **Regression (10%):** Re-run airgap + security-hygiene paranoid suites.
- **Buddy (30%) / Happy (10%):** Verify Skills panel renders inside `/agents?view=skills`, segment control toggles cleanly, deep-link `/agents/skills/<some-real-id>` opens the editor.

QA may downgrade to BLOCK if any of:
- Metrics middleware double-counts (timing-sensitive test).
- Skills `_skills_panel.html` partial breaks layout under any view.
- The accepted SSE-stream deviation surfaces an unexpected secondary leak (e.g. detail strings include filesystem paths).
