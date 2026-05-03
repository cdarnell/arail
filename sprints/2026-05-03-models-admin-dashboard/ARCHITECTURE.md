# Architecture: Models Admin + Hard 35B Rule + Dashboard Reorg

**Date:** 2026-05-03
**Sprint:** [2026-05-03-models-admin-dashboard](./SPRINT.md)
**Branch:** `qukaizen/arail-models-admin-dashboard` off `main` (HEAD `1b4ec61`, post-PR-#28-merge AND post-PR-#29-merge — see Cross-sprint coordination below)

---

## Restatement

Five coupled deliverables that close the local-model story before
the broader product release. (1) Cap dispatched local models at 35B
total params with a server-side hard rule that silently routes
above-threshold models to the AirLLM streaming backend, regardless of
what the chat UI selected. (2) Add a metadata override layer in
`model_specs.py` so MoE / multi-segment names like
`Llama-4-Maverick-17B-128E-Instruct-fp8` get the right total-params
count (~400B) instead of being misread as 17B (active) by the existing
regex. (3) Add an Admin "Models" section that follows the Production
Readiness recipe and exposes load / unload / set-default / set-ctx
controls plus a duplicate of the chat picker. (4) Promote the Mission
card to its own full-width row with a horizontal nav strip below the
title. (5) Pair Mission Status and Activity Feed as a symmetric
2-column row of equal height. None of this breaks the airgapped
default, none touches the rebrand surface, none adds a new dependency.

---

## Line-reference verification (post-PR-#28 + PR-#29 merge)

The sprint ledger's line refs were captured before the prod-readiness
sprint shipped. All numbers below are verified against the current
working tree (HEAD `1b4ec61a`). All line numbers in the rest of this
document are post-merge.

| Sprint claim | Actual location | Notes |
|---|---|---|
| `_extract_param_hint()` @ app.py:4813–4857 | **app.py:4813–4819** (function body 7 lines, not 45) | Function is small. Sprint claim conflated `_extract_param_hint` + `_model_param_hint_value` + `_estimate_model_memory_gb` into one range. |
| `_model_param_hint_value()` (returns `float \| None` in raw param count, e.g. `70_000_000_000`) | **app.py:4845–4857** | Multiplies the hint by the appropriate `K/M/B` scale and returns absolute params (NOT in billions). Important for the 35B rule: the threshold must be expressed as `35 * 1_000_000_000`. |
| `_estimate_model_memory_gb()` | **app.py:4860–4882** | Calls `_model_param_hint_value` internally. |
| `_prepare_chat_context()` `wants_deep` decision | **app.py:3681** | Verified — this is exactly the dispatch fork point. The 35B override slots in here, immediately after the line that computes `wants_deep` from the user-selected backend. |
| `_run_chat_completion()` deep-backend branch | **app.py:3991–3997** | Verified. |
| The default-path `inference_slot` wrap (sixth wrap from prior sprint) | **app.py:4041–4048** (was `app.py:3532` pre-prod-readiness; now sits at `4041` after the wrap was added) | The Llama-4 dispatch piggybacks on the existing wrap structure — no new slot label needed for >35B routing because we mutate `wants_deep` upstream. |
| `_local_memory_snapshot()` (GPU/VRAM probe; "Requires streaming" verdict) | **app.py:4914–4973** (claimed 4914–4962 — body grew slightly) | Verdict label is computed by `_fit_verdict_label()` at **app.py:4885–4892** based on `required_gb` vs `available_gb`. The string "Requires streaming" is advisory only today; the 35B rule promotes that signal into a hard route. |
| `/api/chat/models` endpoint | **app.py:4486** | Verified. The Admin Models section reuses this same data source plus a new `/api/admin/models/scan` for filesystem-only listing. |
| Chat page model picker HTML / JS | **chat.html:1439** (`<div id="model-picker" hidden>`) + JS init at **chat.html:3167–3232** + `renderPicker` at **chat.html:1951–2006** | Sprint claimed picker HTML at chat.html:744–827 and JS at 3167–3200; **HTML lines are wrong** (744–827 is `.picker-pop` CSS only). Real picker HTML is one line at **1439** with the JS-driven body in `renderPicker` at 1951. JS init range is approximately right (3167–3232, not 3167–3200 — the deep-entry projection extends through 3209). |
| Production Readiness admin section | **admin.html:595–612** (claimed 596–612 — off-by-one on opening comment) | Verified shipped from prior sprint. |
| Production Readiness JS driver | **admin.html:904–1058** | Verified. The new Admin Models JS appends after this block. |
| Mission card | **dashboard.html:354–517** with the cramped h2 at **dashboard.html:355–363** (3-element h2: indicator + Mission + Curated view → + Mission docs ↗) | Verified. The Mission card already has `class="card mission-card"` and `id="goal-card"`. Reorg promotes it to `class="card full mission-card"` and lifts the two `.card-title-link` anchors out of the `<h2>` into a sibling nav strip. |
| Mission Status card | **dashboard.html:521–563** (claimed 521–563) | Verified. |
| Activity Feed card | **dashboard.html:565–580** | Verified. |
| Research Report row | **dashboard.html:582–589** (`<div class="card full">` already) | **Verified — already a `card full` row on this branch** because PR #29 merged into main as commit `1b4ec61` (the merge commit IS HEAD). No work needed for Research Report this sprint. See Cross-sprint coordination below. |
| `_OPTIONAL_CHAT_BACKEND_CONFIG` | **app.py:4233–4250** | Used by `wants_deep` check. AirLLM = `model_env: AIRLLM_MODEL`. The 35B override forces `optional_backend_name="airllm"` so this config is consulted. |
| `onboarding_gate` middleware allowlist | **app.py:158–168** | Five `/api/admin/models/*` endpoints below are NOT added to the allowlist — they remain gated like every other `/api/admin/*`. |

---

## Cross-sprint coordination

**Decision: (A) — design assuming PR #29 has merged.**

`git log --oneline qukaizen/knowledge-ux-quirky-whisper..main` returns
empty, and `git log --oneline main..qukaizen/knowledge-ux-quirky-whisper`
also returns empty. Working tree HEAD is `1b4ec61a` which is the merge
commit "Merge pull request #29 from cdarnell/qukaizen/knowledge-ux-quirky-whisper".
The Research Report row is already promoted to `<div class="card full">`
at dashboard.html:582–589 in the current branch baseline, so deliverable
5's "paired Status/Feed row" can be designed against the post-#29
dashboard structure with no further coordination.

The merge sequence on main was:
1. PR #28 (prod-readiness wrappers) — merged at `5fd9158`
2. PR #29 (kb CLI + terminal/dashboard polish) — merged at `1b4ec61`

This sprint branches off `1b4ec61`. **No work needed for the Research
Report row.** The dashboard currently has this card sequence:

```
<div class="grid">
  Quick Actions     [card full]   line 309
  Service Status    [card full]   line 335
  Lab Shortcuts     [card full]   line 341
  Mission           [card mission-card]  line 355   ← promote to [card full mission-card] + lift links
  Mission Status    [card]        line 522          ← keep [card] (left half of paired row)
  Activity Feed     [card]        line 566          ← keep [card] (right half of paired row)
  Research Report   [card full]   line 585          ← already promoted by PR #29 — DO NOT TOUCH
  Knowledge Base    [card full kb-hero]  line 594
  ...
```

---

## Assumptions

1. **Hardware floor is 5090 24GB / M5 36GB.** Anything above ~30 GB
   model footprint (≈35B params at 4-bit + KV cache + runtime) will
   not fit in GPU memory on either floor configuration. The 35B
   threshold is conservative; the user has locked it.
2. **35B = TOTAL params, not active per token** (locked decision in
   SPRINT.md). AirLLM streams full weights from disk regardless of
   MoE active count, so the relevant constraint is total disk-staged
   parameter count, not active. Llama-4-Maverick has 17B active per
   token but ~400B total → must stream.
3. **Silent override is correct UX.** No modal, no greyout — when the
   user selects a >35B model the dispatch silently routes through
   AirLLM (Deep) and the picker shows a "streamed" badge. Locked.
4. **The default backend label `chat-default` from the prior sprint
   is the correct slot to keep.** When 35B routing kicks in we set
   `wants_deep=True` upstream, which causes the dispatch to land in
   the `chat-deep` branch (app.py:3993) — already wrapped with
   `scheduler.inference_slot("chat-deep")`. No new slot label needed.
5. **AirLLM is OPTIONAL (max-tier extra).** When a >35B model is
   selected on a min-tier install, the override path will fail at
   `_get_optional_chat_backend("airllm")` with a clean error result
   from `_optional_backend_error_result()` (existing). Picker must
   surface this state — see Failure mode A3.
6. **`model_specs.py` is the right home for the metadata override.**
   The file already exists, has a registry pattern, and `_extract_param_hint`
   already imports `re` lazily — the override layer reuses both shapes.
   Future migration to YAML/JSON is filed as tech debt, not now.
7. **The chat picker reads `/api/chat/models` once at init** (chat.html:3167)
   and doesn't refresh. The new `streamed: bool` field per model is
   set server-side; the picker JS reads it on the same fetch. No new
   endpoint. (This is the simpler path of the two options the planning
   doc raises.)
8. **Admin Models load/unload acquires `inference_slot("admin-model-load")`**
   to serialize against the chat queue. Loading a heavy model into
   memory is itself an inference-class operation (model warmup runs
   on the GPU). This prevents the failure mode where a user clicks
   "Load Llama-4" while a chat stream is in flight and both fight for
   VRAM. New slot label, same semaphore, same capacity.
9. **Default GPU model and per-model CTX persist to `lab/data/secrets.env`**
   (chmod 0600, git-ignored, mode-locked) using the existing
   `_write_secrets()` helper at app.py:883. Two new keys:
   `ARAIL_DEFAULT_GPU_MODEL` and `ARAIL_MODEL_CTX_OVERRIDES` (JSON-encoded
   `{model_id: ctx_int}`). Survives restart. Mirroring the existing
   secrets pattern is cheaper than inventing a new state file.
10. **Symlinks under `lab/models/` are followed for listing but not
    resolved for path-traversal.** `Path.resolve(strict=False)` is
    used to verify containment under the real models dir, but the
    listing iterates `models_dir.iterdir()` which already returns
    symlinks. The Llama-4 symlink target lives in
    `~/.llama/checkpoints/` — outside the lab tree but pointed at
    intentionally; the listing must not reject it.
11. **`lab/models/airllm_cache` is a runtime-managed cache directory.**
    Existing chat-models scan at app.py:4555–4569 already filters out
    `_cache` suffixes. The new admin scan reuses the same filter
    predicate.
12. **`MODEL_BACKEND` env var is the runtime backend selector** (mlx /
    cuda / cpu / airllm / openai_compat). Setting `ARAIL_DEFAULT_GPU_MODEL`
    only affects which on-disk model is chosen as the default for the
    runtime backend — it does NOT switch backends. Switching backends
    still requires `MODEL_BACKEND` change + restart.

---

## Data flow

### Deliverable 1: Hard 35B-total-params rule

```
                         CLIENT                                      SERVER
       ┌───────────────────────────────────┐
       │ User picks model "Llama-4-...fp8" │
       │ + (optional) backend "mlx"        │
       └───────────────────────────────────┘
                       ↓ POST /api/chat
                       ↓   { backend: "mlx", model: "Llama-4-...fp8", ... }
                       ↓
       ┌─────────────────────────────────────────────────────────────────┐
       │ api_chat → _run_chat_completion → _prepare_chat_context (3665)  │
       │                                                                 │
       │   line 3680: optional_backend_name = "mlx" or None              │
       │   line 3681: wants_deep = optional_backend_name in              │
       │                           _OPTIONAL_CHAT_BACKEND_CONFIG         │
       │                                                                 │
       │   ── INSERT 35B OVERRIDE HERE (NEW) ──                          │
       │   if not wants_deep:                                            │
       │       effective_model = (model_override or                      │
       │                          _current_runtime_model())              │
       │       if model_specs.must_stream(effective_model):              │
       │           wants_deep = True                                     │
       │           optional_backend_name = "airllm"                      │
       │           activity_log.emit("chat",                             │
       │               f"35B+ model {effective_model}: forcing Deep "    │
       │               "(streamed) backend per hardware floor.",         │
       │               "info")                                           │
       │   ── END INSERT ──                                              │
       │                                                                 │
       │   line 3683: if wants_deep:                                     │
       │       deep_backend = _get_optional_chat_backend("airllm")       │
       │       └── may raise if AirLLM not installed (min tier);         │
       │           caught at 3687 → returns clean error_result via       │
       │           _optional_backend_error_result()                      │
       └─────────────────────────────────────────────────────────────────┘
                       ↓
       ┌─────────────────────────────────────────────────────────────────┐
       │ _run_chat_completion (3954) sees deep_backend != None           │
       │   line 3991: if deep_backend is not None:                       │
       │     async with scheduler.inference_slot("chat-deep"):           │
       │         response = await asyncio.to_thread(                     │
       │             deep_backend.complete, ...)                         │
       └─────────────────────────────────────────────────────────────────┘
                       ↓
                   Streamed response back to client
```

The check is **ONE place** — `_prepare_chat_context` (called by both
`_run_chat_completion` and `_run_chat_completion_stream`). Both
streaming and non-streaming paths inherit it for free. There is **no
client-side check** at all; the chat picker badges are advisory and the
client is free to lie about its selection — the server still routes.

### Deliverable 2: Llama-4 metadata override

```
   model_specs.py
   ──────────────
   MODEL_METADATA_OVERRIDES = [
       (re.compile(r"Llama-4.*Maverick.*17B.*128E", re.I), {
           "total_params_b": 400.0,
           "active_params_b": 17.0,
           "license": "Llama Community",
           "context": "1M tokens",
           "moe": True,
           "experts": 128,
           "notes": "MoE — 17B active per token, ~400B total. "
                    "Streams via AirLLM (max tier).",
       }),
       (re.compile(r"Llama-4.*Behemoth.*288B", re.I), {
           "total_params_b": 2000.0,  # ~2T total est
           "active_params_b": 288.0,
           ...
       }),
       # NOTE: order = most-specific first. Generic "Llama-4" pattern
       # would shadow specific variants; we don't ship a generic.
   ]

   def get_total_params(model_name: str) -> float | None:
       """Return TOTAL params in billions, or None if unknown."""
       if not model_name:
           return None
       for pat, meta in MODEL_METADATA_OVERRIDES:
           if pat.search(model_name):
               return float(meta.get("total_params_b") or 0) or None
       return None  # caller falls back to _extract_param_hint regex

   def must_stream(model_name: str) -> bool:
       """True iff total params > 35B. Single source of truth."""
       total_b = get_total_params(model_name)
       if total_b is None:
           # Override unknown — fall back to the existing regex
           # via the portal (which knows about _model_param_hint_value).
           # Returning False here means callers MUST OR-combine with
           # the regex result. See _model_param_hint_value usage in
           # app.py for the full check path.
           return False
       return total_b > 35.0
```

```
   app.py
   ──────
   _extract_param_hint(model_name) flow:
       1. Check MODEL_METADATA_OVERRIDES via model_specs.get_total_params
       2. If hit → return formatted "400B" / "2T"
       3. Else → run existing regex r"(\d+(?:\.\d+)?)([BMK])\b"
       4. Else → return ""

   _model_param_hint_value(model_name) flow (NEW: O(1) cached lookup):
       1. Check model_specs.get_total_params first → if hit, return
          total_b * 1e9
       2. Else → existing path via _extract_param_hint regex

   /api/chat/models payload (line 4486):
       For each model in gallery + optional_backends:
           entry["streamed"] = model_specs.must_stream(entry["model"])
                               or _model_param_hint_value(entry["model"])
                                  > 35e9

   Picker JS (chat.html:1930-1946):
       if (m.streamed) badges += '<span class="streamed-badge">streamed</span>';
```

### Deliverable 3: Admin Models section — endpoint + UI flow

```
                      CLIENT                                SERVER
   ┌──────────────────────────────────────┐
   │ /admin loads admin.html              │
   │ DOMContentLoaded → loadModels()      │  NEW driver
   └──────────────────────────────────────┘
                  ↓ GET /api/admin/models/scan
   ┌──────────────────────────────────────────────────────────────────┐
   │ scan handler:                                                    │
   │   1. List lab/models/* (filter out _cache, hidden, files)        │
   │   2. For each entry: stat size, detect runtime, compute total_b  │
   │      via model_specs.get_total_params || _model_param_hint_value │
   │   3. Cross-reference with /api/chat/models payload (deep_info,   │
   │      optional_backends) for "loaded?" state                      │
   │   4. Read ARAIL_DEFAULT_GPU_MODEL, ARAIL_MODEL_CTX_OVERRIDES     │
   │      from os.getenv (which dotenv populates from secrets.env)    │
   │   5. Read _local_memory_snapshot() for the available_gb hint     │
   │   6. Return { models: [...], default_gpu_model: str|null,        │
   │              snapshot: {...}, ctx_overrides: {...} }             │
   └──────────────────────────────────────────────────────────────────┘
                  ↓
              Card renders:
                ┌──────────────────────────────────────┐
                │ Models                               │
                │   default GPU model: [Qwen3-8B-4bit▼]│
                │                                      │
                │   ◉ Llama-4-Maverick-17B-128E-fp8    │
                │       streamed · 400B · 200 GB       │
                │       [Load] [Unload] [Set CTX 1024▼]│
                │   ○ Qwen3-8B-4bit                    │
                │       8B · 4.5 GB                    │
                │       [Load] [Unload] [Set CTX 4096] │
                └──────────────────────────────────────┘

   User clicks [Load]:
                  ↓ POST /api/admin/models/load { model_id }
   ┌──────────────────────────────────────────────────────────────────┐
   │ load handler:                                                    │
   │   1. Validate model_id: must be a key in scan results            │
   │      (path containment via Path(MODELS_DIR/model_id).resolve()   │
   │      → check parent == MODELS_DIR.resolve())                     │
   │   2. Acquire single-flight _MODEL_LOAD_LOCK                      │
   │   3. async with scheduler.inference_slot("admin-model-load"):    │
   │      a. If model_specs.must_stream(model_id) →                   │
   │         await asyncio.to_thread(_get_optional_chat_backend,      │
   │                                 "airllm")                        │
   │         (AirLLM streams; "load" = warm the wrapper class)        │
   │      b. Else → call existing _prepare_chat_model_load(           │
   │             model=model_id, runtime=detected_runtime,            │
   │             provider=None) (chat-load reuse)                     │
   │   4. Return { ok, status, model, loaded_at }                     │
   └──────────────────────────────────────────────────────────────────┘
```

### Deliverables 4 + 5: Dashboard reorg

**Before (current):**
```
<div class="grid">
  ...
  <div class="card mission-card" id="goal-card">    [1 col, 354–517]
    <h2>
      <span class="indicator"></span> Mission
      <a class="card-title-link" href="/mission">Curated view →</a>
      <a class="card-title-link" href="/docs/missions.md">Mission docs ↗</a>
    </h2>
    ...
  </div>
  <div class="card">                                 [1 col, 522–563]
    <h2><span class="indicator"></span> Mission Status</h2>...
  </div>
  <div class="card">                                 [1 col, 566–580]
    <h2><span class="indicator"></span> Activity Feed</h2>...
  </div>
  ...
</div>
```

**After:**
```
<div class="grid">
  ...
  <div class="card full mission-card" id="goal-card">    [2 col span, full row]
    <h2>
      <span class="indicator"></span> Mission
    </h2>
    <div class="mission-nav-strip">
      {% if current_goal %}<a class="mission-nav-link" href="/mission">Curated view →</a>{% endif %}
      <a class="mission-nav-link" href="/docs/missions.md"
         title="What is a mission? What does Draft Swarm Plan actually do?">Mission docs ↗</a>
    </div>
    ...  (unchanged body)
  </div>
  <div class="card">                                 [1 col, paired]
    <h2><span class="indicator"></span> Mission Status</h2>...
  </div>
  <div class="card">                                 [1 col, paired]
    <h2><span class="indicator"></span> Activity Feed</h2>...
  </div>
  ...
</div>
```

CSS additions (style.css, near the existing `.mission-card` block at
~line 2292 area):
```
.mission-nav-strip {
  display: flex;
  gap: 0.85rem;
  align-items: center;
  margin: -0.4rem 0 0.85rem 0;   /* tuck under h2 */
  padding-bottom: 0.6rem;
  border-bottom: 1px solid var(--border);
}
.mission-nav-link {
  font-size: 0.78rem;
  color: var(--green);
  text-decoration: none;
  padding: 0.2rem 0.5rem;
  border: 1px solid var(--border);
  border-radius: 4px;
  background: var(--surface);
  transition: border-color 0.15s, color 0.15s;
}
.mission-nav-link:hover { border-color: var(--green); color: var(--green-hi, var(--green)); }
```

The paired row works for free: `Mission Status` + `Activity Feed`
both stay `class="card"` (no `full`) which means they each occupy
one column in the existing 2-col `.grid` (style.css:463–470).
At ≤900px the existing `@media (max-width: 900px) { .grid {
grid-template-columns: 1fr; } }` (style.css:1074–1078) collapses
both to stacked. **Equal height** is achieved by the existing CSS
grid behavior — sibling cards in the same row are stretched to
match. Verify in QA across viewports.

---

## Interface contracts

### `src/arail/model_specs.py` (extension)

```python
# Module top — alongside _SPECS:

import re as _re
from functools import lru_cache

# Manual overrides for models whose name doesn't expose total params.
# Order = most-specific first; first regex match wins.
# total_params_b is in BILLIONS (so 400.0 = 400B).
MODEL_METADATA_OVERRIDES: list[tuple["_re.Pattern[str]", Dict[str, Any]]] = [
    (_re.compile(r"Llama-4.*Maverick.*17B.*128E", _re.IGNORECASE), {
        "total_params_b": 400.0,
        "active_params_b": 17.0,
        "moe": True,
        "experts": 128,
        "license": "Llama Community",
        "context": "1M tokens",
        "notes": (
            "Llama-4 Maverick: 128-expert MoE, 17B active per token, "
            "~400B total. Streams via AirLLM (max tier)."
        ),
        "source": "https://huggingface.co/meta-llama/Llama-4-Maverick-17B-128E-Instruct",
    }),
    # Also match the symlink/local-folder variant (no fp8 suffix, etc.)
    # via the same regex above — `Llama-4.*Maverick.*17B.*128E` is broad
    # enough to cover both `meta-llama/Llama-4-Maverick-17B-128E-Instruct`
    # AND `Llama-4-Maverick-17B-128E-Instruct-fp8`.
]

@lru_cache(maxsize=512)
def get_total_params(model_name: str) -> Optional[float]:
    """Return TOTAL params in billions, or None if unknown.

    Postcondition: result is cached per process. Cache eviction is
    LRU at 512 entries — far above the realistic model-name cardinality.
    Bad input: empty / None → returns None.
    """
    if not model_name:
        return None
    for pat, meta in MODEL_METADATA_OVERRIDES:
        if pat.search(model_name):
            value = meta.get("total_params_b")
            if isinstance(value, (int, float)) and value > 0:
                return float(value)
    return None

# Hardware floor for ARAIL deployment — TOTAL parameter cap for in-GPU
# residency. Anything above must stream via AirLLM. Locked decision.
HARDWARE_FLOOR_TOTAL_B = 35.0

@lru_cache(maxsize=512)
def must_stream(model_name: str) -> bool:
    """True iff TOTAL params > HARDWARE_FLOOR_TOTAL_B (35B).

    Single source of truth for the hard hardware-floor rule. Both
    server-side dispatch and the chat-picker streamed-badge must
    consult this function — never re-derive the threshold.

    Postcondition: O(1) per call after first lookup (lru_cache).
    Bad input: empty / None / unparseable → False (treat as small;
    safer default — a small model dispatched to streaming is just
    slow; a large model dispatched to local is OOM).
    """
    if not model_name:
        return False
    total_b = get_total_params(model_name)
    if total_b is not None:
        return total_b > HARDWARE_FLOOR_TOTAL_B
    # Fall back to the regex-based hint (caller-side helper). We can't
    # call _model_param_hint_value here (it lives in app.py — circular).
    # Inline a minimal regex parse:
    m = _re.search(r"(\d+(?:\.\d+)?)([BMK])\b", model_name, _re.IGNORECASE)
    if not m:
        return False
    val = float(m.group(1))
    unit = m.group(2).upper()
    if unit == "B":
        return val > HARDWARE_FLOOR_TOTAL_B
    if unit == "M":
        return val / 1000.0 > HARDWARE_FLOOR_TOTAL_B
    # K → never above 35B
    return False
```

### `src/arail/portal/app.py` — `_extract_param_hint` extension

```python
def _extract_param_hint(model_name: str) -> str:
    """Parse '235B', '70B', '754B' etc. out of a HF repo name.

    First consults model_specs.MODEL_METADATA_OVERRIDES — when the
    name matches a known MoE / multi-segment override the override's
    total_params_b is rendered (e.g. "400B"). Otherwise falls back
    to the existing regex. Returns "" when neither matches.
    """
    from arail.model_specs import get_total_params
    override_b = get_total_params(model_name)
    if override_b is not None:
        if override_b >= 1000:
            return f"{override_b/1000:.1f}T"
        return f"{override_b:.0f}B" if override_b == int(override_b) else f"{override_b:.1f}B"

    import re as _re
    match = _re.search(r"(\d+(?:\.\d+)?)([BMK])\b", model_name, _re.IGNORECASE)
    if match:
        return f"{match.group(1)}{match.group(2).upper()}"
    return ""
```

### `_prepare_chat_context` — 35B override (new block)

Inserted at app.py:3681, immediately AFTER the existing
`wants_deep = optional_backend_name in _OPTIONAL_CHAT_BACKEND_CONFIG`
line:

```python
# ── Hard hardware-floor rule (35B total params) ────────────────────
# If the dispatch landed on a non-Deep backend (mlx/cuda/cpu/runtime
# override) AND the chosen model's total params exceed the hardware
# floor, silently route to AirLLM (Deep) instead. This is the SERVER-
# SIDE enforcement — clients can lie about their selection but the
# server still routes correctly. See sprint VISION § 35B rule.
if not wants_deep:
    from arail.model_specs import must_stream as _must_stream
    candidate_model = (model_override or "").strip() or os.getenv("MODEL_NAME", "")
    if _must_stream(candidate_model):
        wants_deep = True
        optional_backend_name = "airllm"
        activity_log.emit(
            "chat",
            f"35B+ model '{candidate_model}': routing to Deep (AirLLM) "
            f"per hardware floor.",
            "info",
        )
```

### `/api/chat/models` — `streamed` field per entry

In the existing handler at app.py:4486, when constructing each model
entry in `gallery.installed`, `optional_backends`, and `local_models`,
add:

```python
entry["streamed"] = must_stream(entry.get("model") or entry.get("id") or "")
```

`deep_info` at app.py:4628 also gets `"streamed": True` (deep is always
streamed by definition). The picker JS reads `m.streamed` and renders
the badge.

### Picker JS — streamed badge (chat.html)

In `makeOpt` (chat.html:1933 area), insert alongside the existing
`new` and `deep` badges:

```js
${m.streamed ? '<span class="streamed-badge" title="Layer-streamed via AirLLM (model exceeds local hardware floor)">streamed</span>' : ''}
```

CSS (chat.html `<style>` block, near `.deep-badge`):
```css
.streamed-badge {
  font-size: 0.55rem;
  color: var(--amber, #c8a060);
  border: 1px solid var(--amber-a28, rgba(200,160,96,0.28));
  background: var(--amber-a08, rgba(200,160,96,0.08));
  padding: 0 0.4rem;
  border-radius: 3px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}
```

### New endpoints (all under `/api/admin/models/*` — same auth posture as existing `/api/admin/*`)

| Method | Path | Body | Response | Errors |
|---|---|---|---|---|
| GET | `/api/admin/models/scan` | — | `{ models: [{id, path, runtime, size_gb, total_params_b: float\|null, streamed: bool, loaded: bool, ctx: int\|null}], default_gpu_model: str\|null, snapshot: {label, gpu_label, total_gb, free_gb, used_gb}, ctx_overrides: {model_id: int}, scanned_dir: str }` | n/a — empty `models` if dir missing. Never 5xx. |
| POST | `/api/admin/models/load` | `{ model_id: str }` | `{ ok: bool, status: str, model: str, loaded_at: float, streamed: bool }` | 400 `{ok:false, error:"unknown model_id"}` if not in scan results; 400 `{ok:false, error:"path traversal"}` if Path resolution escapes MODELS_DIR; 409 `{ok:false, error:"model load already in progress"}` if `_MODEL_LOAD_LOCK` held; 503 `{ok:false, error:"airllm not installed (./arail upgrade max)"}` if streamed model + AirLLM missing. |
| POST | `/api/admin/models/unload` | `{ model_id: str }` | `{ ok: bool, status: "unloaded", model: str }` | 400 unknown id; 409 if in-flight chat is using the model (`_INFLIGHT_BY_LABEL["chat-deep"] > 0` or analog) AND `force=false`. |
| POST | `/api/admin/models/set-default` | `{ model_id: str }` | `{ ok: bool, default_gpu_model: str }` | 400 unknown model_id; 400 if `must_stream(model_id)` is True (default GPU model must fit in GPU — streamed models cannot be the default). |
| POST | `/api/admin/models/set-ctx` | `{ model_id: str, ctx: int }` | `{ ok: bool, model_id: str, ctx: int, ctx_overrides: {...} }` | 400 unknown id; 400 if `ctx` not in [256, 1_000_000]; 400 if not int. |

All five endpoints:
- Read JSON body via `await request.json()`, default `{}` on parse error.
- Validate `model_id` against `_scan_local_models()` cached result first
  (5-second TTL cache) — cheap defense against arbitrary path injection.
- Persist set-default and set-ctx via `_write_secrets()`.
- Are NOT in `allowed_prefixes` — onboarding gate enforces auth like all
  other `/api/admin/*`.

### `_scan_local_models()` helper (new, app.py)

```python
def _scan_local_models() -> dict[str, Any]:
    """Single source of truth for the on-disk model listing.

    Returns a dict with `models` (list), `default_gpu_model`,
    `ctx_overrides`, `snapshot`. Cached for 5 seconds via module-level
    state to avoid re-walking the dir on every chat request.

    Postcondition: never raises. Returns empty list if MODELS_DIR
    doesn't exist or is unreadable.
    """
    # ... see Failure modes for the validation rules.
```

Module-level cache:
```python
_MODELS_SCAN_CACHE: dict[str, Any] | None = None
_MODELS_SCAN_TS: float = 0.0
_MODELS_SCAN_TTL = 5.0  # seconds
_MODEL_LOAD_LOCK = asyncio.Lock()  # single-flight for /load and /unload
```

### Persistence keys in `lab/data/secrets.env`

```
ARAIL_DEFAULT_GPU_MODEL=Qwen3-8B-4bit
ARAIL_MODEL_CTX_OVERRIDES={"Qwen3-8B-4bit":4096,"Llama-4-Maverick-17B-128E-Instruct-fp8":1024}
```

JSON-encoded value for the CTX overrides because secrets.env is
flat. `_write_secrets()` will quote-escape; the reader uses
`json.loads(os.getenv("ARAIL_MODEL_CTX_OVERRIDES", "{}"))`.

### Admin "Models" admin section (admin.html)

Inserted after the Production Readiness section at admin.html:613
(after the closing `</div>` of `pr-grid` block):

```html
<!-- ═══ Models ═══ -->
<div class="admin-section">
  <h2>Models</h2>
  <div class="models-section">
    <div class="models-default-row">
      <label>Default GPU model</label>
      <select id="models-default" onchange="setDefaultModel(this.value)">
        <option value="">— none —</option>
      </select>
      <span class="models-hw" id="models-hw"></span>
    </div>
    <div id="models-list" class="models-list">loading…</div>
  </div>
</div>
```

CSS (admin.html `<style>` block, after `.pr-toggle` at ~admin.html:531):
```css
.models-section { display: flex; flex-direction: column; gap: 0.65rem; }
.models-default-row { display: flex; align-items: center; gap: 0.6rem; font-size: 0.78rem; }
.models-list { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 0.5rem; }
.models-row { padding: 0.55rem 0.7rem; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); }
.models-row .name { display: flex; align-items: center; gap: 0.4rem; font-size: 0.8rem; color: var(--text-hi); }
.models-row .meta { font-size: 0.7rem; color: var(--muted); margin-top: 0.2rem; }
.models-row .actions { margin-top: 0.45rem; display: flex; gap: 0.35rem; align-items: center; flex-wrap: wrap; }
.models-row .badge-streamed {
  font-size: 0.55rem; color: var(--amber); border: 1px solid var(--amber-a28, rgba(200,160,96,0.28));
  background: var(--amber-a08, rgba(200,160,96,0.08));
  padding: 0 0.4rem; border-radius: 3px; letter-spacing: 0.06em; text-transform: uppercase;
}
.models-row.loaded { border-color: var(--green); }
.models-row .ctx-input { width: 5rem; font-size: 0.7rem; padding: 0.15rem 0.3rem; background: var(--surface); color: var(--text); border: 1px solid var(--border); border-radius: 3px; }
```

JS driver appended after `toggleAutoScan` at admin.html:1058:

```js
// ── Admin Models section ───────────────────────────────────────────
let _modelsCache = null;
async function loadModels() {
  const list = document.getElementById('models-list');
  if (!list) return;
  try {
    const r = await fetch('/api/admin/models/scan');
    if (!r.ok) throw new Error('HTTP ' + r.status);
    const d = await r.json();
    _modelsCache = d;
    // Render default-model dropdown (filter out streamed ones — can't be default).
    const sel = document.getElementById('models-default');
    sel.innerHTML = '<option value="">— none —</option>' +
      d.models.filter(m => !m.streamed).map(m =>
        `<option value="${_prEsc(m.id)}" ${m.id === d.default_gpu_model ? 'selected' : ''}>${_prEsc(m.id)}</option>`
      ).join('');
    document.getElementById('models-hw').textContent =
      d.snapshot ? `${d.snapshot.label || ''} · ${d.snapshot.free_gb || '?'} GB free` : '';
    // Render rows.
    list.innerHTML = d.models.map(m => `
      <div class="models-row ${m.loaded ? 'loaded' : ''}" data-id="${_prEsc(m.id)}">
        <div class="name">${_prEsc(m.id)} ${m.streamed ? '<span class="badge-streamed">streamed</span>' : ''}</div>
        <div class="meta">${_prEsc(m.runtime || 'unknown')} · ${m.size_gb ? m.size_gb.toFixed(1) + ' GB' : '? GB'} · ${m.total_params_b ? m.total_params_b + 'B' : '?B'} ${m.loaded ? '· loaded' : ''}</div>
        <div class="actions">
          <button class="pr-btn" onclick="loadOneModel('${_prEsc(m.id)}')">${m.loaded ? 'Reload' : 'Load'}</button>
          <button class="pr-btn" onclick="unloadOneModel('${_prEsc(m.id)}')" ${m.loaded ? '' : 'disabled'}>Unload</button>
          <span style="font-size:.68rem;color:var(--muted);">CTX</span>
          <input class="ctx-input" type="number" min="256" max="1000000" value="${m.ctx || ''}" placeholder="—" onchange="setModelCtx('${_prEsc(m.id)}', this.value)">
        </div>
      </div>`).join('');
  } catch (e) {
    list.innerHTML = `<div class="pr-err">Failed to load models: ${_prEsc(e.message)}</div>`;
    adminLog('Models scan failed: ' + e.message, 'error');
  }
}
async function loadOneModel(id) {
  adminLog(`Loading ${id}…`);
  const r = await fetch('/api/admin/models/load', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({model_id:id})});
  const d = await r.json();
  if (!r.ok || !d.ok) { adminLog('Load failed: ' + (d.error || 'unknown'), 'error'); return; }
  adminLog(`${id} loaded${d.streamed ? ' (streamed)' : ''}.`);
  loadModels();
}
async function unloadOneModel(id) {
  if (!confirm(`Unload ${id}?`)) return;
  const r = await fetch('/api/admin/models/unload', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({model_id:id})});
  const d = await r.json();
  if (!r.ok || !d.ok) { adminLog('Unload failed: ' + (d.error || 'unknown'), 'error'); return; }
  adminLog(`${id} unloaded.`);
  loadModels();
}
async function setDefaultModel(id) {
  if (!id) return;
  const r = await fetch('/api/admin/models/set-default', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({model_id:id})});
  const d = await r.json();
  if (!r.ok || !d.ok) { adminLog('Set default failed: ' + (d.error || 'unknown'), 'error'); return; }
  adminLog(`Default GPU model: ${id}.`);
}
async function setModelCtx(id, ctx) {
  const n = parseInt(ctx, 10);
  if (!n || n < 256) return;
  const r = await fetch('/api/admin/models/set-ctx', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({model_id:id, ctx:n})});
  const d = await r.json();
  if (!r.ok || !d.ok) { adminLog('Set CTX failed: ' + (d.error || 'unknown'), 'error'); return; }
  adminLog(`${id} CTX → ${n}.`);
}
```

Initialize from the existing DOMContentLoaded block at
admin.html:1305: append `loadModels();` to the trailing init list.

---

## Failure modes (paranoid pass)

### A. Hard 35B rule (`must_stream` + dispatch override)

| # | Failure | Detection | Recovery / Mitigation |
|---|---|---|---|
| A1 | Bypass via direct API: client POSTs `/api/chat` with `backend:"mlx"` and a 70B model | The override happens **server-side in `_prepare_chat_context`** at app.py:3681 — there is no client-side enforcement. | Test: `tests/test_must_stream_rule.py::test_direct_api_bypass_routes_to_deep` POSTs to `/api/chat` with `{backend:"mlx", model:"meta-llama/Llama-3.1-70B"}` and asserts the response's `backend` field is `"airllm"` (not `"mlx"`) and the activity log contains the "routing to Deep" line. |
| A2 | Capacity-0 / regex fails: model name has no `\d+B` and no override (e.g. raw repo name "tinyllama-finetuned") | `_extract_param_hint` returns "", `get_total_params` returns None. | **Default = treat as small (don't force Deep).** Justification: a small model dispatched locally is the common safe case; a large model dispatched locally OOMs. Risk: a 200B model named "MyMystery" slips through. Mitigation: documented in `model_specs.MODEL_METADATA_OVERRIDES` doc-comment ("add a regex if you ship something whose name doesn't expose total params"). The README + admin Models card both nudge users to add overrides. |
| A3 | AirLLM not installed (min tier) when 35B+ model is selected | `_get_optional_chat_backend("airllm")` raises ImportError / AttributeError; caught at app.py:3687 → returns `_optional_backend_error_result()` with a clean reply text + `error` field. | The picker MUST show the streamed badge AND a tooltip "Requires `./arail upgrade max` to load." `optional_backends` payload at app.py:4658 already returns `installed: false` for AirLLM in min tier; the picker uses this to render disabled state. **Test:** `tests/test_must_stream_rule.py::test_streamed_model_min_tier_clean_error` mocks AirLLM uninstalled, dispatches a 70B → asserts response body has the "AirLLM not installed" hint and HTTP 200 (not 500). |
| A4 | Override regex cost on every dispatch is non-O(1) | `must_stream` and `get_total_params` both wrapped with `@lru_cache(maxsize=512)` | First call = O(N) where N = `len(MODEL_METADATA_OVERRIDES)` (small — ≤20 entries realistically); subsequent calls = O(1). N grows as overrides are added; not a concern for v1. |
| A5 | Activity-log spam — every chat fires "routing to Deep" line | `activity_log.emit(... "info")` runs once per dispatch (not per token) | Acceptable; the info-level message lets operators see what's happening. If noisy, downgrade to debug-only or rate-limit. Filed as tech debt, not now. |
| A6 | Symlinked Llama-4 directory present but model name in env is the HF repo path | `_extract_param_hint` is called with whatever's configured in `AIRLLM_MODEL` (e.g. `meta-llama/Llama-4-Maverick-17B-128E-Instruct`); the regex pattern matches both this AND the local symlink name `Llama-4-Maverick-17B-128E-Instruct-fp8`. | Regex pattern `Llama-4.*Maverick.*17B.*128E` is broad enough to match both. Test: `tests/test_metadata_overrides.py::test_llama4_matches_hf_id_and_local_dir` asserts `must_stream("meta-llama/Llama-4-Maverick-17B-128E-Instruct") == True` AND `must_stream("Llama-4-Maverick-17B-128E-Instruct-fp8") == True`. |
| A7 | Streaming endpoint `_run_chat_completion_stream` (app.py:3802) doesn't pick up the override | Both stream + non-stream call `_prepare_chat_context` first | Verified — the override is in `_prepare_chat_context` so both paths inherit it for free. |

### B. Llama-4 metadata override

| # | Failure | Detection | Recovery / Mitigation |
|---|---|---|---|
| B1 | Override pattern collisions — a future `Llama-4-Scout-3B` model would match the same regex if it were too broad | Code review of regex specificity | The shipped pattern requires `17B.*128E` — a 3B Llama-4 won't match. Doc-comment in `MODEL_METADATA_OVERRIDES` warns: "Most-specific first; first match wins. Don't add a generic `Llama-4` pattern — it would shadow specific variants." |
| B2 | Override file becomes stale when new MoE models land | n/a — manual maintenance | Tech debt note: when entries grow >20 or non-engineers need to add them, migrate to `lab/data/model_overrides.yaml` with hot-reload. Ticket filed in Tech debt section. |
| B3 | HF model ID vs local dir name differ (`meta-llama/Llama-4-Maverick-17B-128E-Instruct` vs local `Llama-4-Maverick-17B-128E-Instruct-fp8`) | Regex tested against both forms | Pattern `Llama-4.*Maverick.*17B.*128E` matches both (B1 test covers this). |
| B4 | Regex case sensitivity surprise on weird capitalizations (`LLAMA-4-MAVERICK-17B-128E-INSTRUCT-FP8`) | `_re.IGNORECASE` flag set | Test: assert case-insensitive match. |
| B5 | `lru_cache` keeps a stale override after a hot-reload of `model_specs.py` (dev-only) | Acceptable in production; uvicorn is restarted per change | Note: `lru_cache` is on `must_stream` and `get_total_params`, both of which read `MODEL_METADATA_OVERRIDES` only on miss. In a long-running session if overrides are dynamically appended, the cache won't see new entries. **Documented limitation; not a v1 concern** — overrides change at code-edit time, which means a restart. |

### C. Admin Models section + endpoints

| # | Failure | Detection | Recovery / Mitigation |
|---|---|---|---|
| C1 | Path traversal in `model_id` parameter (e.g. `../../etc/passwd`) | Server-side validation at endpoint entry | Whitelist: `model_id` MUST appear in `_scan_local_models().models` (which iterates `MODELS_DIR.iterdir()` only). Additionally, `Path(MODELS_DIR / model_id).resolve(strict=False).parent == MODELS_DIR.resolve()` check before any file system access. Reject 400 on either failure. **Test:** `tests/test_admin_models_endpoints.py::test_load_path_traversal` POSTs `{model_id:"../../etc/passwd"}` → asserts 400. |
| C2 | Load/unload during in-flight chat — race for VRAM | Both `chat-deep` / `chat-default` and `admin-model-load` use `scheduler.inference_slot()` | New label `"admin-model-load"` shares the same semaphore (capacity 1 by default per `_capacity()` in scheduler.py). Therefore a `Load` button click waits for any in-flight chat to finish before proceeding. Operator sees the modal/button disabled during the wait. **Test:** `tests/test_admin_models_endpoints.py::test_load_serializes_with_chat` runs a fake long chat in one task, fires Load in another, asserts Load completes after chat. |
| C3 | Set-default on a streamed model | Server-side validation in `set-default` endpoint | If `must_stream(model_id) == True` → reject 400 with message "Streamed models cannot be the default GPU model." UI also filters streamed models out of the dropdown so the user can't even try. |
| C4 | Set-CTX with absurd value (e.g. `-1`, `999_999_999`, `"foo"`) | Type + range validation | `int(ctx)` parse, then `256 <= ctx <= 1_000_000`. Reject 400 otherwise. |
| C5 | Concurrent `/load` calls clobber each other | Module-level `_MODEL_LOAD_LOCK = asyncio.Lock()` | Single-flight: second concurrent `/load` returns 409 immediately (use `lock.locked()` check before `await lock.acquire()`). |
| C6 | VRAM probe failure inside scan → page crashes | `_local_memory_snapshot()` already swallows exceptions and returns zeroed dict | Verified at app.py:4914–4973. Scan handler treats `snapshot.free_gb == 0` as "unknown" and the UI renders "? GB free". |
| C7 | `lab/models/` doesn't exist on a fresh clone | Scan handler checks `models_dir.exists()` | Empty list, empty default — UI shows "No models found. Add one under `lab/models/<name>/`." |
| C8 | `secrets.env` write fails (permissions, disk full) | `_write_secrets()` already wraps the write in try/except OSError | Endpoint returns 500 with the OSError message; UI surfaces via `adminLog`. |
| C9 | Onboarding gate bypass — `/api/admin/models/*` hit pre-onboarding | `allowed_prefixes` at app.py:158–168 does NOT include `/api/admin/` | Verified. Test: `tests/test_admin_models_endpoints.py::test_onboarding_gate_blocks_models_endpoints` sends GET `/api/admin/models/scan` without a passphrase set → asserts 401. |
| C10 | Symlink under `lab/models/` pointing outside the repo (Llama-4 case) | Listing iterates `iterdir()` which returns symlinks as-is | Listing is allowed — the user explicitly created the symlink. Path-traversal validation (C1) only kicks in for the `model_id` *string* — not for what the symlink resolves to. The Llama-4 symlink target (`~/.llama/checkpoints/...`) is intentional and required. |
| C11 | The 5-second scan cache returns stale data after a manual model add | TTL 5s | Operator workflow: add model → wait ≤5s → click "Rescan" (button below the list). Acceptable. |
| C12 | `/api/admin/models/scan` is hit on every admin page load — could become slow if `lab/models/` has 100+ entries | Cap iteration | Hard cap at 200 entries. If exceeded, emit warn in payload (`{warning: "model directory has >200 entries; truncated"}`) and stop iteration. |
| C13 | `unload` while in-flight chat is using the model | `_INFLIGHT_BY_LABEL["chat-deep"] > 0` check via `scheduler.per_label_snapshot()` | Refuse with 409 + message "Model in use by an active chat. Stop the chat or set `force=true`." Force-unload still acquires `_MODEL_LOAD_LOCK` and `inference_slot`; in-flight chats will then error cleanly. |
| C14 | Activity-log message reveals model_id from a malformed request → log injection | `activity_log.emit(... model_id ...)` | The activity_log already sanitizes; model_id is bounded to ≤256 chars at validation entry; longer inputs rejected 400. |

### D. Mission card promotion + paired Status/Feed row

| # | Failure | Detection | Recovery / Mitigation |
|---|---|---|---|
| D1 | CSS: two consecutive `card full` rows render fine? | `.full { grid-column: 1 / -1; }` (style.css:471) | Verified — rows in a CSS grid simply stack. The Mission card going `card full` and then Mission Status + Activity Feed being two `card` siblings creates a clean visual: one wide row, one paired row. **Manual smoke test in QA across viewports.** |
| D2 | Mobile viewport (<900px) — symmetric 2-col paired row should collapse to stacked | `@media (max-width:900px) { .grid { grid-template-columns: 1fr; } }` (style.css:1074) | Verified — collapses for free. Both Mission Status and Activity Feed become full-width stacked. |
| D3 | Empty state — no `current_goal` set, Mission row still renders cleanly | Existing `{% if current_goal %}` blocks already gate "Curated view →" | The new mission-nav-strip wraps the same `{% if current_goal %}` around "Curated view →"; "Mission docs ↗" always renders. Empty state: nav strip shows just one link. Add a min-height on `.mission-nav-strip` so the strip doesn't visually collapse to nothing when only one link is present. |
| D4 | Existing JS targeting `id="goal-card"` breaks when class changes from `mission-card` to `card full mission-card` | grep for `goal-card` selectors | Only the ID is used as selector; classes are additive. Verified safe. **Test:** `tests/test_dashboard_layout.py::test_goal_card_id_preserved` fetches `/` with onboarding + goal set, asserts `id="goal-card"` is present and `class` includes both `card`, `full`, and `mission-card`. |
| D5 | Equal height of paired row on tall viewports | CSS grid stretches siblings by default | Verified — no extra CSS needed. If Mission Status grows much taller than Activity Feed (e.g. many experiments), Activity Feed stretches to match. Acceptable. If undesirable, add `align-items: start` to a future `.dashboard-paired-row` mixin (tech debt). |
| D6 | Indicators in `<h2>` get duplicated when adding the nav strip | Visual review | The h2 keeps its single `<span class="indicator"></span>`. Nav strip does NOT have an indicator dot. Verified in template diff. |

### E. Cross-cutting

| # | Failure | Detection | Recovery / Mitigation |
|---|---|---|---|
| E1 | The `must_stream` regex fallback inside `model_specs.py` duplicates logic from `_extract_param_hint` (DRY violation) | Code review | Acceptable: `model_specs.py` cannot import `app.py` (circular). The duplicated 4-line regex is intentional. Tests cover both paths. Tech debt: when `model_specs.py` grows, factor a tiny `_param_regex.py` shared module. |
| E2 | The 35B threshold is hardcoded in two places (`HARDWARE_FLOOR_TOTAL_B` + the doc-comment in must_stream) | Code review | Constant defined once at module level, doc-comment references it. No hardcoded duplication. |
| E3 | `lru_cache` on `must_stream` is per-process — multi-worker uvicorn would have N caches | Same caveat as the prior sprint's semaphore | Acceptable; single-worker today. |
| E4 | New endpoints accidentally added to `allowed_prefixes` by builder | Code review checklist in BUILD_LOG | Builder MUST verify the diff to `app.py:158–168` is empty (no allowlist additions). |
| E5 | The "set-default" endpoint persists `ARAIL_DEFAULT_GPU_MODEL` to secrets.env, but `MODEL_NAME` env var is what the runtime backend actually reads | Two-key disconnect | **Decision:** The set-default endpoint writes BOTH `ARAIL_DEFAULT_GPU_MODEL` (the user-facing preference, surfaced in the admin Models card) AND `MODEL_NAME` (so the runtime backend picks it up on next restart). The admin Models card displays a "Restart Lab to apply" hint after a set-default click. Tech debt: live-swap requires unloading + reloading the backend, not in v1. |

---

## Test strategy

Per ARAIL CLAUDE.md QA allocation: **30% setup / 30% Buddy / 20% security
/ 10% happy / 10% regression.** The QA persona executes; the architect
specifies coverage. NO test code in this artifact (per sprint constraint)
— file names and assertion intents only.

### Setup tests (30%)

| Test | File | Asserts |
|---|---|---|
| `test_admin_models_section_renders` | `tests/test_admin_models_endpoints.py` (new) | Fresh `/admin` page contains `<h2>Models</h2>` and the `models-section` div. (Render-only — uses Jinja TestClient.) |
| `test_models_scan_empty_dir` | `tests/test_admin_models_endpoints.py` | With a freshly-created tmp `MODELS_DIR` (empty), GET `/api/admin/models/scan` returns `{models: [], default_gpu_model: null, snapshot: {...}, scanned_dir: ".../models"}`. No 5xx. |
| `test_models_scan_no_models_dir` | `tests/test_admin_models_endpoints.py` | With `MODELS_DIR` not existing at all, GET returns empty `models` list and a `warning` field hint. |
| `test_pip_audit_uninstalled_does_not_break_models_section` | `tests/test_admin_models_endpoints.py` | With `pip-audit` mocked uninstalled, /admin still renders the Models section (independent of Production Readiness Security). |
| `test_min_tier_no_airllm_streamed_badge_renders` | `tests/test_admin_models_endpoints.py` | Mock AirLLM uninstalled. Scan a fixture dir containing a "fake-Llama-4-Maverick-17B-128E" folder. Assert `models[0].streamed == True` AND the picker JS would render the streamed badge. |
| `test_dashboard_renders_paired_row` | `tests/test_dashboard_layout.py` (new) | Fetch `/`, assert `<div class="card full mission-card"` is present, `<div class="card">` Mission Status + Activity Feed siblings exist (HTML order matters). |

### Buddy / agent tests (30%)

| Test | File | Asserts |
|---|---|---|
| `test_chat_picker_renders_streamed_badge` | `tests/test_chat_streamed_badge.py` (new) | Mock `/api/chat/models` to return a model with `streamed: true`, fetch `/chat`, assert the picker JS init data contains the streamed flag. (Test the API payload, not the rendered DOM — DOM tests are flaky in CI; payload is enough.) |
| `test_chat_picker_does_not_break_with_no_models` | `tests/test_chat_streamed_badge.py` | Mock empty gallery; assert picker still loads and shows "no models found" without 5xx. |
| `test_must_stream_rule_silent_route_to_deep` | `tests/test_must_stream_rule.py` (new) | POST `/api/chat` with `{backend:"mlx", model:"meta-llama/Llama-3.1-70B"}`. Mock the deep_backend complete. Assert response `backend == "airllm"`, response `deep == true`, and activity_log has the "routing to Deep" line. |
| `test_must_stream_streaming_endpoint_too` | `tests/test_must_stream_rule.py` | Same as above but POST `/api/chat/stream`; assert the SSE first event has `backend: "airllm"`. |
| `test_must_stream_no_override_for_small_model` | `tests/test_must_stream_rule.py` | POST with `{model:"Qwen3-8B"}`; assert dispatch lands on the configured backend (not airllm). |
| `test_must_stream_unknown_model_treated_as_small` | `tests/test_must_stream_rule.py` | POST with `{model:"my-mystery-finetune"}` (no override, no regex match); assert dispatch goes to the configured backend (not airllm). Documents the conservative-default behavior in A2. |
| `test_agent_dispatch_unaffected` | `tests/test_must_stream_rule.py` | Researcher / SRE / Pip agents that call `arail.router` directly (NOT through `/api/chat`) still work — their dispatch path doesn't go through `_prepare_chat_context` so the 35B rule doesn't gate them. **This is intentional** (agents pick models via env config, not user UI). Documented in tech debt. |
| `test_set_default_model_persists` | `tests/test_admin_models_endpoints.py` | POST `/api/admin/models/set-default` with `{model_id:"Qwen3-8B-4bit"}`, then read `lab/data/secrets.env` (mocked tmp), assert `ARAIL_DEFAULT_GPU_MODEL=Qwen3-8B-4bit`. |
| `test_set_ctx_persists` | `tests/test_admin_models_endpoints.py` | POST set-ctx, assert `ARAIL_MODEL_CTX_OVERRIDES` JSON in secrets.env contains the new mapping. Existing entries preserved on subsequent set-ctx calls. |
| `test_load_serializes_with_chat` | `tests/test_admin_models_endpoints.py` | Two concurrent tasks: long fake chat + load click; assert load waits for chat completion (via `inference_slot` order). |

### Security tests (20%)

| Test | File | Asserts |
|---|---|---|
| `test_load_path_traversal_rejected` | `tests/test_admin_models_endpoints.py` | POST `/api/admin/models/load` with `{model_id:"../../etc/passwd"}` → 400 + clear error. Same for unload, set-default, set-ctx. |
| `test_load_path_traversal_via_symlink` | `tests/test_admin_models_endpoints.py` | Create a symlink at `lab/models/evil` pointing to `/etc/passwd`. Load it. Assert containment check (parent == MODELS_DIR.resolve()) passes (symlink is in the dir) BUT the actual file open / model load fails cleanly because passwd is not a valid model dir. (Defense in depth: even if the symlink slips containment, the model loader rejects it.) |
| `test_set_ctx_invalid_inputs_rejected` | `tests/test_admin_models_endpoints.py` | POST set-ctx with `{ctx:-1}`, `{ctx:99999999}`, `{ctx:"foo"}` — all 400. |
| `test_set_default_streamed_model_rejected` | `tests/test_admin_models_endpoints.py` | POST set-default with a 70B model_id → 400 + "Streamed models cannot be the default." |
| `test_onboarding_gate_blocks_admin_models` | `tests/test_admin_models_endpoints.py` | GET `/api/admin/models/scan` without passphrase → 401. (Same posture as all other `/api/admin/*`.) |
| `test_direct_api_chat_with_70B_routes_to_deep_server_side` | `tests/test_must_stream_rule.py` | This is A1 — the headline security test. Must pass even when the test client sends `backend:"mlx"`. |
| `test_concurrent_load_returns_409` | `tests/test_admin_models_endpoints.py` | Two concurrent POST `/api/admin/models/load` → second gets 409 (lock contention). |
| `test_unload_in_use_model_refuses_without_force` | `tests/test_admin_models_endpoints.py` | Mock in-flight chat (`_INFLIGHT_BY_LABEL["chat-deep"] = 1`); POST unload → 409. POST `{force:true}` → 200. |

### Happy path (10%)

| Test | File | Asserts |
|---|---|---|
| `test_chat_models_payload_includes_streamed_field` | `tests/test_chat_streamed_badge.py` | GET `/api/chat/models` returns each model with a `streamed: bool` field. |
| `test_admin_models_scan_returns_expected_shape` | `tests/test_admin_models_endpoints.py` | Plant 2 fake model dirs, scan, assert response shape matches the contract. |
| `test_dashboard_mission_card_full_width` | `tests/test_dashboard_layout.py` | Fetch `/`, parse with BeautifulSoup or string-grep, assert `id="goal-card"` div has `class` including `card`, `full`, `mission-card`. |

### Regression (10%)

| Test | File | Asserts |
|---|---|---|
| `test_existing_chat_path_still_works` | extend `tests/test_chat_ui.py` | `/api/chat` POST with a small model still returns existing dict shape (regression after override insertion). |
| `test_pre_existing_5_failures_unchanged` | manual / CI annotation | The 5 known pre-existing failures stay isolated; no new failures introduced. (QA reports the count.) |
| `test_extract_param_hint_backwards_compatible` | `tests/test_metadata_overrides.py` (new) | Existing names like `Qwen3-235B-A22B`, `Llama-3.1-70B`, `Qwen3-8B` still return their existing hint values (`"235B"`, `"70B"`, `"8B"`). Override layer doesn't break the regex path. |
| `test_dashboard_research_report_unchanged` | `tests/test_dashboard_layout.py` | Research Report row still at `class="card full"` (no shift caused by Mission promotion). |
| `test_admin_existing_sections_unchanged` | `tests/test_admin_models_endpoints.py` | Production Readiness section + Service Status section + Activity Log section all still render. |

---

## Tech debt assessment

### Added

- **Two-key persistence disconnect (E5):** `ARAIL_DEFAULT_GPU_MODEL`
  is the user-facing preference; `MODEL_NAME` is what the runtime
  backend actually reads at boot. The set-default endpoint writes
  both, but a live in-process swap isn't supported in v1 — operator
  must restart. Filed as a follow-up: "Live default-model swap
  without restart."
- **`MODEL_METADATA_OVERRIDES` is in-code Python.** Acceptable for
  v1 (small list, edited at code-review time). Migration trigger:
  >20 entries OR non-engineers need to add them. Migration target:
  `lab/data/model_overrides.yaml` with hot-reload.
- **`must_stream` and `_extract_param_hint` duplicate a 4-line
  regex** because `model_specs.py` cannot import `app.py` (circular).
  Acceptable; factor a tiny `_param_regex.py` shared module if
  drift is observed.
- **`lru_cache` on must_stream** is per-process. Multi-worker
  uvicorn would have N caches (same caveat as the prior sprint's
  semaphore). Acceptable; documented.
- **5-second scan cache means manual model adds aren't visible
  immediately.** Operator must wait ≤5s OR click Rescan. Acceptable.
- **`inference_slot("admin-model-load")` shares the chat semaphore.**
  This means a model load blocks chat dispatch for its duration.
  Acceptable for v1 — the alternative (separate semaphore) creates
  a VRAM race. Tech debt: when ARAIL ships multi-GPU support, model
  loads can pin to a specific device and the slot semantics will
  need to evolve.
- **Default GPU model and per-model CTX persist to `secrets.env`.**
  Survives restart, but `pip install -e .` re-init from a fresh
  clone won't preserve. Documented as a future-work note in the
  admin Models card help copy.
- **The streamed-badge contract is duplicated** in chat picker JS,
  admin models JS, and the `streamed` field in `/api/chat/models`
  payload. All three are `must_stream(model_name)` calls — single
  source of truth holds, but three render sites need to match.
  Documented; not a refactor target now.
- **Activity log emits an info-level line on every 35B-routed
  dispatch.** Could be noisy on a heavily-used >35B model. Acceptable
  for v1; downgrade to debug-only or rate-limit if observed.
- **No live `MODEL_BACKEND` change hook.** Switching from `mlx` to
  `cuda` still requires `.env` change + restart. Out of scope.

### Repaid

- **First server-side enforcement of the hardware floor.** Removes
  the class of bug where a user picks a 400B model and gets an OOM
  crash 30 seconds in.
- **Single source of truth for "must stream":** `must_stream()` in
  `model_specs.py`. Both server dispatch and picker badge consult it.
- **Llama-4 finally placed correctly** in the chat picker's Deep
  section instead of being mis-categorized as 17B.
- **First admin surface for local model management** — operators
  no longer need to drop to the CLI to inspect / load / unload
  models. The Production Readiness recipe scales cleanly to a
  fourth admin section without new infrastructure.
- **Dashboard: Mission card now reads as the primary surface** it
  should be (not crammed in next to Mission Status). Cleaner
  hierarchy: Mission → Status + Feed → Research → KB.

### Net

**Slightly debt-positive** — five small coupling points
(two-key persistence, in-code overrides, regex duplication,
shared admin/chat semaphore, three-site badge rendering). All are
documented; all are bounded. The largest two (live swap + override
file format) are clear migration targets when conditions trigger.

---

## File-by-file change list (atomic-commit-friendly, in build order)

The builder lands these in the sequence below. Each numbered group is
one logical commit. Line numbers are post-PR-#28 + post-PR-#29.

### Commit 1 — `model_specs.py`: metadata overrides + `must_stream` (no behavior change yet)

- **MODIFY: `src/arail/model_specs.py`** — at module top (after the
  existing `from typing import Any, Dict, List, Optional, Tuple` at
  line 38), add:
  - `import re as _re` (lazy `re` already at use sites; this just
    surfaces it for the override regexes)
  - `from functools import lru_cache`
- **MODIFY: `src/arail/model_specs.py`** — append after the existing
  `known_models()` function (line 239):
  - `MODEL_METADATA_OVERRIDES` list (per Interface contracts above)
  - `HARDWARE_FLOOR_TOTAL_B = 35.0`
  - `def get_total_params(model_name) -> Optional[float]` (lru_cached)
  - `def must_stream(model_name) -> bool` (lru_cached)

### Commit 2 — Wire `must_stream()` into `_prepare_chat_context` (silently force Deep for >35B)

- **MODIFY: `src/arail/portal/app.py`** — at app.py:3681 (immediately
  after the `wants_deep = optional_backend_name in ...` line, before
  the `deep_backend = None` line at 3682), insert the override block
  per Interface contracts above. Imports `must_stream` from
  `arail.model_specs`.
- **MODIFY: `src/arail/portal/app.py`** — at app.py:4813, replace
  the body of `_extract_param_hint` with the override-first version
  per Interface contracts. Keep the existing 4845–4857
  `_model_param_hint_value` unchanged (it calls `_extract_param_hint`
  internally so it inherits the override behavior for free).

### Commit 3 — Update `/api/chat/models` payload to include `streamed: bool`

- **MODIFY: `src/arail/portal/app.py`** — in `api_chat_models`
  (app.py:4486), add `entry["streamed"] = must_stream(...)` to:
  - `deep_info` (app.py:4628) — set `"streamed": True` (always streamed
    by definition)
  - each entry in `optional_backends` (app.py:4658)
  - `_build_local_model_entry` call site (app.py:4706) — add
    `streamed=must_stream(entry.get("id"))` parameter; modify the helper
    function (greppable name `_build_local_model_entry`) to accept and
    surface this field.

### Commit 4 — Chat picker JS: render the "streamed" badge

- **MODIFY: `src/arail/portal/templates/chat.html`** — in `makeOpt`
  (chat.html:1933 area), add the `streamed-badge` HTML alongside the
  existing `new-badge` and `deep-badge`. CSS: add `.streamed-badge`
  rule near the existing `.deep-badge` rule (search for `.deep-badge`
  to find its line — likely in the same `<style>` block at the top of
  the file).

### Commit 5 — `/api/admin/models/*` endpoints

- **MODIFY: `src/arail/portal/app.py`** — insert new endpoint group at
  **app.py:3398** (immediately after the existing
  `auto-scan` endpoint at app.py:3378–3397, before the `/api/system/graph`
  route at app.py:3400):
  - Module-level: `_MODELS_SCAN_CACHE`, `_MODELS_SCAN_TS`,
    `_MODELS_SCAN_TTL = 5.0`, `_MODEL_LOAD_LOCK = asyncio.Lock()`.
  - Helper: `def _scan_local_models() -> dict[str, Any]` (5s TTL cache).
  - `GET /api/admin/models/scan`
  - `POST /api/admin/models/load`
  - `POST /api/admin/models/unload`
  - `POST /api/admin/models/set-default`
  - `POST /api/admin/models/set-ctx`
  - All use `_write_secrets()` for persistence; all validate
    `model_id` against the cached scan; all return JSON.
- **DO NOT MODIFY** `app.py:158–168` (`allowed_prefixes`) — verify
  diff is empty for that range.

### Commit 6 — Admin Models section template + JS driver

- **MODIFY: `src/arail/portal/templates/admin.html`** — at
  **admin.html:613** (immediately after the closing `</div>` of the
  Production Readiness section at line 612), insert the `<div
  class="admin-section"><h2>Models</h2>...</div>` markup per Interface
  contracts above.
- **MODIFY: `src/arail/portal/templates/admin.html`** — in the existing
  `<style>` block, after the `.pr-toggle` rule at admin.html:531,
  append the `.models-section`, `.models-list`, `.models-row`,
  `.models-default-row`, `.badge-streamed`, `.ctx-input` rules.
- **MODIFY: `src/arail/portal/templates/admin.html`** — append the
  `loadModels`, `loadOneModel`, `unloadOneModel`, `setDefaultModel`,
  `setModelCtx` JS to the trailing `<script>` block, after the existing
  `toggleAutoScan` at admin.html:1058.
- **MODIFY: `src/arail/portal/templates/admin.html`** — in the
  DOMContentLoaded init list at admin.html:1305, append `loadModels();`.

### Commit 7 — Dashboard Mission card promotion (full-width row + nav strip)

- **MODIFY: `src/arail/portal/templates/dashboard.html`** — at
  **dashboard.html:355**, change `<div class="card mission-card"
  id="goal-card">` to `<div class="card full mission-card"
  id="goal-card">`.
- **MODIFY: `src/arail/portal/templates/dashboard.html`** — at
  **dashboard.html:355–363**, simplify the `<h2>` to just
  `<h2><span class="indicator"></span> Mission</h2>`, and INSERT
  immediately after (line 364) the new `<div class="mission-nav-strip">`
  block per Interface contracts above. Wrap "Curated view →" in
  the existing `{% if current_goal %}` conditional.
- **MODIFY: `src/arail/portal/static/style.css`** — append after the
  existing `.mission-card`-related rules near line 2292, the new
  `.mission-nav-strip` and `.mission-nav-link` rules per Interface
  contracts above.

### Commit 8 — Dashboard paired Status/Feed row (verify-only commit)

- **VERIFY: `src/arail/portal/templates/dashboard.html`** — Mission
  Status (line 522) and Activity Feed (line 566) already each have
  `class="card"` (no `full`), which means they already pair as 2-col
  in the existing grid. **No template change needed.** This commit
  exists to:
  1. Add a comment to the template marking the visual pairing
     contract: `<!-- Paired with Activity Feed below — symmetric 2-col -->`
     above Mission Status, mirroring the existing comment above
     Activity Feed at dashboard.html:565.
  2. Verify equal-height rendering across viewports (manual smoke
     test in QA).
  3. Preserve `id="goal-card"` for any JS that targets it.
- If the manual smoke test in QA reveals the Activity Feed
  growing unboundedly tall (long activity history), add a
  `max-height` + scroll to `.activity-feed` selector. Defer the
  change to QA's TEST_REPORT verdict.

---

## Sequencing summary (atomic commits)

1. `model_specs.py`: metadata overrides + `must_stream()` helper (no behavior change)
2. Wire `must_stream()` into `_prepare_chat_context` + `_extract_param_hint` (silent 35B routing)
3. Update `/api/chat/models` payload with `streamed: bool` per model
4. Chat picker JS: render streamed badge
5. `/api/admin/models/*` endpoints + `_scan_local_models()` helper
6. Admin Models section template + JS driver
7. Dashboard Mission card promotion (full-width + nav strip)
8. Dashboard paired Status/Feed row (verify-only + comment)

Each commit is independently buildable: commit 1 ships as a no-op
behavior change. Commit 2 starts routing 35B+ but the picker doesn't
yet show the badge. Commit 3 surfaces the field but the picker hasn't
read it. Commit 4 completes the 35B+ user story. Commits 5–6 add the
admin surface. Commits 7–8 reorg the dashboard. The build can be
reviewed and tested in chunks.

---

## Phase-2 callouts (deferred; do NOT expand into this sprint)

- **Live default-model swap** without restart (would require
  unloading the active backend's model and loading the new one in
  the same process; currently deferred — operator restarts the lab).
- **Multi-GPU model load pinning** (currently `inference_slot` is
  global; with multi-GPU, the slot needs a `device` parameter).
- **`MODEL_METADATA_OVERRIDES` migration to `lab/data/model_overrides.yaml`**
  with hot-reload.
- **Per-token reacquire on streaming `inference_slot`** (currently
  the slot is held for the entire stream; slow client can monopolize).
- **Live `MODEL_BACKEND` change hook** (currently requires `.env`
  edit + restart).
- **Unload-while-in-use semantics** beyond the 409-then-force-flag
  v1 contract (currently force-unload may break in-flight chats
  ungracefully).
- **Activity-log severity** for the 35B-routed line (info → debug
  if too noisy after v1).
- **A `dashboard-row-full` mixin / utility class** for promoting any
  card to a full-width row without repeating the `class="card full"`
  pattern. Not now — only one promotion this sprint.
- **Server-side equal-height enforcement** for the paired row (CSS
  grid does it for free today).
- **Researcher / SRE / Pip agents** going through the 35B rule
  (currently they call `arail.router` directly; the rule only
  enforces at HTTP handler boundary). Fix when agents accept
  user-driven model selection.

---

## Plan deviations requested

None. The locked design intent in SPRINT.md is fully implementable
as specified. Two minor enrichments worth flagging but not blocking:

1. **Add `force` parameter to `/api/admin/models/unload`** (covered
   in Failure mode C13) — not in the locked spec but necessary to
   resolve the in-flight conflict cleanly. Default `false`; UI exposes
   it as a "Force unload" checkbox in a confirm dialog only if the
   first attempt returns 409.

2. **Persist `ARAIL_DEFAULT_GPU_MODEL` AND mirror to `MODEL_NAME`**
   (covered in Failure mode E5) — not in the locked spec but the only
   way the runtime backend will actually pick up the new default
   without writing a separate live-swap path. The "Restart Lab to
   apply" hint manages user expectations.

Both deviations are additive (don't remove anything from the locked
spec) and follow the same secrets.env + onboarding gate posture as
the rest of the work. Builder can implement without further architect
sign-off.

---

## Verdict

**Ready to build.** All five deliverables have:
- Verified line refs against the post-merge codebase
- Complete interface contracts (function signatures, JSON shapes,
  HTML/CSS classes)
- Documented failure modes with corresponding test names
- Atomic-commit sequencing that builds independently
- No new dependencies
- No new outbound network calls
- No changes to the rebrand surface, the airgapped default, or the
  Llama-4 symlink / `airllm_cache` directory
- Test strategy aligned to the ARAIL QA allocation (30/30/20/10/10)

The cross-sprint coordination (PR #29) resolved cleanly: the merge
landed before this sprint started, the Research Report row is
already promoted, and no rebase or wait is required. The architect
hands off to the builder with the file-by-file change list above as
the atomic-commit checklist.
