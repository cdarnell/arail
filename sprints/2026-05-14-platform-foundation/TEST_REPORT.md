# Test report: Platform Foundation — health/metrics/OpenAPI/Skills-into-Agents

**Date:** 2026-05-15
**Build:** [BUILD_LOG.md](./BUILD_LOG.md) at 58aaae6 (architect WEAK_PASS, REVIEW.md @ 81ea4e2)
**Branch:** qukaizen/arail-platform-foundation
**Verdict:** **PASS**

QA allocation per `arail/CLAUDE.md`: 30% setup / 30% Buddy / 20% security /
10% happy / 10% regression. This sprint is platform-API rather than Buddy-touching,
so the 30% Buddy portion has been redirected toward additional security probes
and edge-case hunts on the new platform contracts — documented here for the next QA pass.

---

## Pytest run summary

```
pytest tests/test_system_health_tier_gating.py \
       tests/test_system_metrics.py \
       tests/test_api_conformance.py \
       tests/test_skills_fold_into_agents.py \
       tests/test_qa_platform_foundation_paranoid.py \
       tests/test_qa_security_hygiene_paranoid.py \
       tests/test_qa_airgap_onetap_paranoid.py -q

121 passed, 6 warnings in 5.47s
```

Breakdown:

| Suite | Tests | Status |
|---|---|---|
| test_system_health_tier_gating.py | 7 (builder) | pass |
| test_system_metrics.py | 8 (builder) | pass |
| test_api_conformance.py | 5 (builder) | pass |
| test_skills_fold_into_agents.py | 11 (builder) | pass |
| **test_qa_platform_foundation_paranoid.py (NEW)** | **39 (QA)** | **pass** |
| test_qa_security_hygiene_paranoid.py | regression | pass |
| test_qa_airgap_onetap_paranoid.py | regression | pass |

---

## Tests added (new file: `tests/test_qa_platform_foundation_paranoid.py`)

| # | Test | Asserts |
|---|---|---|
| 1–7 | `test_health_no_query_bypass_for_min_tier[?show_all=true/1, ?tier=max, ?lab_tier=max, ?include_max=1, ?all=1, ?debug=1]` | No query-string permutation reveals max-only services on `LAB_TIER=min`. |
| 8 | `test_health_tier_flip_no_cache` | Mutating `LAB_TIER` mid-process changes the visible `services` keyset on the next request (no stale module-level cache). |
| 9 | `test_health_empty_tier_defaults_to_min` | `LAB_TIER=""` collapses to min — forbidden keys absent. |
| 10 | `test_health_unknown_tier_defaults_to_min` | `LAB_TIER="unicorn-xyz"` clamps to min without raising. |
| 11 | `test_health_spec_tier_field_preserved` | The legacy `tier` field (spec-tier `minimum/standard/full/deep`) is not clobbered by the new lab-tier filter. |
| 12–15 | `test_metrics_only_allows_get[POST/PUT/DELETE/PATCH]` | Non-GET on `/api/system/metrics` returns 405-class. |
| 16 | `test_metrics_unknown_format_silently_ignored` | `?format=garbage` falls through to JSON 200 (api-conventions §4 forward-compat). |
| 17 | `test_metrics_body_no_absolute_paths` | No `/Users/...`, `/home/...`, `/etc/...`, or `$HOME` substring in metrics body. |
| 18 | `test_metrics_body_no_env_dump` | A sentinel `FOO_API_KEY`/`MY_SECRET` env value does NOT leak into metrics output. |
| 19 | `test_metrics_counter_concurrency` | 25 concurrent `/health` hits under an 8-worker thread pool produce `>= +25` increment (lock atomicity). |
| 20 | `test_metrics_active_provider_is_label_not_secret` | `active_provider` length < 64 and equals expected label. |
| 21 | `test_metrics_prometheus_error_envelope_conformant` | 501 envelope keys are exactly `{error, message}`; slug is snake_case lowercase. |
| 22–26 | `test_skills_redirect_ignores_open_redirect_payload[?next=https://evil.com / //evil.com / ?redirect= / ?url=javascript: / view+next combined]` | `/skills` Location header is the literal `/agents?view=skills` — no scheme://, no `evil.com`. |
| 27 | `test_skills_redirect_fragment_not_propagated` | Plain `/skills` redirects to fixed target (smoke). |
| 28–33 | `test_agents_skills_deeplink_exotic_id_safe[../../etc/passwd / urlencoded traversal / 512-char id / NUL-byte / <script> / spaces]` | Exotic `skill_id` does not crash, does not reflect XSS payload unescaped, does not leak `/etc/passwd` contents. |
| 34 | `test_agents_multiple_view_params_last_wins_or_safe` | `?view=status&view=skills` → 200, body contains a valid `data-view=` marker. |
| 35 | `test_agents_view_skills_html_no_data_uri_or_script_injection` | Rendered Skills view has no `javascript:` URI. |
| 36 | `test_skills_with_trailing_slash` | `/skills/` does NOT serve the deleted standalone page. |
| 37 | `test_api_conventions_known_drift_lists_at_least_3` | `docs/api-conventions.md` "Known drift" table has ≥ 3 entries. |
| 38 | `test_api_conventions_documents_error_envelope_shape` | api-conventions doc references `"error"` and `"message"` keys. |
| 39 | `test_metrics_self_call_not_counted_even_with_query` | Self-exclusion holds when `?format=…` is appended to the metrics URL. |

---

## Failures

None.

| # | Test | Symptom | Minimal repro | Severity |
|---|---|---|---|---|
| — | — | — | — | — |

---

## Per-section findings

### §0 conventions (regression / drift)

- `docs/api-conventions.md` "Known drift" table lists **5** pre-existing
  non-conformant endpoints (verified): `POST /api/system/mode`,
  `GET /api/system/health` (`service_checks`), `POST /api/skills/{id}`,
  `GET /api/agents/loadouts`, various `POST /api/agent/*`. Each named in
  the backlog with a stated next-touch remediation. **PASS** — no finding.
- Spot-checked `POST /api/system/mode` envelope (`{"ok": false, "error": "..."}`
  with no `message` key) — confirmed it is the very non-conformance the doc
  catalogs. Drift is named, not hidden.

### §1 health tier-gating

- 7 query-string bypass permutations all filter correctly (tests 1–7).
- Live tier flip works without caching (test 8). The implementation reads
  `LAB_TIER` per request via `_current_tier()`.
- Empty/unknown tier defaults to min — important for fresh-checkout
  setup where `LAB_TIER` may be unset (tests 9–10).
- Spec-tier `tier` field is preserved alongside the new lab-tier filter
  (test 11). The architect specifically flagged this collision risk.

### §2 metrics

- **No token leakage.** Confirmed by sentinel env-var test (test 18) and
  string-search test (REQUIRED_KEYS in builder suite + test 17).
- **No path disclosure.** No `/Users/`, `/home/`, `/etc/`, or HOME path
  fragments in the response body (test 17).
- **Method enforcement.** Non-GET methods return 405-class (tests 12–15).
- **Self-exclusion robust** under query-string variation (test 39).
- **Concurrency-safe.** 25 concurrent hits produce no lost increments
  (test 19) — the `_METRICS_LOCK` is doing its job.
- **`?format=garbage`** silently falls through to JSON 200 per api-conventions
  §4 forward-compat rule (test 16). The implementation only explicitly checks
  `prometheus`; all other values default to JSON. PASS.
- Confirmed `last_provider_change_unix` is wired to provider (Compute Source)
  changes and not to the airgap-mode toggle — by inspection of
  `app.py:7166–7205` (no metric write in the airgap-toggle handler). This
  matches the architect's intent: provider changes ≠ mode changes.

### §4 skills-fold

- **No open redirect.** Five payload shapes (incl. `javascript:` and
  protocol-relative `//evil.com`) all collapse to the fixed literal
  `Location: /agents?view=skills` (tests 22–26).
- **Path-traversal-safe deep-links.** `../../etc/passwd`, urlencoded
  variants, 512-char ids, NUL bytes, XSS payloads, and spaces all
  produce 200 or 404 with no leakage (tests 28–33). No `<script>`
  reflection. No `/etc/passwd` content.
- **Multi `?view=` params** handled deterministically (test 34).
- **`/skills/` trailing slash** does not serve the deleted standalone
  template (test 36).
- **No `javascript:` URI** in rendered Skills view (test 35).

### Cross-cutting regression

- `test_qa_security_hygiene_paranoid.py` and `test_qa_airgap_onetap_paranoid.py`
  both pass alongside the new tests. The new metrics middleware and
  `/skills` redirect do not regress the airgap one-tap protocol or the
  security-hygiene guards (no secret echo-back, no env dump,
  `lab/data/secrets.env` 0600 preserved).

---

## Security review

| Surface | Checked | Findings |
|---|---|---|
| User input | `/api/system/metrics` accepts only `?format=` (whitelisted); unknown values fall through. `/agents?view=` clamps to enum. `/agents/skills/{skill_id}` accepts arbitrary strings but never opens or reads them. | None. |
| Authentication | `/api/system/metrics` and `/api/system/health` are anonymous on loopback per VISION §"Tensions resolved" #1. Documented in api-conventions §8. Onboarding gate explicitly allow-lists `/api/system/metrics`. | Documented as accepted trade-off in REVIEW. No new finding. |
| File I/O | `kb_doc_count` walks `_pkb_root().rglob("*")` but only emits a count, never path strings. Confirmed by reading `app.py:6976-6983`. | None. |
| Network I/O | New endpoints are read-only and synchronous-ish; no SSRF surface. `/skills` redirect target is a static literal — no parameter influence. | None. |
| Deserialization | `/api/system/metrics` does not accept a body. `/skills` redirect has no body. | None. |
| Crypto | N/A — no crypto added this sprint. | N/A. |
| Dependencies | No new dependencies added; psutil already required and gracefully fallback-handled. | None. |
| Info disclosure (metrics body) | Verified no tokens, no absolute paths, no env-var dumps, no provider keys. `active_provider` is a short backend label (`"my_machine"`, `"openrouter"`). | None — see tests 17, 18, 20. |
| Open redirect (`/skills`) | 5 payload shapes verified non-propagating. | None — see tests 22–26. |
| Tier-gating bypass | 7 query-string shapes verified filtered. | None — see tests 1–7. |
| Path traversal (`/agents/skills/{id}`) | Encoded `../../etc/passwd` does not read file. NUL bytes and 512-char ids do not crash. | None — see tests 28–33. |
| SSE stream tier disclosure | Out-of-scope per architect adjudication (accepted deviation, follow-up filed in SPRINT carryovers). Not retested here. | Carryover already tracked. |

---

## Performance

Not a hot path. Metrics endpoint is O(1) under lock; tier filter is O(small_dict).
Concurrency test (test 19) ran 25 parallel `/health` calls in well under
the 5.47s total suite wall-clock; no benchmark warranted. N/A.

---

## Coverage delta

Builder tests (this sprint): 31 new tests (7 + 8 + 5 + 11).
QA tests (this report): **39 new tests** in `tests/test_qa_platform_foundation_paranoid.py`.
Combined required suite: 121 tests, 0 failures.

---

## Tech-debt items surfaced

1. **SSE stream tier disclosure** (already tracked in SPRINT.md Carryovers).
   Not retested here — accepted deviation per architect.
2. **`?format=garbage` is silently accepted** without a "did you mean" message.
   This is intentional per api-conventions §4, but a future enhancement could
   return 400 `invalid_query` when the value is clearly garbage. Not a finding.
3. **`/skills/` trailing slash behavior is implementation-defined** by Starlette
   (currently 307 to `/skills` then 302 to `/agents?view=skills` — two-hop).
   A small UX improvement would be to register the trailing-slash variant as a
   direct 302. Not blocking.
4. **Self-exclusion uses prefix match.** If a future route is added with
   path `/api/system/metrics_extra`, it would be silently excluded from
   counters. Consider tightening to exact-match-or-`/`-prefix. Filed for a
   future audit; current prefix list is `("/api/system/metrics",)` so only
   that exact route + sub-paths match — acceptable today.

---

## Notes for the next QA pass

- When the SSE-stream tier-filter follow-up lands, regression-test that the
  stream's `checks` list intersects `_OPTIONAL_SERVICES` visibility — the
  test fixture should set `LAB_TIER=min` and assert no `marimo`/`open-notebook`/
  `neo4j` check entries are emitted.
- Add a fuzz harness for `/agents/skills/{id}` once paperagents lands — at
  that point exotic IDs may map to real file lookups and traversal becomes
  load-bearing rather than smoke-only.
- The metrics middleware is the **third** `@app.middleware("http")` registered.
  Watch ordering when new middleware is added — counters should still see
  every non-excluded request.
- Consider extracting the `_client(monkeypatch, tmp_path)` helper into a
  shared `conftest.py` fixture; it's now duplicated across three test files.
