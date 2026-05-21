# Review: Provider-aware chat dropdown (4-layer expanded sprint)

**Date:** 2026-05-20
**Build:** [BUILD_LOG.md](./BUILD_LOG.md) at bf5a3f6
**Architecture:** [ARCHITECTURE.md](./ARCHITECTURE.md) at 9f4664e
**Branch:** qukaizen/arail-provider-aware-chat-dropdown (origin/main..HEAD = ba9f136..bf5a3f6)

## Verdict: BLOCK

The five mandatory corrections are all genuinely in the code, scope is clean, commit
hygiene is excellent, and security/token hygiene is sound. **But two real functional
defects mean the headline feature does not work end-to-end:**

1. **B1 — Cloud gallery renders empty even on success** (server↔frontend contract mismatch).
2. **B2 — L3 Ollama ctx is never wired into dispatch** (`OllamaNativeBackend` is built and
   unit-tested but never instantiated; the most common local runtime silently ignores ctx —
   the exact F-OLLAMA-SHIM trap the design was written to avoid).

Neither is in the "5 corrections / 3 regressions" gate, so each correction passed in isolation —
but the integration is broken. A user who flips to Claude sees "No models returned"; a user who
sets ctx on an Ollama model sees nothing change. Both must be fixed before ship.

---

## F-CLOUD-CURRENT + R1 status (explicit, as requested)

- **F-CLOUD-CURRENT — FIXED.** The cloud branch (`app.py:6007-6103`) is a self-contained
  early-return wrapper that returns BEFORE the legacy `current` computation at `app.py:6112`
  can ever run. In the cloud branch `current = cloud_model_ids[0] if cloud_model_ids else None`
  (line 6090) — never a local id. Proven by `test_cloud_branch_current_is_cloud_model_not_local`
  (asserts `current` ∉ {qwen2.5:7b, ai-eng:latest, ...}). The core bug is genuinely closed.
- **R1 — present but WEAKER than spec.** The design required a byte-identical golden snapshot of
  the no-provider payload ("the single most important test in the sprint"). As built,
  `test_r1_*` asserts only **key presence** (`R1_REQUIRED_TOP_KEYS - body.keys()`), which (a) does
  not detect *added* keys, and (b) does not compare values. It is not fake — it verifies the
  routing guard (no-provider / empty / my_machine all reach the legacy branch) and that no
  cloud-only field (`airgapped:true`) leaks in. Mitigating fact: I diffed the function and the
  legacy body is **byte-unchanged** — only the signature gained `provider: str = ""` and the cloud
  branch was inserted as a pure early-return above the untouched `try:`. So the regression risk is
  structurally low today. I am **not** BLOCKing on R1 (it is weak, not fake, and the path it guards
  is provably untouched), but hardening it to a value-level snapshot is a required carryover — as
  written it will not catch a *future* legacy-branch edit, which is the whole point of R1.

---

## Spec adherence

**The 5 mandatory corrections — all verified in code (not just claimed):**

| Correction | Status | Evidence |
|---|---|---|
| F-VALIDATE | PASS | `_validate_local_model_id_relaxed` (`app.py:6409-6443`) — NOT `_validate_model_id`. Accepts scan ∪ Ollama ids (`detect_installed_models`), rejects `..`/`/`/`\`, empty, >256, and unknown ids. Tests accept `qwen3:8b`, reject `claude-opus-4-7` and `../etc/passwd`. |
| F-CATALOG | PASS | `CatalogEntry` has `provider`/`ctx` = `field(default=None)` (`chat/__init__.py:43-44`); `as_dict()` always emits both (lines 60-61); `load_catalog` reads them (lines 94-95). Legacy rows default None. |
| F-CLOUD-CURRENT | PASS | See above — cloud branch overrides `current`; legacy `current` (line 6112) unreachable from cloud path. |
| F-CACHE | PASS | set-ctx purges every `_RUNTIME_BACKEND_CACHE` key where `k[1]==model_id` (`app.py:6482-6484`) AND sets `_MODELS_SCAN_TS=0.0` (6487). Cache key is `(runtime, model_id)` so `k[1]` is correct. Test plants 2 entries, asserts both gone. |
| F-DEFAULT-LEAK | PASS | Use-time: `_apply_chat_defaults` drops cloud default → my_machine when `_is_airgapped()` (`app.py:5422-5425`). Set-time: `/api/chat/default` refuses cloud default while airgapped (5472). Per-message wins (5401). |

**The 3 load-bearing regressions:**

| Regression | Status | Notes |
|---|---|---|
| R1 golden snapshot | WEAK | Key-presence + routing-guard test, not byte-identical value snapshot. Legacy body provably unchanged so risk is low; harden as carryover. |
| R2 unchanged complete() bodies | PASS | `test_openai_compat_complete_body_unchanged_without_ctx_override` captures `mock_session.post` args, asserts `num_ctx not in body` + standard keys; `n_ctx==4096` via FakeLlama. Genuine capture-and-compare. |
| R3 airgap parametrized | PASS | Iterates ALL 10 `_CLOUD_PROVIDERS` for both `/api/chat/models?provider=` and `/api/chat/default`; asserts `airgapped:true`/`ok:false` AND `requests.get/post.assert_not_called()`. Real. |

**Other failure modes:**

| Mode | Status | Evidence |
|---|---|---|
| F-NEW | PASS | `OllamaNativeBackend.complete` reads `getattr(self,"_num_ctx",None)` defensively (`backends.py:1356`); test builds via `__new__` with/without `_num_ctx`, no AttributeError. |
| F-OLLAMA-SHIM | **PARTIAL → see B2** | Class POSTs to `…/api/chat` not `/v1` (verified, well-tested) — but the class is never instantiated by dispatch, so the shim trap is NOT actually avoided in production. |
| F-COMPAT | PASS | `_fetch_provider_models` routes huggingface/google/cohere (empty `models_path`) to curated YAML; live providers have `/models`; tolerates missing `data`, returns `[]` on error. Verified `models_path` empty for those 3. |
| F-RACE | PASS | `_loadModelsSeq` ticket captured per call, checked after error AND success paths (`chat.legacy.html:1116/1127/1133`). Genuine seq-guard. |
| F-OOM | PASS | OOM hint shown for ctx ≥ 131072 in set-ctx handler; clamp 256..1M enforced server-side; no auto-apply. |
| F-MUSTSTREAM | PASS | `test_must_stream_rule.py` green; `model_specs.py` has NO real import of `arail.portal`/`app` (the grep match was the explanatory comment). |
| F-PROVIDER-DRIFT | PASS | Server `_PROVIDER_KEY_ENVS`/`_PROVIDER_META`/`_CLOUD_PROVIDERS` all contain the 10 (5 new); JS `PROVIDER_META` + `CLOUD` array both contain all 10; 10 radios present. Server↔JS parity holds. |

## Code quality findings

- [INFO] Cloud branch (`app.py:6007-6103`) is long but linear and well-commented; each sub-branch
  is a guard-return. Acceptable.
- [INFO] `_resolve_ctx_override` exact→substring→spec→default chain is clean and never raises.
- [INFO] Commit hygiene is exemplary: 13 build commits each map to one implementation step + its
  test, touching only relevant files (verified per-commit). `git revert` of any step is clean.
  The one combine (steps 11+12, commit 78465f3) is documented and justified.

## Security findings

- [INFO] **Token hygiene clean.** No new endpoint response contains a token value. `_provider_token`
  is read only to gate the no-token CTA; `/api/chat/default` writes ids only ("never a token" — and
  verified). Diff of added lines shows only env-var-NAME maps and docs URLs, no token echo.
- [INFO] **Airgap-first ordering verified on all 3 cloud-touching paths.** `/api/chat/models` cloud
  branch checks `_is_airgapped()` (line 6026) before token read (6039) or network (6059).
  `/api/chat/default` refuses cloud before any write (5472). set-ctx is local-only and rejects
  non-local ids. R3 proves no outbound call fires when airgapped, across all 10 providers.
- [INFO] **XSS (F7) covered.** Every upstream model id rendered into the DOM passes through
  `escapeHtml` (`chat.legacy.html:856`, used 22×, incl. cloud-card render at 1185-1190).
- [INFO] **Path traversal** on set-ctx model_id rejected (`..`, `/`, `\`) and gated to known local
  ids — tested.
- [INFO] Security suites green: `test_qa_security_hygiene_paranoid.py`,
  `test_qa_airgap_bypass_attempts.py` (96 passed combined with regression suites).

## Test coverage assessment

- **Sprint suite: 98 passed** (ran all 7 files myself — confirms builder's claim exactly).
- **Full suite: claim of "12 pre-existing failures" is imprecise but the material claim holds.**
  The full suite is order/pollution-sensitive: branch HEAD shows **13** failures in one run;
  origin/main shows **15** in the same harness. Authoritative finding: **every failure on the
  branch is also present on origin/main, and NO new failure is introduced by this sprint.** All
  failing tests are in unrelated surfaces (docs routes, swarm surfaces, opencode lifecycle,
  dashboard layout, system metrics, and an airgap-default test that PASSES in isolation —
  pre-existing env-leak pollution). `test_metrics_hybrid_mode` fails on main too. No masked
  regression (no branch failure offsets a sprint fix). The "12" should be corrected to "≤15,
  all pre-existing, none new" in the ledger.
- **Coverage gap:** there is NO test that the cloud-branch payload is actually consumed by the
  frontend renderer, and NO test that `OllamaNativeBackend` is reachable from dispatch. Both gaps
  are exactly where B1/B2 hide — unit tests proved the parts, nothing proved the wiring.

## Performance assessment

Not a hot path. `_fetch_provider_models` keeps the 200-cap and 12s timeout, sync `requests`
inside an async route (matches existing pattern; design noted `to_thread` as a non-blocking
future option). No regression. No benchmark gate required per design.

## Tech debt delta

Matches ARCHITECTURE.md prediction (dual ctx-validation gate, OllamaNativeBackend partial dup,
parallel provider lists, curated cloud rows) — all anticipated and fenced. **One unanticipated
debt item to file:** B2 means `ARAIL_MODEL_CTX_OVERRIDES` is now wired for llama.cpp/CPU but
still dead for Ollama (the design claimed L3 "finally wires it into n_ctx/num_ctx" — only half
true as built). The "setting does nothing" trap the design claimed to repay is still live for
the default local runtime.

## Required actions before merge

1. **[BLOCK] B1 — Cloud gallery renders empty on success.** Server puts cloud models in
   `gallery.catalog` (`app.py:6097`), but the frontend cloud branch reads
   `cloudModels = (gallery.installed || [])` (`chat.legacy.html:1175`) — always `[]` for cloud
   responses → hits the "No models returned for <provider>" empty state (line 1177) even when the
   fetch succeeded. Fix the frontend to read `gallery.catalog` (or have the server populate
   `installed` for cloud — but `catalog` is the design's documented shape, so fix the JS). Add an
   integration test that a successful cloud fetch renders ≥1 card.

2. **[BLOCK] B2 — L3 Ollama ctx not wired into dispatch.** `OllamaNativeBackend` exists in
   `backends.py` and is registered in `BACKEND_MAP`, but `_get_runtime_backend`'s ollama branch
   (`app.py:4919-4928`) still builds a plain `OpenAICompatBackend` at `…/v1` and never sets
   `_num_ctx` — so the native `/api/chat` + `options.num_ctx` path (the entire point of L3 for the
   default local runtime) is unreachable. The design's L3 data flow (ARCHITECTURE.md lines 100-109)
   required the ollama branch to build `OllamaNativeBackend` via `__new__` and set
   `be._num_ctx = _resolve_ctx_override(model_id, default=None)`. Implement that; add a test that a
   set ctx for an Ollama model produces `options.num_ctx` in the dispatched request body (not just
   in the standalone backend unit test).

3. **[ASK → carryover] R1 hardening.** Upgrade R1 from key-presence to a value-level golden snapshot
   (freeze the full no-provider payload with a deterministically-mocked local gallery; assert exact
   equality, catching added keys and changed values). Required so R1 protects future edits to the
   legacy branch — its stated purpose.

4. **[ASK → carryover] Correct the sprint ledger** failure-count claim from "12 pre-existing,
   unchanged" to "all pre-existing, none introduced (full-suite count is order-sensitive: 13 on
   branch, 15 on main in this harness; every branch failure also fails on main)."

5. **[INFO] File the B2 debt:** `ARAIL_MODEL_CTX_OVERRIDES` remains dead for Ollama until B2 is
   fixed; the design's "repaid debt" claim is only half-realized.

---

**Carryover/fix-list count:** 5 (2 BLOCK, 2 ASK-carryover, 1 INFO). Re-review required after
B1 + B2 are addressed.

---

## Re-review (loop 2)

**Date:** 2026-05-20
**Fix-loop commits reviewed:** `6cd007b` (B2), `2566332` (B1), `f92f697` (R1 harden / C1), `cf10b91` (C2+C3 ledger)
**origin/main at re-review:** c45e9a3 (main advanced one commit past the loop-1 fork point; no-regression checked against current main)

### Verdict: PASS

Both loop-1 BLOCKs are genuinely cleared in the live code, each now has a real
reachability/contract test (not isolated unit tests), R1 is hardened to exact-key-set +
nested-structure + types, the full suite introduces **zero** new failures vs main, and the
4 fix commits touched nothing beyond `app.py`, `chat.legacy.html`, the new test files, and
BUILD_LOG. The headline feature works end-to-end in my independent trace.

### B1 — CLEARED

- **Code:** `chat.legacy.html:1174-1177` now reads `gallery.catalog` (was `gallery.installed`,
  always `[]` for cloud) and maps `e => (typeof e === 'string' ? e : e.id)` — handles both
  string and object catalog entries. The local/`my_machine` branch (lines 1221-1257) is
  untouched and still renders from `gallery.installed` — verified by direct read, the two
  branches are cleanly separated by the `if (isCloud)` guard.
- **Test:** `test_b1_cloud_gallery_contract.py` (5 tests) is a real server↔frontend **contract**
  test via FastAPI TestClient against the live `/api/chat/models?provider=...` route. Asserts
  cloud success → `gallery.catalog` has ≥1 entry with `{id, installed_state:"available",
  source:"cloud", runtime==provider}` AND `gallery.installed == []`; every top-level `models`
  id appears in `catalog`; no-token → empty `catalog` + `cta.kind=="no_token"`; local path →
  `gallery.installed` is a list, `airgapped` not true. Proves a cloud success now produces
  renderable cards instead of the empty state.
- **Caveat (carryover for qa):** the B1 test asserts the *server* returns the shape the JS
  reads; it does not execute the JS in jsdom. The JS fix is a 2-line literal change I read and
  confirmed reads `gallery.catalog` and maps `.id`. Server-contract + my direct JS read close
  B1; a jsdom render assertion would be the ideal belt-and-suspenders. Low risk.

### B2 — CLEARED

- **Code:** `_get_runtime_backend`'s ollama branch (`app.py:4921-4933`) now builds
  `OllamaNativeBackend.__new__(...)` (NOT `OpenAICompatBackend`), sets `backend_name="ollama:native"`,
  and resolves `be._num_ctx = _resolve_ctx_override(model_id, default=None)` **in the branch**
  (per ARCHITECTURE.md L3, F-NEW). Non-ollama runtimes keep `OpenAICompatBackend` (no regression).
  `cache_key` remains `(runtime, model_id)`, so the F-CACHE purge from loop 1 still aligns
  (`k[1]==model_id`). `OllamaNativeBackend.complete` (`backends.py:1352+`) reads `_num_ctx`
  defensively, adds `options.num_ctx` only when set, and POSTs to `{root}/api/chat` (not `/v1`).
- **Test:** `test_b2_ollama_dispatch_wiring.py` (7 tests) is a real **reachability** test.
  `test_dispatch_ollama_returns_ollama_native_backend` asserts the *dispatch path* returns
  `OllamaNativeBackend`. `test_ctx_override_flows_into_num_ctx_for_ollama` plants
  `{"ai-eng:latest":16384}` in `ARAIL_MODEL_CTX_OVERRIDES`, calls `_get_runtime_backend`, then
  `complete()` and asserts `options.num_ctx == 16384` in the POST body — the full
  set-ctx→resolve→build→dispatch path. `test_dispatch_posts_to_api_chat_not_v1` asserts
  `/api/chat` in URL and `/v1/` absent. `test_no_ctx_override_means_no_num_ctx_in_dispatch`
  proves the no-override case omits `num_ctx` (preserves today's behavior). This is exactly the
  wiring the loop-1 unit tests failed to exercise.

### R1 — HARDENED (C1 cleared)

- `test_r1_hardened_golden_snapshot.py` (14 tests) deterministically mocks `_get_primary_router`,
  `gallery_view`, `_local_memory_snapshot`, `_get_live_ollama_current`, `_load_active_provider`,
  then asserts the **exact** top-level key set (added OR removed key fails), the **exact** gallery
  key set `{installed, catalog, runtime_counts}`, field types (backend:str, switchable:bool,
  models:list, gallery lists/dict), required nested key sets for `deep`/`compact`/`hardware`/
  `model_load`/`onboarding`, and that no cloud-only field (`airgapped:true`, `cta`) leaks. This is
  a genuine upgrade from loop-1's key-presence-only check and will catch a future legacy-branch
  edit that adds/removes a top-level or gallery key. The legacy `/api/chat/models` payload still
  passes (no regression). **Residual (minor carryover):** nested dicts use required-subset, not
  byte-exact value equality; a future *value* change inside `deep`/`compact` would not be caught.
  Acceptable — the spec's core concern (structural drift of the frozen branch) is now guarded.

### Did fixing B1 break R1? — No (the subtle check)

Confirmed independent. B1's commit `2566332` touched only `chat.legacy.html` (client JS); R1
snapshots the *server* payload. The B1 diff contains no server-side change. The R1 hardened
suite (14 tests) passes in the same run as B1, and the cloud branch is only entered for
`?provider=<cloud>` while R1 exercises the no-provider/empty/my_machine legacy path. No coupling.

### No regression

- **Sprint suite: 124 passed, 0 failed** (all 10 files; ran myself). Matches the builder's claim
  exactly. R2 (`test_ctx_override_backends.py`) and R3 (`test_r1_r3_chat_models.py`) both green —
  the fixes did not break the prior load-bearing regressions.
- **Full suite, no-new-failure proof:** ran the entire suite on branch HEAD (13 FAILED) and on
  current `origin/main` (c45e9a3, 15 FAILED) in the same harness. Set-diff: the failures present
  **on branch but not on main is EMPTY** — i.e. this sprint introduces zero new failures. The two
  extra failures on main (`test_docs_cross_links`, `test_docs_sprint3_qa`) are order/pollution-
  sensitive docs tests that don't fire in the branch run order; pre-existing, unrelated. All
  branch failures are in unrelated surfaces (opencode lifecycle, dashboard layout, docs routes,
  swarm, system metrics, airgap-default env-leak pollution). C2's corrected ledger wording ("every
  branch failure also fails on main; no new failure; count order-sensitive — 13 branch / 15 main")
  matches my independent observation exactly.

### No new scope drift

`git diff origin/main...HEAD --stat` plus per-commit diffstats confirm the 4 fix commits touched
only: `app.py` (B2 ollama branch, +23/-8), `chat.legacy.html` (B1, 2 effective lines),
`test_b2_ollama_dispatch_wiring.py`, `test_b1_cloud_gallery_contract.py`,
`test_r1_hardened_golden_snapshot.py`, and `BUILD_LOG.md`. No `chat.html` (WIP template stays
untouched per A-non-goal), no autoresearch, no agents, no token-storage / secrets.env code, no
new dependency. Token hygiene unchanged (no new endpoint, no token echo). Airgap ordering
unchanged. Clean.

### Tech debt delta (C3)

C3 note in BUILD_LOG is accurate: `ARAIL_MODEL_CTX_OVERRIDES` is now consumed by `CPUBackend`
(`__init__` n_ctx) and `OllamaNativeBackend` (dispatch branch `_num_ctx`); MLX, AeroLLM, and
AirLLM still ignore it. The loop-1 "B2 debt" (override dead for the default local runtime) is now
**closed for Ollama** — the headline-relevant runtime. Remaining no-op for MLX/AeroLLM/AirLLM is
filed and deferred. Net debt is now slightly negative vs loop 1 (the live trap the loop-1 review
flagged is repaid for the common case).

### Headline feature — works end-to-end (independent trace)

- Flip to Claude → server cloud branch returns `gallery.catalog=[cloud models]` → JS reads
  `gallery.catalog`, maps `.id`, renders cards. (Was: empty state on success. Now: cards.)
- Set ctx on an Ollama model → `set-ctx` persists + purges cache → next dispatch builds
  `OllamaNativeBackend` with resolved `_num_ctx` → `complete()` POSTs `/api/chat` with
  `options.num_ctx`. (Was: silently dropped via `/v1` shim. Now: honored.)

### Carryovers for qa (none blocking)

1. **B1 jsdom gap** — server-contract test proves the shape; no JS-execution (jsdom) test asserts
   the cards actually render in a DOM. Recommend qa add a focused JS/jsdom render assertion (also
   covers the F-RACE seq-guard interplay).
2. **R1 nested value-exactness** — top-level and gallery key sets are exact; nested dicts
   (`deep`/`compact`/`model_load`/`onboarding`) are required-subset, not byte-exact. A future
   value change inside those would slip through. Low priority; structural drift is covered.
3. **Full-suite order pollution** — the airgap-default and docs-routes tests pass in isolation but
   fail under full-suite env-leak pollution. Pre-existing on main; worth a separate housekeeping
   ticket (env teardown between tests), out of scope for this sprint.

### Required actions before merge (loop 2)

None. PASS. Proceed to qa with the three non-blocking carryovers above noted for coverage.
