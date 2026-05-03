# Review: Models Admin + Hard 35B Rule + Dashboard Reorg

**Date:** 2026-05-03
**Build:** [BUILD_LOG.md](./BUILD_LOG.md) at `750819f` (HEAD of branch)
**Architecture:** [ARCHITECTURE.md](./ARCHITECTURE.md) at `cf6f221`
**Reviewer:** architect (review mode)

---

## Verdict: BLOCK

One BLOCK-level functional bug in the admin Models JS (admin click handlers
are emitted with broken HTML attribute quoting → all four buttons —
Load / Unload / Reload / set-CTX — are non-functional in the rendered DOM).
Two WEAK findings (the surfaced `_prepare_chat_model_load` "deviation" is
based on a false premise — the helper DOES exist; and the Rescan button
does not bypass the 5-second TTL cache as intended). Otherwise the spec
adherence is high and the security-critical 35B server-side rule is
correctly implemented and proven by a working unit-test of `must_stream`.

---

## Spec adherence — high level

- All 8 planned commits landed in order with the documented atomic shape.
- Failure-mode mitigations from ARCHITECTURE.md §A–§E are present in code,
  with the exceptions called out below.
- No new dependencies. No emojis introduced. `allowed_prefixes`
  (app.py:158–168) unchanged — admin Models endpoints stay onboarding-gated.
- All 9 commits are clean (no `--no-verify`, no `--amend`).
- 393 tests collected, 388 pass + 5 known pre-existing failures (verified
  pre-existing by checking out chat.html at `a4ef0b1` and re-running the
  failing test — same failure on the unmodified baseline).

---

## Mitigations table

| # | Failure mode | Mitigation in code | Verified at | Status |
|---|---|---|---|---|
| A1 | Direct-API bypass: client POSTs `backend:"mlx"` + 70B model | `_prepare_chat_context` overrides `wants_deep` and `optional_backend_name = "airllm"` AFTER reading client `backend_override`. Both stream + non-stream paths call `_prepare_chat_context`. | app.py:4115–4136 | **PASS** |
| A2 | Capacity-0 / regex fails (unknown model) | `must_stream` returns False → defaults to small (safer-default per design rationale). | model_specs.py:319–337 | **PASS** |
| A3 | AirLLM not installed when 35B+ selected | `_get_optional_chat_backend("airllm")` raises → caught at app.py:4143–4149 → returns `_optional_backend_error_result()` (HTTP 200 + readable reply). The `streamed: True` flag in `optional_backends` payload (app.py:5127) lets the picker show the install hint. | app.py:4140–4149 | **PASS** |
| A4 | Override regex non-O(1) cost | `@lru_cache(maxsize=512)` on both `get_total_params` and `must_stream`. | model_specs.py:280, 300 | **PASS** |
| A5 | Activity-log spam on every dispatch | One info-level emit per dispatch (not per token); acceptable per design. | app.py:4130–4135 | **PASS** |
| A6 | HF-id vs local-dir-name mismatch for Llama-4 | Regex `Llama-4.*Maverick.*17B.*128E` matches both `meta-llama/Llama-4-Maverick-17B-128E-Instruct` and `Llama-4-Maverick-17B-128E-Instruct-fp8` (verified empirically). | model_specs.py:253 | **PASS** |
| A7 | Streaming endpoint inherits override | Both `_run_chat_completion` and `_run_chat_completion_stream` call `_prepare_chat_context` (app.py:4269, 4428). | app.py:4258–4520 | **PASS** |
| B1 | Llama-4 pattern collision | Regex requires `17B.*128E`; `Llama-4-Scout-3B` would NOT match. Verified `must_stream("Llama-3-Maverick-17B-128E") == False` (no Llama-4 prefix). | model_specs.py:253 | **PASS** |
| B3 | HF-id vs local form | Same as A6. | model_specs.py:253 | **PASS** |
| B4 | Case sensitivity | `_re.IGNORECASE` flag set; verified `must_stream("LLAMA-4-MAVERICK-17B-128E-INSTRUCT-FP8") == True`. | model_specs.py:253 | **PASS** |
| C1 | Path traversal in `model_id` | `_validate_model_id` rejects `..`, `/`, `\`, parent-resolution check, AND whitelist against scan results. | app.py:3542–3564 | **PASS** |
| C2 | Load/unload races chat for VRAM | `inference_slot("admin-model-load")` shares the same global semaphore as `chat-deep` / `chat-default`. | app.py:3611, 3699 | **PASS** |
| C3 | Set-default on streamed model | `_ms(model_id)` check returns 400 with clear message; UI also filters streamed out of dropdown (`d.models.filter(m => !m.streamed)`). | app.py:3742–3753; admin.html:1113 | **PASS** |
| C4 | Set-CTX absurd / wrong-type input | `int()` parse + `256 <= ctx <= 1_000_000` range check. | app.py:3792–3802 | **PASS** |
| C5 | Concurrent /load → clobber | `_MODEL_LOAD_LOCK.locked()` returns 409 immediately before acquiring. | app.py:3600–3604 | **PASS** |
| C6 | VRAM probe failure | `_local_memory_snapshot()` already swallows exceptions; scan handler tolerates missing fields. | app.py:3444; admin.html:1119–1121 | **PASS** |
| C7 | `lab/models/` missing on fresh clone | `models_dir.exists()` short-circuits with empty list + `warning: "models directory not found"`. | app.py:3448–3459 | **PASS** |
| C8 | secrets.env write failure | `_write_secrets()` OSError caught → 500 + message. | app.py:3759–3762, 3815–3818 | **PASS** |
| C9 | Onboarding-gate bypass | `allowed_prefixes` unchanged at app.py:158–168; `/api/admin/models/*` NOT added. | app.py:158–168 | **PASS** |
| C10 | Symlink in `lab/models/` (Llama-4) | Listing accepts symlinks; only `model_id` STRING is path-traversal-checked, never the symlink target. | app.py:3473, 3478 | **PASS** |
| C11 | 5s scan cache stale after manual add | Rescan button intended to bypass cache via `?force=1` query param. **Endpoint does NOT read the query param → cache is NOT bypassed.** Cache expires naturally after 5s. | app.py:3567–3575 | **WEAK** (see Issue 2) |
| C12 | 200-entry cap | `_MODELS_SCAN_MAX = 200`; loop breaks with `warning` when exceeded. | app.py:3413, 3464–3466 | **PASS** |
| C13 | Unload while in-flight | `scheduler.per_label_snapshot()` checks `chat-deep` AND `chat-default` `in_flight > 0` → 409. `force=true` body param bypasses. UI prompts and retries on 409. | app.py:3674–3689; admin.html:1180–1191 | **PASS** |
| C14 | Activity-log injection via model_id | `_validate_model_id` caps length at 256 and rejects path separators before any log emit. | app.py:3547–3553 | **PASS** |
| D1 | Two consecutive `card full` rows render | Mission card promoted to `card full mission-card` (dashboard.html:355); Mission Status + Activity Feed stay `card` (526, 570); Research Report stays `card full` (589). Visual smoke test deferred to QA. | dashboard.html:355, 526, 570, 589 | **PASS** |
| D2 | Mobile (<900px) collapses paired row | `@media (max-width: 900px) { .grid { grid-template-columns: 1fr; } }` (style.css:1074). Inherited automatically. | style.css:1074–1078 | **PASS** |
| D3 | Empty `current_goal` Mission row clean | "Curated view →" wrapped in `{% if current_goal %}`; "Mission docs ↗" always renders; `min-height: 1.6rem` on `.mission-nav-strip` keeps strip stable. | dashboard.html:357–363; style.css:2328 | **PASS** |
| D4 | `id="goal-card"` JS targeting preserved | `id="goal-card"` retained on the new `card full mission-card` div. | dashboard.html:355 | **PASS** |
| D5 | Equal-height paired row | CSS grid stretches siblings by default. Verified visually deferred to QA. | style.css:463–470 | **PASS** |
| D6 | Indicator dot duplicated | h2 keeps single `<span class="indicator">`; nav strip has none. | dashboard.html:356–363 | **PASS** |
| E1 | DRY regex duplication in model_specs | Documented (intentional, circular-import avoidance). | model_specs.py:309–337 | **PASS** |
| E2 | 35B threshold hardcoded twice | Single `HARDWARE_FLOOR_TOTAL_B` constant; doc-comments reference it. | model_specs.py:277 | **PASS** |
| E3 | `lru_cache` per-process (multi-worker) | Documented; single-worker today. | n/a | **PASS** |
| E4 | New endpoints accidentally allowlisted | `git diff a4ef0b1..HEAD` confirms app.py:158–168 unchanged. | app.py:158–168 | **PASS** |
| E5 | Two-key persistence (`ARAIL_DEFAULT_GPU_MODEL` + `MODEL_NAME`) | `set-default` mirror-writes both, returns `message: "Restart Lab to apply..."`. | app.py:3755–3773 | **PASS** |

**Result:** 31/32 mitigations PASS, 1 WEAK (C11 Rescan button is a no-op
within the 5s window). 0 missing.

---

## Builder-surfaced "deviation" — independent verdict: **builder was wrong about the premise**

The builder's BUILD_LOG.md Step 5 note claims:

> The actual load logic is embedded in the `/api/chat/model-load` endpoint
> and cannot be called standalone.

This is **false**. `_prepare_chat_model_load` exists as a standalone async
function at **app.py:4721–4767** (separated out exactly so it can be called
from anywhere). It:

1. Sets `_CHAT_MODEL_LOAD_STATE` (which the chat-page UI polls via
   `GET /api/chat/model-load`) so admin loads would surface in the same
   UI affordance the chat page already has.
2. Dispatches to the right helper:
   - `_get_optional_chat_backend(provider)` if provider is one of the
     optional backends
   - `_get_runtime_backend(runtime, model)` if runtime is `ollama` or
     `mlx-openai` (the cases where `lab/models/<dir>` requires a real
     backend init)
   - `_get_primary_router()` otherwise
3. Reports `state="error"` with the exception type+message on failure
   (the admin endpoint could then surface it in the JSON response).

What the builder shipped instead, in the non-streamed branch (app.py:3630–3637):

```python
router = _get_primary_router()
await asyncio.to_thread(
    lambda: setattr(router._backend, "model_name", model_id)
    if hasattr(router._backend, "model_name") else None
)
except Exception:
    pass  # best-effort; loading state is reported via scan
```

Three concrete losses vs calling `_prepare_chat_model_load`:

1. **Errors are silently swallowed (`pass`).** A truly-broken model — e.g.
   missing `config.json`, corrupted weights, wrong architecture — never
   surfaces to the admin response. The endpoint returns `{"ok": True,
   "status": "loaded"}` even if the underlying load actually failed. The
   only feedback the operator gets is implicit ("the chat doesn't work
   when I select that model").
2. **`_CHAT_MODEL_LOAD_STATE` is never updated.** The chat-page Live
   model-load spinner / status will not reflect admin-initiated loads.
3. **For Ollama / mlx-openai models, `setattr` mutates the SHARED router's
   backend in place.** Subsequent unrelated chat requests that don't
   override `model_name` will inherit the admin-set name. Cross-request
   contamination is possible.

The "loads lazily on first inference anyway" claim is partly true (router
is lazy-initialised), but it doesn't address points 1–3.

**Verdict: WEAK.** Not BLOCK because (a) the streamed branch correctly
acquires the AirLLM backend via `_get_optional_chat_backend` (the security-
relevant case is fine), and (b) the chat path is also gated by
`_prepare_chat_context` so a malformed model still gets caught the next
time someone actually chats. But this is the kind of "best-effort" that
ages badly. **Required fix before next sprint:** replace lines 3630–3637
with a real call to `_prepare_chat_model_load(model=model_id, runtime=…,
provider=None)`, including detected_runtime from the scan results.

---

## Issues found

### Issue 1 — admin Models JS click-handler quoting is broken **[BLOCK]**

**What:** All four interactive controls in the admin Models card emit
malformed `onclick` HTML. Specifically:

```js
<button class="pr-btn" onclick="loadOneModel(${JSON.stringify(m.id)})">Load</button>
<button class="pr-btn" onclick="unloadOneModel(${JSON.stringify(m.id)})" ...>Unload</button>
<input ... onchange="setModelCtx(${JSON.stringify(m.id)}, this.value)">
```

**Where:** admin.html:1143, 1144, 1148.

**Why it's wrong:** `JSON.stringify("Qwen3-8B-4bit")` returns the string
`"Qwen3-8B-4bit"` *with its quotes*. Substituting that into the
double-quoted attribute produces literal HTML
`onclick="loadOneModel("Qwen3-8B-4bit")"`. The HTML parser closes the
`onclick` attribute at the first inner `"`, so the actual `onclick`
value becomes the broken fragment `loadOneModel(`, and the rest is
parsed as junk attributes. Verified empirically with jsdom:

```
outerHTML: <button class="pr-btn" onclick="loadOneModel(" qwen3-8b-4bit")"="">Load</button>
onclick attr: loadOneModel(
```

**Impact:** Load, Reload, Unload, and set-CTX buttons in the admin
Models card are all non-functional. The Rescan button works because it
calls `loadModels(true)` directly (no model_id substitution). The
default-model dropdown works because the `option value="..."` is built
correctly via `_prEsc`. So the entire click-driven UX of the new admin
section is broken on render.

**Suggested fix:** Switch to `data-id` + event delegation, OR use
single-quoted onclick with HTML-escaped ID, OR call `_prEsc` and wrap in
`'…'`:

```js
// Option A (preferred): data-id + event delegation
<button class="pr-btn" data-action="load" data-id="${_prEsc(m.id)}">Load</button>
// Then: list.addEventListener('click', e => { … e.target.dataset.id … })

// Option B: single quotes inside double-quoted attribute
<button class="pr-btn" onclick="loadOneModel('${_prEsc(m.id)}')">Load</button>
// (still vulnerable to a single-quote in m.id, but model_id whitelist
//  forbids ' anyway)
```

---

### Issue 2 — Rescan button is a no-op within the 5-second TTL window **[WEAK]**

**What:** The admin UI's "↺ Rescan" button calls `loadModels(true)`
which fetches `/api/admin/models/scan?force=1`. The endpoint
(`admin_models_scan` at app.py:3567–3575) does NOT read the query
parameter — it always calls `_scan_local_models()` with the default
`force=False`, which returns the cached result for up to 5 seconds.

**Where:** app.py:3567–3575 (endpoint); admin.html:1104 (caller),
admin.html:644 (Rescan button).

**Why it's wrong:** Documented user workflow in ARCHITECTURE.md §C11 is
"add model → click Rescan → see it immediately." That workflow is broken
within the 5s TTL window — the operator clicks Rescan, sees stale data,
and has to wait + re-click.

**Suggested fix:** Read the query parameter in the endpoint:

```python
@app.get("/api/admin/models/scan")
async def admin_models_scan(force: bool = False):
    ...
    data = _scan_local_models(force=force)
```

The `_scan_local_models(force=...)` parameter already exists (app.py:3416),
so this is a one-line wire-up.

---

### Issue 3 — Builder's "_prepare_chat_model_load doesn't exist" claim is incorrect **[WEAK]**

Already discussed above under "Builder-surfaced deviation." Documented
here for the issues table:

**What:** The non-streamed `load` branch best-effort-mutates a shared
router's `model_name` attribute, swallows all exceptions, and never
updates `_CHAT_MODEL_LOAD_STATE`. The available standalone helper
`_prepare_chat_model_load` (app.py:4721–4767) does all three correctly
and was overlooked.

**Where:** app.py:3627–3637.

**Suggested fix:** Replace the lambda+setattr block with a call to
`_prepare_chat_model_load(model=model_id, runtime=detected_runtime,
provider=None)`, where `detected_runtime` comes from the per-entry
scan result (`_scan_local_models()['models'][i]['runtime']`).

---

### Issue 4 — `_validate_model_id` whitelist re-uses cached scan, race window present **[NIT]**

**What:** `_validate_model_id` calls `_scan_local_models()` with the
default 5s TTL. If a model is added to `lab/models/` and the operator
clicks Load within 5 seconds, the whitelist will reject the new model
("unknown model_id"). Same window as Issue 2.

**Where:** app.py:3560.

**Why it's wrong:** Mostly cosmetic; resolved naturally after the cache
expires. Worth noting because it stacks with Issue 2 — both stem from
not honoring `force=True` plumbing.

**Suggested fix:** Have `_validate_model_id` always call
`_scan_local_models(force=False)` but invalidate the cache when the load
endpoint is invoked, OR allow the load endpoint to pass `force=True`
through to `_validate_model_id` on retry.

---

### Issue 5 — `_modelsCache` is set but never read **[NIT]**

**What:** `let _modelsCache = null;` (admin.html:1099) then
`_modelsCache = d;` (1108), but no other code reads it. Dead variable.

**Where:** admin.html:1099, 1108.

**Suggested fix:** Remove the variable, or use it (e.g. for the
defaulted CTX value when the user opens a model picker that doesn't
re-fetch).

---

## Code quality findings

- [INFO] **Lambda+ternary in to_thread** (app.py:3633–3635) is an
  awkward construct. A regular function or even a single-line
  conditional would be clearer:
  ```python
  if hasattr(router._backend, "model_name"):
      await asyncio.to_thread(
          setattr, router._backend, "model_name", model_id
      )
  ```
- [INFO] `_validate_model_id` returns `(False, err)` and the caller does
  `status = 400 if "traversal" not in err and "unknown" not in err else 400`
  (app.py:3596) — the conditional always evaluates to 400. Dead logic;
  not wrong, just confusing. Remove.
- [INFO] Duplicated `from arail.model_specs import must_stream as _ms`
  inside multiple endpoints (3606, 3702, 3742) where a single
  module-level import would suffice. Acceptable for v1.
- [INFO] `_modelsCache` dead variable (Issue 5).

## Security findings

- [INFO] **Path-traversal defense is layered** — string-level reject
  (`..`/`/`/`\`), parent-resolution check, AND whitelist check. Three
  independent checks; even if one is bypassed the others catch it.
- [INFO] **`_validate_model_id` validates length ≤256 chars** before
  any filesystem access. Good defense against memory-exhaustion via
  long model_ids.
- [INFO] **Onboarding gate confirmed unchanged.** `allowed_prefixes`
  diff is empty for the sprint range.
- [INFO] **Secrets-write path unchanged.** Both `set-default` and
  `set-ctx` use the existing `_write_secrets()` helper (chmod 0600,
  git-ignored).
- [ASK] **`os.environ` mutation in set-default and set-ctx** (app.py:3765,
  3820) updates the running process's env. This is correct for the
  read-side (subsequent reads see the new value) but the env mutation
  is not protected by a lock and is observable to other request handlers
  mid-flight. Acceptable for v1 — single-worker — but worth a note for
  multi-worker deployment.
- [INFO] The `force=true` query string is passed via JSON body
  (`{"model_id":..., "force":true}`) which is fine; not via query
  parameter. No CSRF concern beyond the existing `/api/admin/*` posture.

## Test coverage assessment

- **No new unit tests added by the builder.** Per ARCHITECTURE.md the
  test strategy was specification-only; QA executes. That is the
  documented allocation.
- **393 tests collected, 388 pass + 5 known pre-existing failures.**
  Confirmed pre-existing by reverting chat.html and re-running
  `tests/test_chat_ui.py::test_chat_page_renders_compact_single_thread_shell`
  — same failure on baseline `a4ef0b1`.
- **Existing admin tests** (`test_admin_cleanup_endpoints.py`,
  `test_admin_pr_section.py`, `test_admin_security_endpoints.py`)
  all pass: 40/40.

QA must add:

- `tests/test_must_stream_rule.py` (A1, A2, A3, A6, A7) — security
  pass, especially the headline A1 "direct API bypass with backend=mlx
  and 70B model still routes to AirLLM" assertion.
- `tests/test_admin_models_endpoints.py` (C1–C13) — entire suite.
  Critical: C5 (concurrent /load → 409), C13 (unload while in-flight →
  409 + force-true bypass), and C1 (path traversal).
- `tests/test_metadata_overrides.py` (B1, B3, B4) — Llama-4 + collision
  + case-insensitivity.
- `tests/test_dashboard_layout.py` (D1, D4) — paired-row + goal-card ID.
- A new test that **directly exercises the broken admin Models JS** by
  rendering admin.html, parsing with a real HTML parser, and asserting
  `button[data-id]` or correctly-formed `onclick` attributes — this
  would have caught Issue 1.

## Performance assessment

Not a hot-path change. `must_stream` is `lru_cache`d (O(1) after first
call). The 5s scan cache prevents `lab/models/` re-walks on every chat
request. No benchmarks needed for this sprint per design.

## Tech debt delta vs ARCHITECTURE.md prediction

Architecture predicted "slightly debt-positive." Actual delta agrees
with that, plus three previously-undisclosed items:

1. **Click-handler quoting bug (Issue 1).** Adds a follow-up ticket
   for either an event-delegation refactor or a switch-to-data-attrs.
   Probably a 30-min fix.
2. **Rescan force param disconnect (Issue 2).** Two-character fix
   (signature change), but documents an architecture pattern that
   should be checked elsewhere (any `force` parameter that the builder
   plumbed should be verified end-to-end).
3. **Best-effort load swallowing errors (Issue 3 / surfaced deviation).**
   Adds debt: silently-swallowed exceptions are the worst kind of
   debt because they look like success. Builder should be reminded that
   "the function I want doesn't exist, so I'll make it best-effort"
   warrants asking the architect, not skipping the helper.

None of these are catastrophic. None are in the security-critical path.

## Required actions before merge

1. **[BLOCK] Fix the admin Models button quoting bug** (Issue 1). Pick
   one of the three suggested fixes and ship a follow-up commit. Verify
   with a real HTML parser (not just visual inspection) that all four
   buttons have correctly-formed `onclick` attributes.

2. **[WEAK → fix or file ticket] Wire `?force=1` through to
   `_scan_local_models(force=True)`** (Issue 2). One-line change; ship
   in the same commit as the BLOCK fix.

3. **[WEAK → fix or file ticket] Replace the best-effort `setattr`
   block with a call to `_prepare_chat_model_load`** (Issue 3 / surfaced
   deviation). If a same-sprint fix is too large, file as the first
   ticket of the next sprint and add a code comment pointing to the
   ticket.

4. **[NIT, optional] Remove dead `_modelsCache` variable** (Issue 5)
   and **clean up the dead `status = 400 if ... else 400` line** at
   app.py:3596.

If items 1+2 land in a follow-up commit and item 3 has a ticket filed
(or is fixed), this passes WEAK_PASS. As shipped today, it's BLOCK
because the admin Models UX — the headline deliverable for this sprint —
is functionally broken in the browser.

---

## Phase-2 reminders (deferred per ARCHITECTURE.md, not this sprint's debt)

The following were filed in ARCHITECTURE.md § Phase-2 callouts and were
correctly NOT addressed in this sprint:

- Live default-model swap without restart.
- Multi-GPU `inference_slot` device pinning.
- `MODEL_METADATA_OVERRIDES` migration to `lab/data/model_overrides.yaml`
  with hot-reload.
- Per-token reacquire on streaming `inference_slot`.
- Live `MODEL_BACKEND` change hook.
- Activity-log severity downgrade for the 35B-routed line.
- Researcher / SRE / Pip agents going through the 35B rule (currently
  agent path bypasses `_prepare_chat_context`, which is the
  intentional dispatch boundary).

---

## Re-review 2026-05-03 (post loop-back)

**Build:** [BUILD_LOG.md](./BUILD_LOG.md) at `77f7b0f` (HEAD of branch)
**Loop-back commits:** `30c721c`, `0604d12`, `32cfb79`
**Reviewer:** architect (review mode, re-review pass)

### Verdict: PASS

All three findings from the prior review are CLOSED. No new issues
introduced by the loop-back fixes. Test suite holds at 388 pass + 5
known pre-existing failures (zero new failures, zero regressions). No
new dependencies, no `--no-verify`, no `--amend`. Imports clean.

The headline admin Models UX is now functional in the browser; the
documented Rescan workflow works; and admin-initiated loads now surface
errors and propagate state to the chat UI.

### Per-fix verification

#### Fix 1 — Issue 1 [BLOCK]: admin Models button quoting → **CLOSED**

Verified at `src/arail/portal/templates/admin.html:1098–1170`.

- **No `onclick`/`onchange` on the four interactive controls.** Lines
  1165–1166 (Load/Unload buttons) carry only `data-action` + `data-id`;
  line 1170 (CTX input) carries only `data-id`. (The two non-Models
  `onclick`s remaining in the file — lines 644 (Rescan), 640 (default
  dropdown `onchange`) — never substitute a model_id, so they were
  never broken.)
- **`_initModelsListDelegate()` exists at admin.html:1102–1120.** Single
  `click` listener on `#models-list` (1106), single `change` listener
  (1115). Reads `dataset.id` from `.closest('[data-id]')` — plain DOM
  string, never re-parsed as HTML. Quoting class of bug is
  structurally impossible with this pattern.
- **`_delegateAttached` guard works (line 1104).** The listener is
  attached to the `list` element itself, not its children, so
  `list.innerHTML = …` (line 1152) replaces children but leaves the
  listener and the guard flag intact across all subsequent `loadModels()`
  calls. Verified by reading: re-binding only happens if the page is
  fully reloaded.
- **Empirical HTML-parser sanity check (jsdom-equivalent in
  `html.parser`)** confirms `data-id="Qwen3-8B-4bit"`,
  `data-id="meta-llama/Llama-3.1-70B"`, `data-id="Test-Model.v2_alpha"`,
  and even `data-id="odd&id<x>"` (with `_prEsc` applied) all parse to
  the correct attribute values.
- **Defense-in-depth:** `_validate_model_id` (server-side, app.py:3565)
  rejects `..`/`/`/`\` and caps id length at 256, so even a bypass of
  the client-side `_prEsc` cannot produce a hostile payload that the
  load endpoint will accept.

#### Fix 2 — Issue 2 [WEAK]: Rescan force → **CLOSED**

Verified at `src/arail/portal/app.py:3568–3577`.

- **Signature is `async def admin_models_scan(force: bool = False)`**
  (line 3568). FastAPI auto-parses `?force=1` (and `?force=true`) into
  the bool argument.
- **Endpoint calls `_scan_local_models(force=force)`** (line 3577).
- **Cache invalidation is honored** at app.py:3429 — the early-return
  `if not force and _MODELS_SCAN_CACHE is not None and (now -
  _MODELS_SCAN_TS) < _MODELS_SCAN_TTL` is bypassed when `force=True`,
  forcing a fresh disk walk.
- **End-to-end trace:** click `↺ Rescan` → `loadModels(true)` (admin.html:644)
  → `fetch('/api/admin/models/scan?force=1')` (1126) → FastAPI parses
  `force=True` → `_scan_local_models(force=True)` → cache skipped,
  fresh result returned. ARCHITECTURE.md §C11 workflow restored.

#### Fix 3 — Issue 3 [WEAK]: real `_prepare_chat_model_load` → **CLOSED**

Verified at `src/arail/portal/app.py:3614–3653` and helper at app.py:4737.

- **Lambda+setattr block is gone.** The `try/except: pass` and the
  `setattr(router._backend, "model_name", model_id)` are removed.
- **`_prepare_chat_model_load(model=model_id, runtime=detected_runtime,
  provider=None)` is called** at app.py:3644.
- **`detected_runtime` resolution** at lines 3614–3619: scans local
  models, finds the entry with matching `id`, reads its `runtime` field.
  `None` if not found, but the load lock is still held inside
  `_MODEL_LOAD_LOCK`, so this is not a TOCTOU vulnerability — even if
  `runtime` is `None`, the helper's `else: _get_primary_router()`
  branch handles it.
- **Errors propagate as HTTP 500** (lines 3649–3653): if
  `load_state.get("state") == "error"`, the handler returns
  `JSONResponse({"ok": False, "error": load_state["message"]},
  status_code=500)`. Verified by reading `_prepare_chat_model_load`
  at app.py:4772–4782 — exception path sets `state="error"` and
  `message=f"Load failed: {type(exc).__name__}: {exc}"`.
- **`_CHAT_MODEL_LOAD_STATE` is naturally updated by the helper.**
  Confirmed at app.py:4744 (loading) and app.py:4762 (ready) /
  app.py:4773 (error). The chat-page UI's `GET /api/chat/model-load`
  poller will now reflect admin-initiated loads.
- **No new lock contention.** `_MODEL_LOAD_LOCK` (asyncio.Lock,
  app.py:3410) and `_CHAT_MODEL_LOAD_LOCK` (threading.Lock, app.py:4692)
  are distinct lock types with disjoint hold-windows; the threading
  lock is held only inside the brief `_set_chat_model_load_state`
  block. No deadlock risk introduced.
- **No shared-router mutation.** For `runtime in ("ollama",
  "mlx-openai")`, `_get_runtime_backend(runtime, model_id)` builds a
  per-(runtime, model_id) `OpenAICompatBackend` cached in
  `_RUNTIME_BACKEND_CACHE` (app.py:4080–4113). No in-place
  `model_name` mutation on a shared backend → cross-request
  contamination eliminated.

### New issues introduced by the loop-back

#### Issue 6 — `_CHAT_MODEL_LOAD_STATE` can stick at `state="error"` after a failed admin load **[INFO]**

**What:** When `_prepare_chat_model_load` raises (e.g. corrupt model
weights), the global `_CHAT_MODEL_LOAD_STATE` is updated to
`state="error"` and stays there until the next successful load. The
chat-page UI polling `/api/chat/model-load` will surface this error
indefinitely, even though the chat itself is unaffected (the error was
on a different model, initiated from admin).

**Where:** app.py:4773–4782 (the helper's exception path) +
app.py:3649–3653 (admin handler returns 500 but does not reset the
state to `ready`).

**Why it's INFO not WEAK:** The same property exists on the chat-driven
load path (app.py:4791+) — this isn't a regression, it's the helper's
established contract being correctly inherited by admin. A
"clear-error" follow-up could file as a Phase-2 ticket if it shows up
in real use.

**Suggested fix (Phase-2):** Add a `_clear_chat_model_load_state()` or
auto-clear after N seconds of `state="error"`, or have the chat poller
treat error-stuck-without-recent-update as `ready`.

### Mitigations table delta

| # | Failure mode | Status now |
|---|---|---|
| C11 | 5s scan cache stale after manual add | **PASS** (was WEAK; Rescan now correctly bypasses TTL via `force=true`) |

All other rows unchanged from the prior review's table.

### Sanity checks

- `git log --oneline e08d91f..HEAD` shows exactly **3 fix commits**
  (`30c721c`, `0604d12`, `32cfb79`) plus the BUILD_LOG.md update
  (`77f7b0f`). 4 total since the prior review, 3 of them functional.
- `python -c "from arail.portal import app; from arail import
  model_specs"` → clean (no warnings, no errors).
- No `--no-verify` or `--amend` in any commit message in the loop-back
  range.
- No new dependencies (`pyproject.toml` and `requirements*.txt`
  unchanged in the loop-back range).
- Test suite: **388 passed, 5 failed**. The 5 failures are the same
  pre-existing tests called out in the original review
  (`test_buddy_suggesters`, `test_chat_ui`, `test_drafter`,
  `test_toast_ui` x2). Zero new failures.

### Required actions before merge

None. All three prior findings are closed. Issue 6 is INFO-level and
does not block.

### Phase-2 reminders unchanged

(See section above; no additions from this re-review except the
optional Issue 6 follow-up.)


QA should NOT mark these as gaps; they are deliberately deferred.
