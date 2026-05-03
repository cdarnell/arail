# Test report: Models Admin + Hard 35B Rule + Dashboard Reorg

**Date:** 2026-05-03
**Build:** [BUILD_LOG.md](./BUILD_LOG.md) at `736b6a3` (HEAD of branch)
**Architecture:** [ARCHITECTURE.md](./ARCHITECTURE.md)
**Review:** [REVIEW.md](./REVIEW.md) (PASS, post loop-back)
**QA:** qa subagent

---

## Verdict: PASS

- **125 new tests passing** + **1 xfail** flagging a low-severity defect
  (DEFECT-1, null-byte model_id surfaces as `ValueError`/500 instead of
  400 — does not bypass any security check, just degrades the API shape).
- **Full suite: 513 passed, 5 failed, 1 xfailed.** The 5 failures are the
  same pre-existing tests called out in BUILD_LOG.md and REVIEW.md (zero
  new failures introduced).
- All five architect MUST-HIT scenarios covered by dedicated tests.
- Onboarding-gate boundary verified by both source-grep AND live request:
  `/api/admin/models/{scan,load,unload,set-default,set-ctx}` are all 401
  before onboarding.
- Dispatch override is server-side only — clients lying about `backend:
  "mlx"` with a 70B model still get routed through Deep, proven by
  asserting which mock backend's `complete()` was actually called.
- HTML quoting fix (Fix 1, Issue 1 BLOCK) verified with both source-grep
  and a parameterised hostile-id corpus parsed via stdlib `html.parser`.

---

## Coverage by allocation bucket

ARAIL allocation: **30% setup / 30% Buddy / 20% security / 10% happy /
10% regression** (per `arail/CLAUDE.md`).

| Bucket | Target % | Test count | Notes |
|---|---|---|---|
| Setup | 30% | ~38 | model_specs imports clean; empty/missing `lab/models/` handled; metadata override registry shape; lru_cache plumbing; module re-import safety. |
| Buddy / agents | 30% | ~38 | Dispatch override (chat picker still works) — 9 tests; HTML safety (admin Models picker) — 17 tests; metadata override (chat picker badge data source) — 12 tests. |
| Security | 20% | ~26 | Path traversal corpus (12 parametrized cases) + length cap + null-byte (xfail), onboarding-gate enforcement (4 tests), set-default rejects streamed model, server-side dispatch override (5 tests), allowlist source-grep verification. |
| Happy | 10% | ~13 | Scan happy path, set-default mirror-write, set-ctx happy + boundary, dashboard renders both empty + populated state, Llama-4 routes correctly. |
| Regression | 10% | ~10 | TTL-cache + `?force=1` plumbing, dashboard layout invariants (D1/D3/D4/D6), pre-existing 5 failures isolation confirmed. |
| **Total** | **100%** | **125 + 1 xfail** | |

(Allocation buckets are approximate — many tests cover more than one
concern.)

---

## Architect MUST-HIT scenarios

| # | Scenario | Covered by | Status |
|---|---|---|---|
| **A1** | Direct API bypass: `POST /api/chat backend="mlx" + 70B model` must route to Deep server-side | `tests/test_dispatch_35b_enforcement.py::test_chat_with_backend_mlx_and_70b_model_routes_to_deep` (+ 4 supporting tests) | **PASS** |
| **C1** | Path traversal in `/api/admin/models/{load,unload,set-default,set-ctx}` rejected with 400; nothing outside `lab/models/` touched | `tests/test_admin_models_endpoints.py::test_load_rejects_path_traversal` (parametrized over 12 hostile inputs) + `test_set_default_path_traversal_rejected` + `test_load_rejects_oversized_model_id` | **PASS** (1 xfail on null-byte → see DEFECT-1) |
| **C5** | Two simultaneous POSTs to `/load` with same model_id → second returns 409 | `tests/test_admin_models_endpoints.py::test_concurrent_load_returns_409` | **PASS** |
| **C13** | Unload while in-flight → 409; `force=true` bypass succeeds | `tests/test_admin_models_endpoints.py::test_unload_while_inflight_chat_returns_409` + `test_unload_while_inflight_with_force_true_bypasses` + `test_unload_default_chat_inflight_also_blocks` | **PASS** |
| **HTML quoting regression** | Hostile model_ids parsed with real HTML parser; data-id round-trips correctly | `tests/test_admin_models_html_safety.py::test_render_with_hostile_id_parses_correctly` (parametrized over 9 hostile ids) + 5 source-level checks | **PASS** |

---

## Defects discovered

### DEFECT-1 — null-byte model_id surfaces as 500, not 400 [LOW]

**Symptom:** `POST /api/admin/models/load` with `{"model_id":
"Qwen3-8B-4bit\x00.txt"}` causes `Path.resolve()` →
`os.path.realpath()` to raise `ValueError: embedded null byte`. The
exception escapes the FastAPI handler and surfaces as a 500 (or
propagates to the TestClient caller, depending on Starlette version).

**Minimal repro:**
```python
import os; os.environ["ARAIL_PASSWORD"] = "x"
from arail.portal.app import app
from fastapi.testclient import TestClient
TestClient(app).post("/api/admin/models/load",
                     json={"model_id": "Qwen3-8B-4bit\x00.txt"})
# → ValueError: embedded null byte (or 500)
```

**Where:** `_validate_model_id` at `app.py:3542–3564`. The string-level
guards (`..`/`/`/`\\`) pass, then `Path.resolve()` blows up before the
whitelist check can catch it.

**Severity: LOW.** Not a security bypass — the model still doesn't load
and no path is touched. But the API contract says hostile input → 4xx,
not 5xx. Filed as `xfail` in
`tests/test_admin_models_endpoints.py::test_load_rejects_null_byte` so
that the moment the builder fixes it (one-line `if "\x00" in model_id:
return False, "null byte in model_id"` at the top of `_validate_model_id`),
the test will start failing (`XPASS strict`-style) and force a
follow-up PR.

**Suggested fix:** Add `if "\x00" in model_id: return False, "null byte
rejected"` before the path-resolution step (one line at app.py:3553).

---

## Security review

| Surface | Checked | Findings |
|---|---|---|
| **Path traversal in admin endpoints** | 12-input parametrized corpus (`../../etc/passwd`, `/absolute/...`, `Llama-3.1-70B/../../../etc/passwd`, `..`, `../`, `foo/../bar`, `foo\\..\\bar`, `foo\\bar`, `/`, `\\`, `~/.ssh/id_rsa`, `.`) — all return 400 | All cases caught by `_validate_model_id`'s string-level guards (`..`/`/`/`\\`) before any FS access. Defense-in-depth: `Path.resolve()` containment + scan-result whitelist as second + third lines. **DEFECT-1** for the null-byte input is documented. |
| **Activity-log injection via model_id** | length cap test at 257 chars, character-set tests via path-traversal corpus | Length cap fires at 256 chars before any log emit (app.py:3549). Path-separator chars rejected before reaching `activity_log.emit`. |
| **35B server-side enforcement** | `POST /api/chat backend="mlx" + 70B model`, then assert which mock backend was called | Server overrides client backend in `_prepare_chat_context` (app.py:4140–4151). Both streaming and non-streaming paths inherit it. The fake `_FakeDeepBackend.complete()` is called; `_FakePrimaryRouter.complete()` is NOT. Audit: every override emits an `info`-level activity_log line (verified by `test_chat_dispatch_override_emits_activity_log`). |
| **Onboarding gate** | All five `/api/admin/models/*` endpoints called pre-onboarding | All return 401. Source-grep confirms `/api/admin/models` is NOT in `allowed_prefixes` (app.py:158–168). Verified by `test_allowlist_does_not_contain_admin_models`. |
| **Set-default streamed-model rejection** | `POST /api/admin/models/set-default model_id="Llama-3.1-70B"` | Returns 400 with "Streamed models cannot be the default GPU model" (app.py:3759–3769). |
| **Secrets persistence** | `_write_secrets` mocked; verified `MODEL_NAME` mirror-write + `ARAIL_DEFAULT_GPU_MODEL` keys + JSON-encoded `ARAIL_MODEL_CTX_OVERRIDES` | Both keys persist as expected. The "Restart Lab to apply" message surfaces in the response body (operator visibility). |
| **JSON body parsing** | malformed JSON, missing keys, wrong types | Returns 400 with `ok=false`; never 5xx. |
| **CSRF / cross-origin** | Out of scope for this sprint per ARCHITECTURE.md note ("/api/admin/* posture unchanged from prior sprint"). | n/a |

---

## Performance

N/A. This sprint touched a non-hot path (admin endpoints + dispatch
override). The dispatch override adds one dictionary lookup +
`@lru_cache`d regex check per chat request — measurable as O(1) after
cache warm-up. No benchmark filed.

---

## Coverage delta

Test count delta verified by running the full suite before and after:

```
Before sprint (a4ef0b1, baseline): 388 passed, 5 failed
After sprint  (736b6a3, this branch): 513 passed, 5 failed, 1 xfailed
```

**Net new tests: 125 passing + 1 xfailed = 126 total new tests.**

Pre-existing 5 failures isolation confirmed:
- `test_buddy_suggesters::test_next_experiment_flags_uncovered_term`
- `test_chat_ui::test_chat_page_renders_compact_single_thread_shell`
- `test_drafter::test_loader_resolves_drafter_via_seed`
- `test_toast_ui::test_css_includes_toast_styles`
- `test_toast_ui::test_activity_event_level_suggest_renders`

These are unchanged from main (`a4ef0b1`); zero new failures introduced.

---

## Final test counts

| Metric | Value |
|---|---|
| New test files added | **5** (one atomic commit each: `be48a18`, `66d9596`, `9435197`, `d09a20a`, `736b6a3`) |
| Total new tests | **126** (125 pass + 1 xfail) |
| New test code LOC | **1,569** lines |
| New tests runtime | **~3.4 seconds** (well under the <30s target) |
| Defects discovered | **1** (DEFECT-1, severity LOW, captured as `xfail`) |
| Pre-existing failures unchanged | **5 / 5 confirmed** |
| New regressions introduced | **0** |

---

## Notes for the next QA pass

Patterns spotted while writing these tests:

1. **`_validate_model_id` filesystem-resolution path needs an explicit
   null-byte / control-character pre-filter.** The string-level guards
   only check `..`/`/`/`\\`. Any character class that survives those but
   blows up at the OS layer (`\x00`, `\n` on some FS, very long paths
   on Windows) will surface as a 500. DEFECT-1 captured this for null
   bytes; consider a broader allowlist (e.g. `re.match(r"[A-Za-z0-9._-]+",
   model_id)`).
2. **The `_OPTIONAL_CHAT_BACKEND_CACHE` is module-global.** Tests that
   exercise dispatch must monkeypatch `_get_optional_chat_backend` rather
   than relying on the cache being clean. Documented here so the next QA
   doesn't get bitten by stale-cache flakiness.
3. **Issue 6 (state-stickiness on `_CHAT_MODEL_LOAD_STATE`) from the
   re-review is still open as INFO-level.** Not tested in this pass per
   the architect's note that it's a deferred follow-up. If a real corrupt
   model lands in `lab/models/`, a future QA pass should exercise the
   admin → chat-state propagation path explicitly.
4. **Areas under-tested:** the streaming path's `_run_chat_completion_stream`
   was tested only at the `_prepare_chat_context` boundary. A full
   end-to-end SSE-stream test would catch any subtle async-iterator bug
   in the override path. Filed as a future-QA follow-up.
5. **HTML safety tests use a synthetic render of the JS template, not
   the actual JS execution.** A jsdom or Playwright run would be the
   gold standard but adds dependencies. The synthetic-render +
   source-grep combo is the cheapest reliable fallback and matches the
   architect's "verify with a real HTML parser" suggestion.
