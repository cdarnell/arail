# Build log: Provider-aware chat dropdown (4-layer expanded sprint)

**Architecture:** [ARCHITECTURE.md](./ARCHITECTURE.md) at 9f4664e
**Started:** 2026-05-20

## Plan

| # | Files | Change | Test | Commit ref |
|---|---|---|---|---|
| 1 | `app.py`, `chat.legacy.html` | Phase A: Add 5 new providers to `_PROVIDER_KEY_ENVS`/`_PROVIDER_META`; add JS `PROVIDER_META`/`CLOUD` + 5 radios (L2) | F-PROVIDER-DRIFT | — |
| 2 | `model_specs.py` | Phase A: `context_tokens()` + `context_label()` + unit tests | model_specs unit | — |
| 3 | `chat/__init__.py`, `chat/models_catalog.yaml` | Phase A: Extend `CatalogEntry` + `as_dict()` with `provider`/`ctx`; add cloud YAML rows; back-compat test R4 | R4, F-CATALOG | — |
| 4 | `router/backends.py` | Phase B: `_resolve_ctx_override()`; wire into `CPUBackend.__init__` `n_ctx`. **R2 written first.** | R2, then CPUBackend wiring | — |
| 5 | `router/backends.py` | Phase B: `OllamaNativeBackend` + register in `BACKEND_MAP` (F-NEW, F-OLLAMA-SHIM) | F-NEW/F-OLLAMA-SHIM unit | — |
| 6 | `app.py` | Phase B: Factor `_persist_ctx_override()` out of `admin_models_set_ctx`; admin path stays green | admin ctx test | — |
| 7 | `app.py` | Phase C: Factor `_fetch_provider_models()` out of `providers_models`; both share it | — | — |
| 8 | `app.py` | Phase C: `/api/chat/models` cloud branch (airgap→no-token→gallery; override `current`). **R1 golden snapshot written first.** | R1, F-CLOUD-CURRENT, R3, F-AIRGAP | — |
| 9 | `app.py` | Phase C: `POST /api/chat/models/set-ctx` (relaxed validation, cache purge) | F-VALIDATE, F-CACHE | — |
| 10 | `app.py` | Phase C: `POST /api/chat/default` + `_apply_chat_defaults` wired into `api_chat`/`api_chat_stream` | F-DEFAULT-LEAK, L4 | — |
| 11 | `chat.legacy.html` | Phase D: `loadModels(provider)` with seq-guard; loading/CTA/airgap/error render states (F-RACE) | F-RACE | — |
| 12 | `chat.legacy.html` | Phase D: Radio change → `setActiveProvider()` then `loadModels(provider)` | — | — |
| 13 | `chat.legacy.html` | Phase D: ctx card fields + inline set control on selected local card; OOM hint | F-OOM | — |
| 14 | `chat.legacy.html` | Phase D: L4 "Set as default" control + status + "Reset" link | L4 UI | — |

Tests written regression-first where mandated:
- R2 written BEFORE step 4 (CPUBackend ctx wiring)
- R1 written BEFORE step 8 (cloud branch)
- R3 written with step 8, parametrized over all 10 providers

## Execution

### Step 1 — Phase A: Five new providers + JS/HTML registration
Commit: TBD

### Step 2 — Phase A: `context_tokens` / `context_label` + unit tests
Commit: TBD

### Step 3 — Phase A: `CatalogEntry` extension + cloud YAML rows + R4
Commit: TBD

### Step 4 — Phase B: `_resolve_ctx_override` + CPUBackend `n_ctx` (R2 first)
Commit: TBD

### Step 5 — Phase B: `OllamaNativeBackend` + `BACKEND_MAP` registration
Commit: TBD

### Step 6 — Phase B: Factor `_persist_ctx_override` (admin path DRY)
Commit: TBD

### Step 7 — Phase C: Factor `_fetch_provider_models`
Commit: TBD

### Step 8 — Phase C: `/api/chat/models` cloud branch (R1 first, then R3)
Commit: TBD

### Step 9 — Phase C: `POST /api/chat/models/set-ctx`
Commit: TBD

### Step 10 — Phase C: `POST /api/chat/default` + `_apply_chat_defaults`
Commit: TBD

### Step 11 — Phase D: `loadModels(provider)` with seq-guard
Commit: TBD

### Step 12 — Phase D: Radio → `setActiveProvider` → `loadModels`
Commit: TBD

### Step 13 — Phase D: ctx card fields + OOM hint
Commit: TBD

### Step 14 — Phase D: L4 "Set as default" control
Commit: TBD

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

## Final state

TBD — will update with test counts after step 14.
