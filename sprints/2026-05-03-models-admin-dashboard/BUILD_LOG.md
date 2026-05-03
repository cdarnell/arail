# Build log: Models Admin + Hard 35B Rule + Dashboard Reorg

**Architecture:** [ARCHITECTURE.md](./ARCHITECTURE.md) at a4ef0b1
**Started:** 2026-05-03

## Plan

| # | Files | Change | Commit ref |
|---|---|---|---|
| 1 | `src/arail/model_specs.py` | Add `MODEL_METADATA_OVERRIDES`, `HARDWARE_FLOOR_TOTAL_B`, `get_total_params()`, `must_stream()` | 1df24d4 |
| 2 | `src/arail/portal/app.py` | Wire `must_stream()` into `_prepare_chat_context` + update `_extract_param_hint` | c5ba69f |
| 3 | `src/arail/portal/app.py` | Add `streamed: bool` field to `/api/chat/models` payload | 6a86fe6 |
| 4 | `src/arail/portal/templates/chat.html` | Add `streamed-badge` in `makeOpt` + CSS | 7de500d |
| 5 | `src/arail/portal/app.py` | Five `/api/admin/models/*` endpoints + `_scan_local_models()` helper | 3d78f25 |
| 6 | `src/arail/portal/templates/admin.html` | Admin Models section HTML + CSS + JS driver | fc3bb74 |
| 7 | `src/arail/portal/templates/dashboard.html`, `src/arail/portal/static/style.css` | Mission card promotion: `card full` + nav strip | 0f75a9b |
| 8 | `src/arail/portal/templates/dashboard.html` | Mission Status + Activity Feed paired row comment | 2515a49 |

## Execution

### Step 1 — model_specs.py: metadata overrides + `must_stream`
Commit: `1df24d4`

Added `import re as _re` and `from functools import lru_cache` at module top. Appended after `known_models()`:
- `MODEL_METADATA_OVERRIDES`: one entry for `Llama-4.*Maverick.*17B.*128E` (case-insensitive) mapping to 400B total / 17B active. Behemoth placeholder commented out.
- `HARDWARE_FLOOR_TOTAL_B = 35.0`
- `get_total_params(model_name) -> Optional[float]` — lru_cached, returns billions or None
- `must_stream(model_name) -> bool` — lru_cached, consults `get_total_params` then falls back to inline 4-line regex (intentional duplication; circular dep with app.py)

Verified:
- `must_stream('Llama-4-Maverick-17B-128E-Instruct-fp8')` → True
- `must_stream('meta-llama/Llama-4-Maverick-17B-128E-Instruct')` → True
- `must_stream('Llama-3.1-70B')` → True (regex fallback catches 70B)
- `must_stream('Qwen3-8B')` → False
- `must_stream('tinyllama')` → False (no match, defaults to small)

No deviations from ARCHITECTURE.md interface contracts.

### Step 2 — Wire `must_stream()` into `_prepare_chat_context` + fix `_extract_param_hint`
Commit: `c5ba69f`

Inserted the 35B override block at app.py:3681 immediately after `wants_deep = optional_backend_name in _OPTIONAL_CHAT_BACKEND_CONFIG`. When `wants_deep` is False, checks `must_stream(candidate_model)` — if True, sets `wants_deep = True`, `optional_backend_name = "airllm"`, and emits an info activity log. Candidate model derived from `model_override` or `MODEL_NAME` env var.

Replaced `_extract_param_hint` body to consult `get_total_params` first — Llama-4-Maverick now renders "400B" instead of "17B". Falls back to existing regex unchanged. `_model_param_hint_value` inherits fix for free (calls `_extract_param_hint`).

Both streaming (`_run_chat_completion_stream`) and non-streaming (`_run_chat_completion`) paths call `_prepare_chat_context` — enforcement is inherited by both for free (failure mode A7).

### Step 3 — `/api/chat/models` `streamed: bool`
Commit: `6a86fe6`

Added `"streamed": True` to `deep_info` (deep backends always stream). Changed import of `lookup` to also import `must_stream as _must_stream_ms` (though `_build_local_model_entry` has its own local import). Added `"streamed": True` to both `optional_backends` entries (airllm, aerollm). Added `streamed` computation inside `_build_local_model_entry` using a local import of `must_stream`.

Backward-compatible — new field only, existing fields unchanged.

### Step 4 — Chat picker `streamed` badge
Commit: `7de500d`

Added `.streamed-badge` CSS in chat.html `<style>` block (amber styling, border-radius 3px). Updated `makeOpt()` to read `m.streamed` and conditionally emit the badge alongside existing `new-badge` and `deep-badge`. Also added the badge to the rail render (`renderModelRail`) at the card inner HTML.

### Step 5 — `/api/admin/models/*` endpoints
Commit: `3d78f25`

Inserted 435 lines after the `auto-scan` toggle endpoint at app.py:3397, before `/api/system/graph`:

Module-level: `_MODELS_SCAN_CACHE`, `_MODELS_SCAN_TS`, `_MODELS_SCAN_TTL = 5.0`, `_MODEL_LOAD_LOCK = asyncio.Lock()`, `_MODELS_SCAN_MAX = 200`.

`_scan_local_models(force=False)`: 5s TTL cache, walks `lab/models/`, filters hidden/`_cache`/plain-files, detects runtime from dir contents, computes size_gb, total_params_b, streamed, ctx. Hard cap at 200 entries with warning payload. Never raises.

`_validate_model_id(model_id)`: checks string type, max 256 chars, no `..`/`/`/`\`, parent containment via `Path.resolve()`, whitelist check against scan results.

Five endpoints per ARCHITECTURE.md contracts. Failure-mode mitigations implemented:
- C1: path traversal — `_validate_model_id` rejects
- C3: streamed-default rejection in `set-default`
- C4: ctx 256–1_000_000 range + int validation in `set-ctx`
- C5: `_MODEL_LOAD_LOCK.locked()` → 409 on concurrent load
- C6: `_local_memory_snapshot()` swallows exceptions, scan uses its output
- C7: `models_dir.exists()` check → empty list + warning field
- C8: `_write_secrets()` OSError → 500 with message
- C9: NOT added to `allowed_prefixes` — verified diff is clean
- C10: `iterdir()` follows symlinks; path traversal check allows them
- C12: 200-entry cap with warning in payload
- C13: `per_label_snapshot()` checks `chat-deep` + `chat-default` in_flight > 0 → 409

Deviation: `load` handler uses best-effort warm for non-streamed models (sets model_name on backend) rather than calling a full `_prepare_chat_model_load` (which doesn't exist as a standalone helper). ARCHITECTURE.md said "call existing _prepare_chat_model_load" but no such standalone function exists in app.py — the load logic is embedded in the `/api/chat/model-load` endpoint. Best-effort warm is consistent with the spec's intent (C2 notes load is to "warm the wrapper class"). **No architect feedback required** — the architect's description was aspirational; the actual load path for non-streamed models is best-effort because local backends load lazily on first inference anyway.

### Step 6 — Admin Models section template + JS driver
Commit: `fc3bb74`

Inserted `<div class="admin-section"><h2>Models</h2>...</div>` after the Production Readiness section (after line 612 `</div>`). HTML includes default GPU model dropdown (filtered to non-streamed only), per-model cards grid, and a Rescan button.

CSS: `.models-section`, `.models-list`, `.models-row`, `.badge-streamed`, `.ctx-input`, `.models-default-row`, `.models-hw`, `.models-rescan`, `.models-empty`.

JS driver: `loadModels(force)`, `loadOneModel(id)`, `unloadOneModel(id)` (with force retry on 409), `setDefaultModel(id)`, `setModelCtx(id, ctx)`. Added `loadModels()` to DOMContentLoaded init block.

Uses `_prEsc()` throughout (existing admin XSS escape helper). JS strings use `JSON.stringify(m.id)` for inline onclick attributes (proper escaping).

### Step 7 — Dashboard Mission card promotion
Commit: `0f75a9b`

Changed `class="card mission-card"` to `class="card full mission-card"` on the goal-card div. Simplified `<h2>` to `<h2><span class="indicator"></span> Mission</h2>`. Inserted `<div class="mission-nav-strip">` sibling after `<h2>` containing "Curated view →" (inside `{% if current_goal %}`) and "Mission docs ↗" (always rendered).

CSS in style.css: `.mission-nav-strip` (flex, gap, margin, border-bottom, min-height for stable empty state) and `.mission-nav-link` (green pill with hover transition). Appended after `.lab-theme-text` block near line 2315.

`id="goal-card"` preserved. Indicator dot stays only in the `<h2>`, not in the nav strip.

### Step 8 — Dashboard paired Status/Feed row (verify-only)
Commit: `2515a49`

Verified: Mission Status and Activity Feed both have `class="card"` (no `full`) at dashboard.html:527 and 570 post-changes. They pair as a symmetric 2-col row in the existing grid automatically. Research Report row at line 590 remains `class="card full"` — untouched.

Added comment above Mission Status documenting the pairing contract, mirroring the existing comment above Activity Feed.

## Architect feedback required

*None. One minor deviation in Step 5 noted above (load handler uses best-effort rather than a named `_prepare_chat_model_load` helper that doesn't exist). The intent of the spec is met — load acquires the single-flight lock and inference_slot.*

## Final state

- **Commits:** 9 (1 skeleton + 8 implementation), SHAs `bb33f39` through `2515a49`
- **Test suite:** 388 passing, 5 failing — all 5 failures are the pre-existing failures from PR #28 era (unchanged). Zero new failures introduced.
- **LOC delta (approximate):** +98 model_specs.py, +493 app.py, +13 chat.html, +170 admin.html, +37 dashboard.html + style.css combined = ~811 lines added
- **Failure-mode mitigations:** All from ARCHITECTURE.md §A through §E implemented. Only deviation: Step 5 load handler best-effort for non-streamed models (see Step 5 notes).
- **Allowlist (E4):** Verified `app.py:158–168` unchanged — `/api/admin/models/*` NOT in `allowed_prefixes`.
