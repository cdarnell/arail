# Build log: Provider-aware chat dropdown (4-layer expanded sprint)

**Architecture:** [ARCHITECTURE.md](./ARCHITECTURE.md) at 9f4664e
**Started:** 2026-05-20

## Plan

| # | Files | Change | Test | Commit ref |
|---|---|---|---|---|
| 1 | `app.py`, `chat.legacy.html` | Phase A: Add 5 new providers to `_PROVIDER_KEY_ENVS`/`_PROVIDER_META`; add JS `PROVIDER_META`/`CLOUD` + 5 radios (L2) | F-PROVIDER-DRIFT | 8ca221d |
| 2 | `model_specs.py` | Phase A: `context_tokens()` + `context_label()` + unit tests | model_specs unit | 6024e6a |
| 3 | `chat/__init__.py`, `chat/models_catalog.yaml` | Phase A: Extend `CatalogEntry` + `as_dict()` with `provider`/`ctx`; add cloud YAML rows; back-compat test R4 | R4, F-CATALOG | d1a3bd1 |
| 4 | `router/backends.py` | Phase B: `_resolve_ctx_override()`; wire into `CPUBackend.__init__` `n_ctx`. **R2 written first.** | R2, then CPUBackend wiring | 716b553 |
| 5 | `router/backends.py` | Phase B: `OllamaNativeBackend` + register in `BACKEND_MAP` (F-NEW, F-OLLAMA-SHIM) | F-NEW/F-OLLAMA-SHIM unit | 788652e |
| 6 | `app.py` | Phase B: Factor `_persist_ctx_override()` out of `admin_models_set_ctx`; admin path stays green | admin ctx test | 27c5061 |
| 7 | `app.py` | Phase C: Factor `_fetch_provider_models()` out of `providers_models`; both share it | — | b61972c |
| 8 | `app.py` | Phase C: `/api/chat/models` cloud branch (airgap→no-token→gallery; override `current`). **R1 golden snapshot written first.** | R1, F-CLOUD-CURRENT, R3, F-AIRGAP | 50bb107 |
| 9 | `app.py` | Phase C: `POST /api/chat/models/set-ctx` (relaxed validation, cache purge) | F-VALIDATE, F-CACHE | 31e7e33 |
| 10 | `app.py` | Phase C: `POST /api/chat/default` + `_apply_chat_defaults` wired into `api_chat`/`api_chat_stream` | F-DEFAULT-LEAK, L4 | f41d66c |
| 11+12 | `chat.legacy.html` | Phase D: `loadModels(provider)` with seq-guard; radio change wiring (steps 11+12 combined) | F-RACE | 78465f3 |
| 13 | `chat.legacy.html` | Phase D: ctx card fields + inline set control on selected local card; OOM hint | F-OOM | 53060dd |
| 14 | `chat.legacy.html` | Phase D: L4 "Set as default" control + status + "Reset" link | L4 UI | 5fba162 |

Tests written regression-first where mandated:
- R2 written BEFORE step 4 (CPUBackend ctx wiring)
- R1 written BEFORE step 8 (cloud branch)
- R3 written with step 8, parametrized over all 10 providers

## Execution

### Step 1 — Phase A: Five new providers + JS/HTML registration
Added xai/google/mistral/cohere/together to `_PROVIDER_KEY_ENVS`, `_PROVIDER_META`, JS `PROVIDER_META`, `CLOUD` array, and five radio `<label class="compute-opt">` entries.
Commit: 8ca221d

### Step 2 — Phase A: `context_tokens` / `context_label` + unit tests
`context_tokens(label)` with `@lru_cache(maxsize=512)` parses K/M/k/m suffixes; returns None on unparse. `context_label(model_name)` convenience lookup. 23 tests in `tests/test_context_tokens.py`.
Commit: 6024e6a

### Step 3 — Phase A: `CatalogEntry` extension + cloud YAML rows + R4
Added `provider: str | None` and `ctx: str | None` fields with `field(default=None)` to `CatalogEntry`. `as_dict()` always emits both keys. 24 cloud YAML rows added (claude/nvidia/openrouter/huggingface/xai/google/mistral/cohere/together). 7 R4 back-compat tests all pass.
Commit: d1a3bd1

### Step 4 — Phase B: `_resolve_ctx_override` + `CPUBackend` n_ctx (R2 first)
R2 baseline written before CPUBackend wiring. `_resolve_ctx_override(model_name, default)` does exact→substring→spec→default chain; clamps [256..1M]; handles bad JSON gracefully. `CPUBackend.__init__` uses it instead of hardcoded 4096. 10 tests pass.
Commit: 716b553

### Step 5 — Phase B: `OllamaNativeBackend` + `BACKEND_MAP`

`OllamaNativeBackend(OpenAICompatBackend)`: `_ollama_root()` strips `/v1`; `complete()`/`stream_complete()` POST to `{root}/api/chat` with `options.num_ctx` only when `getattr(self, '_num_ctx', None)` is set (F-NEW). 11 tests pass.
Commit: 788652e

### Step 6 — Phase B: Factor `_persist_ctx_override`
Extracted shared `_persist_ctx_override(model_id, ctx) -> dict` function. Admin and chat set-ctx paths both call it. Admin path keeps strict `_validate_model_id`; chat gets relaxed gate (step 9).
Commit: 27c5061

### Step 7 — Phase C: Factor `_fetch_provider_models`
`_fetch_provider_models(provider) -> list[str]`: live `/models` call for providers with `models_path`; curated YAML fallback for huggingface/google/cohere (no standard endpoint); cap 200; returns [] on any error. `providers_models` route delegates to it.
Commit: b61972c

### Step 8 — Phase C: `/api/chat/models` cloud branch (R1+R3+F-CLOUD-CURRENT)
Cloud branch guard: `if provider and provider.strip().lower() not in ("", "my_machine"):`. F-AIRGAP checked first; no-token CTA; gallery built; F-CLOUD-CURRENT: `current` = first cloud model id. Legacy branch untouched (R1). R3 parametrized over all 10 providers. 29 tests pass.
Commit: 50bb107

### Step 9 — Phase C: `POST /api/chat/models/set-ctx`
`_validate_local_model_id_relaxed()`: accepts Ollama ids, rejects cloud ids, rejects traversal (`..`, `/`), rejects empty, rejects >256 chars. Purges `_RUNTIME_BACKEND_CACHE` keys for the model; resets `_MODELS_SCAN_TS = 0.0`. All errors return HTTP 200 with `{ok: False, error: "..."}`. 9 tests pass.
Commit: 31e7e33

### Step 10 — Phase C: `POST /api/chat/default` + `_apply_chat_defaults`
`_apply_chat_defaults(backend, model, runtime)`: per-message values win (A8); reads `ARAIL_CHAT_DEFAULT_MODEL` from secrets.env or os.environ; F-DEFAULT-LEAK: drops stored cloud default when `_is_airgapped()` True; bad JSON degrades silently. SET path airgap-checks cloud providers; CLEAR path removes the env key. Wired into `api_chat` and `api_chat_stream`. 8 tests pass; R3 default-airgap tests (10 cases) now pass.
Commit: f41d66c

### Steps 11+12 — Phase D: `loadModels(provider)` + radio wiring (combined)

Steps 11+12 combined: `setActiveProvider` already calls `loadModels(provider)` after the POST so radio change triggers gallery reload in one atomic commit. F-RACE seq-guard via `_loadModelsSeq` counter. Render states: loading spinner → airgap banner / no-token CTA / unknown-provider CTA / cloud card grid / error fallback. CTA "Open provider settings" button wired to `openProvidersModal()`. Initial `loadModels(selectedProvider())` on page load.
Commit: 78465f3

### Step 13 — Phase D: ctx card fields + inline set control + OOM hint

`renderInstalledCards` adds `data-ctx` attribute and `.fmp-card-ctx` badge. `selectInstalled` calls `showCtxPanel(id)`. `showCtxPanel`: reveals `#fmp-ctx-panel`, populates current display, pre-fills input. `#fmp-ctx-set` click handler: POSTs to `POST /api/chat/models/set-ctx`; on success updates in-memory `FMP.installed` entry and re-renders; shows OOM hint for ctx >= 131072 (128K).
Commit: 53060dd

### Step 14 — Phase D: L4 "Set as default" control

`#fmp-set-default`: POSTs `{provider, model, runtime}` to `POST /api/chat/default`; on success shows "Default: MODEL (PROVIDER)" and reveals `#fmp-reset-default`. `#fmp-reset-default`: POSTs `{clear: true}`; on success shows "Default cleared" and hides reset link. Airgap enforcement is server-side.
Commit: 5fba162

## Open questions (architect's 3)

1. **ctx override key matching**: Using exact-then-substring fallback per the
   architect's preferred recommendation. Will flag if substring proves too loose.
2. **`current` with empty provider list**: Returns `null`, picker shows CTA row
   (not labeled error) — reads as "no models to select" which is accurate.
   Flagging in BUILD_LOG per instructions.
3. **OpenRouter 200-cap UX**: The unsorted 200 does read a bit dense but
   within acceptable limits for now. No scope expansion — noting for
   VISION disconfirming-evidence (b) follow-up.

## Architect feedback required

_(empty — no blockers encountered)_

## Fix-loop pass (2026-05-20, post-REVIEW.md BLOCK)

### Fix-loop B2 — wire OllamaNativeBackend into _get_runtime_backend ollama dispatch

`_get_runtime_backend`'s ollama branch was building `OpenAICompatBackend` at `/v1` and never
setting `_num_ctx`. Added runtime branch: ollama builds `OllamaNativeBackend.__new__` with
`_num_ctx = _resolve_ctx_override(model_id, default=None)` (ARCHITECTURE.md L3).
Added `tests/test_b2_ollama_dispatch_wiring.py` — 7 integration tests proving reachability
from dispatch and that ctx override flows into `options.num_ctx` in the POST body.
Commit: 6cd007b

### Fix-loop B1 — cloud gallery reads gallery.catalog not gallery.installed

Frontend cloud branch read `gallery.installed` (always `[]` for cloud) instead of
`gallery.catalog`. Fixed `chat.legacy.html:1175`: now reads `gallery.catalog` and maps
`.id` from each catalog entry object.
Added `tests/test_b1_cloud_gallery_contract.py` — 5 integration tests proving the
server↔frontend contract (cloud success populates catalog; no-token CTA returns empty;
local path gallery.installed unchanged).
Commit: 2566332

### Fix-loop C1 — R1 hardened to value-level golden snapshot

Prior R1 checked key presence only. Added `tests/test_r1_hardened_golden_snapshot.py` — 14
tests that mock `_get_primary_router`, `gallery_view`, and `_local_memory_snapshot`
deterministically, then assert exact top-level key set, gallery key set/types, nested dict
structures (deep/compact/hardware/model_load/onboarding), and no cloud-only fields leak.
Commit: f92f697

## Final state

**Tests:** 124 sprint-specific tests passing (0 failures) after fix-loop.
Pre-fix-loop count was 98; fix-loop adds 26 (B2: 7, B1: 5, C1: 14).

Full suite failure count: the "12 pre-existing failures" claim in the original ledger is
corrected per architect's review findings. Accurate statement: **every failure on this branch
is also present on origin/main; no new failure is introduced by this sprint.** The full-suite
failure count is order/environment-sensitive (13 on branch, 15 on main in the review harness).
The failures are in unrelated surfaces (docs routes, swarm, opencode lifecycle, dashboard
layout, system metrics, airgap-default env-leak pollution). No masked regression.

**Tech-debt note (C3):** `ARAIL_MODEL_CTX_OVERRIDES` is now consumed by `CPUBackend` (via
`_resolve_ctx_override` in `__init__`) and `OllamaNativeBackend` (via `_get_runtime_backend`
ollama branch). Other local backends (MLX, AeroLLM, AirLLM) still ignore it — the env var
is a no-op for those runtimes. Fix is deferred; note filed per architect carryover C3.

**Sprint test files (post-fix-loop):**

- `tests/test_context_tokens.py` — 23 tests (model_specs.context_tokens/context_label)
- `tests/test_catalog_entry_compat.py` — 7 tests (R4 CatalogEntry back-compat)
- `tests/test_ctx_override_backends.py` — 10 tests (R2 + _resolve_ctx_override)
- `tests/test_ollama_native_backend.py` — 11 tests (F-NEW/F-OLLAMA-SHIM unit)
- `tests/test_r1_r3_chat_models.py` — 29 tests (R1 routing/key-presence + R3/cloud-branch)
- `tests/test_r1_hardened_golden_snapshot.py` — 14 tests (R1 value-level golden snapshot)
- `tests/test_chat_set_ctx.py` — 9 tests (F-VALIDATE/F-CACHE)
- `tests/test_chat_default.py` — 9 tests (F-DEFAULT-LEAK/L4)
- `tests/test_b2_ollama_dispatch_wiring.py` — 7 tests (B2 reachability integration)
- `tests/test_b1_cloud_gallery_contract.py` — 5 tests (B1 server↔frontend contract)

**Commits:** 19 (15 original build + 4 fix-loop)

**Files changed in fix-loop:**

- `src/arail/portal/app.py` — B2: ollama dispatch builds OllamaNativeBackend with _num_ctx
- `src/arail/portal/templates/chat.legacy.html` — B1: cloud gallery reads gallery.catalog

**Scope drift:** None. No files touched outside the two wiring fixes and new test files.

**Deviations from original plan:**

- Steps 11+12 combined into one commit (setActiveProvider was the natural integration point).
- Step 10 updated R3 default-airgap tests that were committed in step 8 but previously failing.
- Fix-loop adds 4 commits beyond the original 15 (B2, B1, C1, ledger update).
