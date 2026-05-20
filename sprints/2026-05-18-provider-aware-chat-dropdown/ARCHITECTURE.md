# Architecture: Provider-aware chat dropdown (4-layer expanded sprint)

**Date:** 2026-05-20
**Spec:** [VISION.md](./VISION.md) + [SPRINT.md](./SPRINT.md) § "Scope expansion — 2026-05-20"
**Branch:** qukaizen/arail-provider-aware-chat-dropdown

## Restatement

Today the Chat tab's model picker is blind to the active Compute Source: `GET /api/chat/models`
(app.py ~5775) always reads the local runtime gallery (Ollama + MLX + on-disk) and ignores the
provider the user just selected, so flipping to Claude/OpenRouter leaves a local model id selected
that doesn't exist upstream — a silent-wrong dispatch. This sprint makes the picker honest
(**L1**) by teaching `/api/chat/models` a `?provider=` branch that returns the cloud provider's
models (or an empty-key CTA, or an airgap refusal) in the SAME gallery shape the frontend already
renders; adds five OpenAI-compatible cloud providers as pure registry entries (**L2**); surfaces
each model's context window with a resource-cost hint and wires the *already-existing-but-unused*
`ARAIL_MODEL_CTX_OVERRIDES` store into local inference at load time — llama.cpp `n_ctx` and a new
Ollama-native `/api/chat` backend with `options.num_ctx` (**L3**); and adds a chat-tab-only
"set as default" override so one click pins provider+model for all chat while per-message values
still win (**L4**). Active template is `chat.legacy.html`; the WIP `chat.html` is untouched.

## Assumptions

- **A1.** ctx is a **load-time** property, not a per-call parameter. llama.cpp fixes `n_ctx` at
  `Llama(...)` construction (backends.py:378); Ollama reloads the model when `num_ctx` changes.
  Therefore ctx is resolved when a backend is *built*, NOT threaded through `complete()`. This is
  load-bearing: it keeps `complete()`/`stream_complete()` signatures and request bodies
  byte-identical, which protects the local-inference regression surface.
- **A2.** Cloud model context windows are fixed per model upstream — ARAIL cannot change them.
  Cloud ctx is therefore **display-only**; the inline "set ctx" control appears on the selected
  **local** card only.
- **A3.** The five new providers (xAI, Google Gemini, Mistral, Cohere, Together) all speak an
  OpenAI-compatible `/v1` surface with **bearer** auth, so `_CLOUD_PROVIDERS` (derived from the
  key map) and `_auth_headers` (bearer fallback, app.py:1271) need **zero** changes — they are
  pure additions to `_PROVIDER_KEY_ENVS` + `_PROVIDER_META`.
- **A4.** The frontend `renderCatalogCards` / `renderInstalledCards` consume `gallery.installed`
  and `gallery.catalog` arrays of dicts. Reusing this exact shape for cloud models means **no card
  renderer changes** — cloud models are catalog entries with `installed_state:"available"`.
- **A5.** `LAB_MODE` default is `airgapped` (app.py:1100). Every cloud-touching endpoint must
  refuse before doing any network or token work. We do NOT relax this default.
- **A6.** Tokens live in `lab/data/secrets.env` chmod 0600, are never echoed back, never logged.
  All new code obeys this; no new endpoint returns a token value.
- **A7.** The catalog YAML loader (`load_catalog`, chat/__init__.py:55) reads only named keys via
  `.get()`, so adding optional `provider:`/`ctx:` fields to existing rows does not break parsing.
  **BUT** `CatalogEntry.as_dict()` (line 40) only emits the known fields — it must be extended to
  surface the new ones, or they vanish before reaching the gallery. (See F-CATALOG.)
- **A8.** Per-message overrides in the chat send path always win over stored defaults. L4's shim
  only fills *blanks*; it never overwrites a value the client sent.

### Non-goals (explicit)

- `chat.html` (the WIP template). Legacy only.
- Lab-wide override across autoresearch / agents. L4 is **chat tab only** (frozen-surface +
  OOM-caution discipline from MEMORY).
- Per-provider cost ceilings / auto-selecting a "sensible default" model on provider switch.
- Token streaming for Ollama-native. Today's runtime path already does a single blocking
  `complete()` emitted as one delta (app.py:5107); `OllamaNativeBackend` preserves that.
- Threading ctx into cloud backends or per-call dispatch (A1/A2).
- A search UI for OpenRouter's 200+ models (cap at 200 stays; VISION disconfirming-evidence (b)
  is the trigger to revisit, not this sprint).

## Data flow

### L1/L2 — picker populate

```
chat.legacy.html
  radio "compute-source" change
    → setActiveProvider()                POST /api/providers/active {provider}   (airgap-guarded already)
    → loadModels(provider)               GET  /api/chat/models?provider=<p>
         |                                   (seq-guard: stamp a request id; ignore stale responses)
         v
   app.py api_chat_models(provider?)
     if provider in (None,"","my_machine"):   # ── BYTE-IDENTICAL legacy branch ──
        <unchanged code path → local gallery payload>
     else:                                      # ── new cloud branch ──
        if _is_airgapped():        → {airgapped:true, gallery:{installed:[],catalog:[]}, cta:{kind:"airgapped",...}}
        elif not _provider_token:  → {gallery:{installed:[],catalog:[]}, cta:{kind:"no_token", provider, message, docs}}
        else:
            models = _fetch_provider_models(provider)   # shared with /api/providers/models
            gallery.catalog = [ {id, name, installed_state:"available", source:"cloud",
                                 runtime:<provider>, ctx, ctx_label, ...} for m in models ]
            current = <first cloud model or echoed selection>   # NOT the local model
        → {provider, current, gallery, cta?, airgapped?}
     frontend: loading → renderCatalogCards | renderCta | renderAirgap
```

### L3 — ctx into local inference (load-time)

```
SET path:
  selected LOCAL card "Set context" → POST /api/chat/models/set-ctx {model_id, ctx}
     → _persist_ctx_override(model_id, ctx)      # validate 256..1_000_000, write secrets.env + os.environ
     → purge _RUNTIME_BACKEND_CACHE entries whose key[1]==model_id   # CRITICAL (F-CACHE)
     → _MODELS_SCAN_TS = 0.0                       # invalidate scan cache (matches admin handler)

USE path (CPUBackend, load-time):
  CPUBackend.__init__ → n_ctx = _resolve_ctx_override(self.model_name, default=4096)

USE path (Ollama, load-time-equivalent):
  _prepare_chat_context → runtime_choice=="ollama"
     → _get_runtime_backend("ollama", model_id)
          builds OllamaNativeBackend via __new__ (NO __init__ — F-NEW)
          be._num_ctx = _resolve_ctx_override(model_id, default=None)   # resolve in branch, not __init__
     → response = backend.complete(prompt, max_tokens, temperature, top_p)
          OllamaNativeBackend.complete → POST {ollama_root}/api/chat   (root, NOT /v1)
              body={model, messages, stream:false, options:{num_ctx:<be._num_ctx>}}   # only if set
          parse NDJSON / single JSON → ModelResponse
```

### L4 — chat-wide default

```
SET:  Compute Source card "Set as default for all chat" → POST /api/chat/default {provider, model, runtime}
        (airgap-guard: refuse cloud default when airgapped, mirrors providers_active)
        → secrets.env: COMPUTE_SOURCE=<provider> (existing), ARAIL_CHAT_DEFAULT_MODEL=<json {model,runtime}>
CLEAR: POST /api/chat/default {clear:true} → remove ARAIL_CHAT_DEFAULT_MODEL (COMPUTE_SOURCE reverts to my_machine on next read)
USE:  /api/chat & /api/chat/stream
        → _apply_chat_defaults(backend_override, model_override, runtime_override)   # fills ONLY blanks
        → _run_chat_completion[_stream](...)   # per-message values already won
```

### Exact JSON payload shapes

**`GET /api/chat/models?provider=claude` — cloud success** (additive keys; legacy keys still present):
```json
{
  "provider": "claude",
  "current": "claude-opus-4-7",
  "gallery": {
    "installed": [],
    "catalog": [
      {"id": "claude-opus-4-7", "name": "claude-opus-4-7", "family": "claude",
       "installed_state": "available", "source": "cloud", "runtime": "claude",
       "ctx": 200000, "ctx_label": "200K tokens", "size_gb": null, "tier": "flagship"}
    ],
    "runtime_counts": {}
  },
  "models": ["claude-opus-4-7"],
  "airgapped": false
}
```

**`GET /api/chat/models?provider=claude` — no saved token** (CTA, never silent empty):
```json
{
  "provider": "claude",
  "current": null,
  "gallery": {"installed": [], "catalog": [], "runtime_counts": {}},
  "cta": {"kind": "no_token", "provider": "claude",
          "message": "Save a Claude (Anthropic) key in ⚙ Manage providers to see its models.",
          "docs": "https://console.anthropic.com/settings/keys"},
  "airgapped": false
}
```

**`GET /api/chat/models?provider=claude` — airgapped** (refusal, gallery shape preserved):
```json
{
  "provider": "claude",
  "current": null,
  "gallery": {"installed": [], "catalog": [], "runtime_counts": {}},
  "cta": {"kind": "airgapped",
          "message": "Lab is airgapped. Set LAB_MODE=hybrid in .env and restart to use cloud providers."},
  "airgapped": true
}
```

**`GET /api/chat/models` (no `?provider=`)** — **byte-identical to today.** Frozen by golden snapshot (see Test strategy R1). The cloud branch must be a strict `if provider and provider != "my_machine":` wrapper that the legacy code never enters.

**Curated YAML schema extension** (`models_catalog.yaml`, optional fields on existing/new rows):
```yaml
- id: claude-opus-4-7
  name: Claude Opus 4.7
  family: claude
  provider: claude          # NEW — when set, row is a cloud catalog entry for that provider
  ctx: "200K tokens"        # NEW — string; parsed by model_specs.context_tokens()
  source: cloud             # cloud rows use source:cloud (loader already accepts arbitrary source string)
  tier: flagship
  # size_gb/install omitted → default 0/"" (loader already tolerant)
```
`provider`-bearing rows are the curated fallback for providers where a live `/models` call is
absent or awkward (huggingface always; gemini/cohere by default — see L2). Rows WITHOUT a
`provider` field stay local-gallery rows (today's behavior, unchanged).

**ctx card fields** (added to each gallery card the picker renders):
```
ctx        int|null     resolved context window in tokens (override > spec > catalog > null)
ctx_label  str|null     human label ("128K tokens"); falls back to "Context: unknown"
ctx_source "override"|"spec"|"catalog"|"unknown"   provenance, for the resource-cost hint copy
ctx_settable bool       true ONLY for the selected LOCAL card (cloud/non-selected → false)
ctx_cost_hint str       e.g. "Larger context uses more memory — may risk OOM on this machine."
                        local cards reuse fit.verdict to escalate the warning; cloud cards omit
```

## Interface contracts

### Changed endpoint — `GET /api/chat/models`
- **Params:** optional `provider: str` query param.
- **Pre:** none. **Post (no provider / "my_machine"):** byte-identical legacy payload.
- **Post (cloud):** the cloud-success / no-token / airgap shapes above. Always returns a
  `gallery` key with the standard `{installed, catalog, runtime_counts}` structure so the
  frontend renderer never sees a missing field.
- **Bad input:** unknown provider → treat as cloud branch, fall through to
  `{cta:{kind:"unknown_provider"...}, gallery:{...empty}}` (never 500, never local fallthrough).
- **Airgap:** cloud branch refuses first, before any token read or network call.

### New endpoint — `POST /api/chat/models/set-ctx`
- **Body:** `{model_id: str, ctx: int}`. **Returns:** `{ok, model_id, ctx, ctx_overrides}`.
- **Validation:** ctx ∈ [256, 1_000_000] (mirror admin handler). **model_id validation: see
  F-VALIDATE — it must NOT reuse `_validate_model_id` unchanged** (that whitelists on-disk dirs
  only and would reject Ollama ids). Use a relaxed gate: non-empty, ≤256 chars, no path
  separators / `..`, AND present in the union of `_scan_local_models` ids ∪ Ollama-installed ids
  (`arail.chat.detect_installed_models`). Cloud models are rejected (ctx is display-only for cloud).
- **Side effects:** `_persist_ctx_override` writes secrets.env + os.environ; **purge
  `_RUNTIME_BACKEND_CACHE` for the model**; set `_MODELS_SCAN_TS = 0.0`.
- **Airgap:** N/A (local-only operation) — but reject any model_id that isn't a known LOCAL id.
- **Why a separate route, not exposing the admin one:** keeps the admin surface admin-gated;
  the chat route accepts the broader local-id set (Ollama). Both delegate to the shared
  `_persist_ctx_override`.

### New endpoint — `POST /api/chat/default`
- **Body:** `{provider: str, model: str, runtime: str}` to set, or `{clear: true}` to revert.
- **Returns:** `{ok, provider, model, runtime}` or `{ok, cleared:true}`.
- **Airgap:** if `provider` is a cloud provider and `_is_airgapped()` → refuse
  (`{ok:false, error:"Airgapped — cloud default blocked..."}`), mirroring `providers_active`.
- **Side effects:** writes `COMPUTE_SOURCE` (existing key) and `ARAIL_CHAT_DEFAULT_MODEL`
  (new JSON `{model,runtime}`) to secrets.env + os.environ. Never logs/echoes a token (it stores
  no token — just provider/model/runtime ids).

### New helper — `model_specs.context_tokens(label: str | int | None) -> int | None`
- Lives in `src/arail/model_specs.py` (alongside `must_stream`). `@lru_cache`.
- Parses `"128K tokens"→131072`, `"1M tokens"→1048576`, `"32k"→32768`, bare `int`/`"4096"→4096`,
  `None`/unparseable → `None`. K=1024, M=1024² (binary, matches n_ctx semantics).
- **Contract:** pure, no app.py import (model_specs must never import app.py — circular, see
  model_specs.py:312). **Companion** `context_label(model_name)`: convenience that does
  `lookup(model_name)` then returns its `context` string (or `None`).

### New helper — `_resolve_ctx_override(model_name: str, default: int | None) -> int | None`
- Lives in `src/arail/router/backends.py` (so backends can call it without importing app.py).
- Reads `ARAIL_MODEL_CTX_OVERRIDES` (JSON, env) → **substring match** model_name against keys
  (overrides are keyed by the id the user set; chat ids and load-time names may differ slightly).
  On match: clamp to [256, 1_000_000], return it. Else: try `model_specs.context_tokens(
  model_specs.context_label(model_name))`. Else: return `default`.
- **Contract:** never raises (bad JSON → ignore, fall through). Returns `None` only if `default`
  is `None` and nothing resolves. backends.py importing model_specs is allowed (one-way).

### New helper — `_fetch_provider_models(provider: str) -> list[str]`
- Lives in `src/arail/portal/app.py`, factored OUT of `providers_models` (~1313). Both
  `/api/providers/models` and the `/api/chat/models` cloud branch call it.
- **Pre:** caller has already done the airgap + token checks. **Post:** returns up to 200 model
  ids from the live `/models` endpoint, OR the curated YAML rows (`provider==<provider>`) when the
  provider has no usable `models_path` (huggingface) or is configured curated-first
  (gemini/cohere). On network/401/timeout → returns `[]` (caller renders an error/empty row).
- **Decision (live vs curated per provider):** claude, nvidia, openrouter, xai, mistral, together
  → live `/models` (well-behaved OpenAI shape). huggingface → curated (no `/models`, `models_path:""`).
  google (gemini) + cohere → **curated by default** (their `/models` shapes/aliasing are quirky;
  see F-COMPAT) with a config flag to flip to live later.

### New helper — `_persist_ctx_override(model_id: str, ctx: int) -> dict`
- Lives in `src/arail/portal/app.py`, factored OUT of `admin_models_set_ctx` (~4537-4553).
- Reads/merges/writes `ARAIL_MODEL_CTX_OVERRIDES` to secrets.env + os.environ; returns the merged
  dict. **Both** the admin handler and the new chat delegate call it (DRY — single persistence path).
- Does NOT itself purge the runtime cache (caller's responsibility, so the admin path can keep its
  existing behavior); the chat delegate adds the purge.

### New helper — `_apply_chat_defaults(backend, model, runtime) -> tuple[str|None,str|None,str|None]`
- Lives in `src/arail/portal/app.py`. Reads `COMPUTE_SOURCE` + `ARAIL_CHAT_DEFAULT_MODEL`.
- Fills ONLY arguments that are falsy/blank; returns the resolved triple. Per-message values win
  (A8). Called once at the top of `api_chat` and `api_chat_stream`, before `_run_chat_completion[_stream]`.

### New backend — `OllamaNativeBackend(OpenAICompatBackend)`
- Lives in `src/arail/router/backends.py`. Registered in `BACKEND_MAP` as `"ollama_native"`
  (additive; does not displace `openai_compat`).
- Overrides `complete` (and `stream_complete` for symmetry, though the chat path only calls
  `complete` — app.py:5107) to POST `{ollama_root}/api/chat` (note: **root**, derived by
  stripping a trailing `/v1` off `self.base_url`), body
  `{model, messages, stream:false, options:{num_ctx:<self._num_ctx>}}` — `options.num_ctx` is
  included **only when `self._num_ctx` is set** (else omitted → Ollama default, preserves today's
  behavior). Parses Ollama's response (`message.content`; NDJSON when streamed). Returns the same
  `ModelResponse(backend="ollama_native", ...)` contract.
- **Preconditions on construction via `__new__`:** caller (`_get_runtime_backend` ollama branch)
  MUST set `_session`, `base_url`, `model_name`, `api_key`, `backend_name`, AND `_num_ctx`.
  (F-NEW: `__init__` is bypassed; nothing is auto-initialized.)

## Failure modes

| # | Failure | Detection | Mitigation | Proving test |
|---|---|---|---|---|
| F-CACHE | `set-ctx` changes a model's ctx but `_RUNTIME_BACKEND_CACHE` still holds the old `OllamaNativeBackend` with stale `_num_ctx` → user sets 32K, still gets 4K | Cache is keyed `(runtime, model_id)`; entry survives the override write | `/api/chat/models/set-ctx` purges every cache entry whose `key[1]==model_id` (and ideally the `(*, model_id)` for all runtimes) | Unit: set ctx for a cached ollama model → assert cache entry gone; next `_get_runtime_backend` rebuilds with new `_num_ctx` |
| F-NEW | `_get_runtime_backend` builds via `__new__` (app.py:4827), bypassing `__init__`; a new `OllamaNativeBackend` attribute (`_num_ctx`) is therefore unset → AttributeError at request time | Any attr the override reads must be set by the builder, not `__init__` | Builder sets `_num_ctx` in the ollama branch; `complete` reads `getattr(self,"_num_ctx",None)` defensively | Unit: build via `__new__` path, call `complete` (mocked POST) → no AttributeError; num_ctx present iff set |
| F-OLLAMA-SHIM | Ollama's OpenAI `/v1` shim silently DROPS `num_ctx` → ctx slider appears to work but model still truncates at default | Sending `num_ctx` to `/v1/chat/completions` is a no-op upstream | Use the **native** `/api/chat` endpoint (root, not `/v1`) with `options.num_ctx` — the documented path | Unit: assert `OllamaNativeBackend.complete` POSTs to `…/api/chat` (NOT `/v1/...`) with `options.num_ctx` in body |
| F-COMPAT | Gemini/Cohere "OpenAI-compatible" `/models` returns a non-OpenAI shape or model ids that aren't usable in `/chat/completions` → empty or broken catalog | `_fetch_provider_models` gets a payload that doesn't match `data:[{id}]` | Default these two to **curated YAML** (`provider:` rows), live `/models` behind a flag; `_fetch_provider_models` already tolerates missing `data` (returns `[]`) | Unit: gemini/cohere → curated path returns the YAML ids; live path with junk payload → `[]` not 500 |
| F-RACE | Rapid radio flips: `loadModels("claude")` in flight when user flips to `openrouter`; claude's response lands last → dropdown shows claude while radio reads openrouter | Two overlapping fetches, later-issued may resolve first | Frontend seq-guard: increment a module `loadSeq`, capture it per call, ignore any response whose captured seq ≠ current `loadSeq`. Also re-read `selectedProvider()` before painting | Integration (mocked fetch w/ delays): flip A→B, A resolves last → assert grid shows B's models |
| F-AIRGAP | A cloud provider leaks through `/api/chat/models`, `/api/chat/default`, or `/api/chat/models/set-ctx` when `LAB_MODE=airgapped` | Endpoint does network/token work before checking `_is_airgapped()` | Airgap check is the FIRST branch in each cloud-touching path; set-ctx rejects non-local ids entirely | Regression (parametrized over ALL 10 cloud providers): airgapped → `/api/chat/models?provider=<p>` returns `airgapped:true` + empty gallery, no outbound request (assert `requests.get` not called) |
| F-OOM | User sets a huge ctx (e.g. 1M) on a local model → llama.cpp/Ollama allocates a giant KV cache → OOM (MEMORY: machine has OOMed before) | ctx is settable up to 1M; large ctx × model = large KV | UI ctx control shows `ctx_cost_hint` and escalates using existing `fit.verdict`; copy says "may risk OOM on this machine"; clamp stays 256..1M; **no auto-apply** — takes effect on restart/reload so the user is warned first | Unit: card payload for a local model includes `ctx_cost_hint`; a model whose `fit.verdict` is tight escalates the hint wording |
| F-CLOUD-CURRENT | Cloud branch leaves `current` pointing at a LOCAL model (app.py:5795 always resolves a local id) → dropdown pre-selects a local model under a cloud provider — the exact bug we're fixing | `current` is computed from the local backend before the branch | In the cloud branch, override `current` to the first cloud model id (or echo the client's selection); never let the local `current` survive into a cloud response | Unit: `?provider=claude` with token → `current` is a claude model id (or null), never `qwen2.5:7b` |
| F-CATALOG | New `provider:`/`ctx:` YAML fields are parsed by `load_catalog` but dropped by `CatalogEntry.as_dict()` (chat/__init__.py:40 emits only known fields) → cloud rows never reach the gallery | as_dict omits unknown fields | Extend `CatalogEntry` with optional `provider`/`ctx` fields and emit them in `as_dict`; keep them optional w/ defaults so legacy rows (no fields) still load | Regression: load a legacy-only catalog (no new fields) → all entries load, `provider`/`ctx` default to None/"" ; load a catalog WITH fields → they survive `as_dict` |
| F-MUSTSTREAM | New ctx parser tempts a refactor of the `must_stream` inline-regex duplication (model_specs.py:326) → if "fixed" by importing app.py, introduces the circular import the comment warns about | A new import of app.py from model_specs | Do NOT touch the duplication this sprint; `context_tokens` is a *separate* parser (ctx label → int), unrelated to the param-count regex. Leave the documented debt as-is | Regression: `must_stream` behavior unchanged (existing `test_must_stream_rule.py` still green); no new import of app.py in model_specs (grep test) |
| F-VALIDATE | Chat `set-ctx` reuses `_validate_model_id` → rejects every Ollama model (whitelist is on-disk dirs only, app.py:4276) → ctx control silently fails for the most common local runtime | `_validate_model_id` calls `_scan_local_models` (dirs only) | Chat delegate uses a relaxed local-id gate (on-disk ids ∪ Ollama-installed ids); admin route keeps strict `_validate_model_id` | Unit: chat `set-ctx` with an Ollama id (mocked `detect_installed_models`) → accepted; with a cloud id → rejected; with `../etc` → rejected |
| F-DEFAULT-LEAK | L4 default persists a cloud provider while airgapped (e.g. set in hybrid, then `.env` flipped to airgapped) → `_apply_chat_defaults` routes chat to a blocked cloud provider | Stored default read without re-checking lab mode at use time | `_apply_chat_defaults` (or the downstream guard) drops a cloud default when `_is_airgapped()` and falls back to my_machine; `/api/chat/default` refuses to SET a cloud default while airgapped | Unit: store cloud default in hybrid; flip airgapped; `_apply_chat_defaults` → resolves to my_machine, not the cloud provider |
| F-PROVIDER-DRIFT | New providers added to `_PROVIDER_KEY_ENVS`/`_PROVIDER_META` but frontend `PROVIDER_META`/`CLOUD`/radios not updated (or vice-versa) → modal/picker out of sync | Two parallel lists (server + JS) | Add all five to BOTH; the airgap-parametrized regression iterates `_CLOUD_PROVIDERS` so a missing server entry fails a test; a DOM test asserts a radio exists per provider | Regression: count of `compute-source` radios == len(server providers)+1(my_machine); each cloud provider has a `PROVIDER_META` JS entry |

## Test strategy

**Unit (model_specs / backends):**
- `context_tokens`: "128K tokens"→131072, "1M tokens"→1048576, "32k"→32768, "4096"/4096→4096,
  "", None, "banana"→None. (K=1024, M=1024².)
- `_resolve_ctx_override`: override hit (substring, clamped), override miss → spec fallback,
  both miss → default; bad JSON env → default (no raise); clamp <256 and >1_000_000.
- `OllamaNativeBackend.complete` (mocked `requests`): POSTs to `…/api/chat` (not `/v1`),
  `options.num_ctx` present iff `_num_ctx` set, parses `message.content`, returns
  `ModelResponse(backend="ollama_native")`. (F-OLLAMA-SHIM, F-NEW.)

**Unit (app.py endpoints, FastAPI TestClient + monkeypatched network):**
- `/api/chat/models?provider=claude`: token+hybrid → cloud gallery, `current` is a cloud id
  (F-CLOUD-CURRENT); no token → `cta.kind=="no_token"` + docs link; airgapped → `airgapped:true`
  (F-AIRGAP); unknown provider → `cta.kind=="unknown_provider"`, never 500.
- `/api/chat/models/set-ctx`: Ollama id accepted (F-VALIDATE), cloud id rejected, traversal
  rejected, ctx out of range rejected; on success cache purged (F-CACHE), `_MODELS_SCAN_TS==0.0`.
- `/api/chat/default`: set local default ok; set cloud default while airgapped → refused
  (F-DEFAULT-LEAK); `{clear:true}` removes `ARAIL_CHAT_DEFAULT_MODEL`.
- `_apply_chat_defaults`: per-message wins; blanks filled from store; airgapped drops cloud default.

**Integration:**
- Frontend race (jsdom or a focused JS test): `loadModels` seq-guard — flip A→B with A resolving
  last → grid renders B (F-RACE).
- Radio change → `setActiveProvider` then `loadModels(provider)` → grid repopulates; loading state
  shown during fetch (first-paint rule); error fetch → labeled error row, not silent empty.

**Regression (the load-bearing ones):**
- **R1 — golden snapshot:** `GET /api/chat/models` with NO `?provider=` returns a payload
  byte-identical to a captured baseline (snapshot the dict keys + structure; mock the local
  gallery deterministically). Any drift fails. This is the single most important test in the sprint.
- **R2 — backend body unchanged:** with NO ctx override set, `CPUBackend` builds `n_ctx=4096`
  and `OpenAICompatBackend.complete`/`stream_complete` produce request bodies identical to today
  (no `num_ctx`, no new keys). Capture-and-compare the JSON payload.
- **R3 — airgap parametrized over all 10 cloud providers:** for each in `_CLOUD_PROVIDERS`,
  airgapped `/api/chat/models?provider=<p>`, `/api/chat/default {provider:<p>}` →
  refused/airgapped, and assert no outbound `requests.get`/`requests.post` was made.
- **R4 — catalog back-compat:** legacy YAML (no `provider`/`ctx`) loads unchanged through
  `load_catalog`/`as_dict` (F-CATALOG); existing `test_chat_model_sync.py` stays green.
- **R5 — must_stream untouched:** `test_must_stream_rule.py` green; grep-test that `model_specs`
  imports nothing from `arail.portal` (F-MUSTSTREAM).

**Security (ARAIL gating — runs on others' machines):**
- No endpoint response contains a token value (assert secrets never echoed) — extend the existing
  airgap/secret-hygiene suites (`test_qa_security_hygiene_paranoid.py`,
  `test_qa_airgap_bypass_attempts.py`).
- set-ctx model_id path-traversal attempts (`../`, abs paths, separators) rejected (F-VALIDATE).
- Airgap bypass attempts on all three new/changed cloud paths (covered by R3, plus a paranoid
  variant that tries header/case tricks on the provider param).

**Performance:** VISION win-condition is p95 < 800ms on picker repopulate. Not a hot inner loop;
no benchmark gate required, but `_fetch_provider_models` keeps the 200-cap and the existing
timeouts (8–12s) and must not block the event loop (it's sync `requests` inside an async route —
acceptable as today, but the cloud branch should mirror the existing pattern; if it becomes a
problem, wrap in `to_thread` — note for builder, not a blocker).

## Tech debt

**Added:**
- A third "ctx persistence caller" surface (admin + chat) — mitigated by factoring
  `_persist_ctx_override` so there's still ONE write path; the two routes differ only in
  validation. Net new debt is the dual validation gate (strict admin vs relaxed chat).
- A new backend class (`OllamaNativeBackend`) that partially duplicates `OpenAICompatBackend`'s
  request plumbing (different endpoint + body). Acceptable: the OpenAI shim genuinely can't carry
  `num_ctx` (F-OLLAMA-SHIM), so a distinct backend is the correct abstraction, not duplication.
- Two parallel provider lists (server `_PROVIDER_META` + JS `PROVIDER_META`) grow from 5→10
  entries each. Pre-existing pattern; the parametrized tests (F-PROVIDER-DRIFT) pin them together.
- Curated cloud-model rows in `models_catalog.yaml` (HF + gemini/cohere) are a maintenance surface
  (VISION risk 1). Mitigated: updates are a single YAML edit, no code change. VISION disconfirming
  evidence (c) (>2 maintenance issues in 30 days) is the trigger to pivot to live-only.

**Repaid:**
- `ARAIL_MODEL_CTX_OVERRIDES` was dead weight — written by admin, read by the scan, but **never
  consumed by inference**. L3 finally wires it into `n_ctx`/`num_ctx`, closing a latent
  "setting does nothing" trap.
- The dropdown's silent-wrong cloud behavior (the core VISION bug) is removed.

**Net:** roughly neutral. The biggest single risk is the regression surface around the legacy
`/api/chat/models` branch and the `complete()` bodies — both pinned by golden-snapshot tests
(R1/R2) so the debt is *fenced*, not floating. No follow-up ticket required beyond the standing
VISION disconfirming-evidence triggers (HF curated staleness, OpenRouter list usability).

## Recommended implementation order

**Phase A — registry + parser (no behavior change to inference):**
1. Add the five providers to `_PROVIDER_KEY_ENVS` + `_PROVIDER_META`; add JS `PROVIDER_META`/`CLOUD`
   entries + five radios in `chat.legacy.html`. (L2)
2. `model_specs.context_tokens` / `context_label` + unit tests.
3. Extend `CatalogEntry` (+`as_dict`) and YAML schema with optional `provider`/`ctx`; back-compat
   test R4. (Unblocks curated cloud rows.)

**Phase B — ctx into inference (load-time):**
4. `_resolve_ctx_override` in backends.py; wire into `CPUBackend.__init__` (`n_ctx`). R2 first to
   freeze the no-override baseline, THEN the wiring.
5. `OllamaNativeBackend` + register in `BACKEND_MAP`; build it from `_get_runtime_backend`'s
   ollama branch with `_num_ctx` resolved in the branch (F-NEW).
6. Factor `_persist_ctx_override` out of the admin handler (admin path stays green).

**Phase C — endpoints:**
7. `_fetch_provider_models` factored out of `providers_models`; both endpoints share it.
8. `/api/chat/models` cloud branch (airgap → no-token → cloud gallery; override `current`).
   R1 golden snapshot of the legacy branch BEFORE writing the cloud branch.
9. `POST /api/chat/models/set-ctx` (relaxed validation, cache purge). (L3 set path)
10. `POST /api/chat/default` + `_apply_chat_defaults`, wired into `api_chat`/`api_chat_stream`. (L4)

**Phase D — frontend:**
11. `loadModels(provider)` with seq-guard (F-RACE); loading/CTA/airgap/error render states.
12. Radio change → `setActiveProvider()` then `loadModels(provider)`.
13. ctx card fields + inline set control on the selected local card (cloud display-only); OOM hint.
14. L4 "Set as default for all chat" control + status line + "Reset to per-message" link.

R3 (airgap parametrized) and the security suite extensions run continuously from Phase C onward.

## Open questions for the builder

1. **ctx override key matching.** Overrides are keyed by the id the user set in the UI; the
   load-time `model_name` (e.g. CPUBackend's basename of a `.gguf`, or an Ollama tag) may differ.
   `_resolve_ctx_override` uses substring match — if that proves too loose/tight in practice,
   prefer an exact-then-substring fallback. Not a blocker; flag in BUILD_LOG if you change it.
2. **`current` for a cloud provider with no obvious default.** The design echoes the client's
   selection or picks the first cloud model. If the client sends no selection and the provider's
   `/models` is empty (e.g. token valid but list 403'd), `current` is `null` and the picker shows
   the CTA/empty — confirm that reads acceptably vs. a "couldn't list models" labeled row.
3. **OpenRouter 200-cap UX.** Out of scope to add search, but if the unsorted 200 reads badly,
   note it for the VISION disconfirming-evidence (b) follow-up rather than expanding scope here.

---

## Verdict: PROCEED to build.

The recommended design is sound and I adopt it, with five corrections/sharpenings the builder
MUST honor (each has a failure-mode row and a test): (F-VALIDATE) the chat `set-ctx` route must
NOT reuse `_validate_model_id` — it would reject every Ollama model; use a relaxed local-id gate.
(F-CATALOG) extend `CatalogEntry.as_dict` or the new YAML fields silently vanish. (F-CLOUD-CURRENT)
override `current` in the cloud branch — the local `current` at app.py:5795 is exactly the stale
selection we're fixing. (F-CACHE) purge `_RUNTIME_BACKEND_CACHE` on set-ctx. (F-DEFAULT-LEAK)
re-check airgap at default *use* time, not just at set time. The load-bearing protections —
golden snapshot of the legacy `/api/chat/models` branch (R1), unchanged `complete()` bodies (R2),
and airgap refusal parametrized over all 10 cloud providers (R3) — are specified and gate the ship.
