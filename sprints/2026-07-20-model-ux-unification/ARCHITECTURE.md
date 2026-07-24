# Architecture: Model selection UX — unified-list fidelity, disclosed honestly

**Date:** 2026-07-20
**Spec:** [VISION.md](./VISION.md) at `8b2c9cab334a05ab440d04185cbf024d7aae70f2`
**Six-gap brief:** the `§2.1–§2.6` labels below are shorthand for the six gaps enumerated in **VISION.md → "Wedge"** (nest snapshot / read the truthful list / stop the lying button / catalog copy / delete `backend_notice` / fix the pointer / load-state-machine). There is **no committed `PROMPT.md`** — a prior draft cited one at a path that does not resolve; that citation is corrected here to point at the VISION.md sections that actually carry these items. All `§`-references below are verifiable against VISION.md + `src/`, not an uncommitted file.
**Mode:** design
**Leash:** Phase 0 (display fidelity) ships as its own PR first. **Phase 0b (load/unload lifecycle honesty) is a second, small-but-real PR** that must land before any load-widget/ETA UI is trusted — it is NOT "one-line wiring" and is not smuggled into Phase 0. Additive UI is gated behind disconfirming-evidence #1. If §2.2 or the Phase-0b executor needs a bigger refactor than the contracts here size it, **stop and report — do not expand quietly.**

---

## Restatement

This is attempt #6 at the same screen, and the previous five all died the same way: correct backend truth about memory/fit is computed server-side, never reaches the DOM, gets filed as a "follow-up," and the next sprint redesigns the layout from a blank page. The one Chat-tab model list currently shows **five simultaneous false claims** — a `Local · GPU (≤ 8B)` header over a 26B model, a green `good` fit chip on that 26B (frontend defaults every missing verdict to `'good'`), `—` for free RAM/VRAM (the snapshot is computed but nested one level too high in the payload), an Eject button that returns `{"ok": true}` while the multi-GB aeroLLM singleton stays pinned, and `backend_notice`/catalog copy that oversells a streaming capability (`AERO_MOE_SELECT`) that is off and absent from `src/`. Every one of those is backed by *correct code that never renders*. The deliverable is **truthfulness of the list that already exists** — wire the computed truth to the screen, delete the lies that can't be made true this sprint, and keep it one list in the Chat tab (no new tab). **The first-draft of this architecture fixed the display lies but left the load/unload lifecycle — Cancel, timeout, concurrency, model-switch, eject — as un-audited moving parts; three adversarial critiques showed that half was about to ship a *sixth* class of lying button (Cancel reports `canceled` while an un-cancellable thread finishes loading; Ollama eject reports `ok:true` when `ollama stop` failed). This revision closes those.** If I can't restate it, the things that must be honest are: **fit chip, free-memory line, both Unload paths, the Cancel affordance, the load-state, and the backend badge copy.**

---

## Assumptions

Hidden assumptions kill systems. These are the ones this design rests on; each has a failure-mode row and a test.

1. **A1 — `gallery.installed` and `compact.local_models.items` share one source.** Confirmed: `local_entries` is built by iterating `gallery.get("installed", [])` (`app.py:7773-7786`) and enriching each row with `_build_local_model_entry` (which adds the real `fit`). So the "two lists" are one list, one enriched. This is what makes §2.2 cheap. **If this were two independently-sourced lists, the "one sprint, mostly wiring" premise would be wrong** (disconfirming-evidence #2 → stop and re-scope).
2. **A2 — `_local_memory_snapshot()` reflects real OS truth within ±1 GB at read time.** It reads `psutil.virtual_memory()` (Apple Silicon unified memory) or `nvidia-smi` (CUDA). `psutil` is a hard dep. **But** if the import ever fails, the darwin fallback currently sets `free_gb = total_gb` (`app.py:8164`) — a lie in the optimistic direction. This design closes that (F-FALLBACKLIE): a failed `available` probe must yield `Unknown`, never a number equal to total.
3. **A3 — the aeroLLM singleton cannot be hot-freed this sprint, but its residency *is* observable.** Freeing it requires clearing three caches (`AeroLLMBackend._shared[key]`, `deep_policy._deep_router`, `_OPTIONAL_CHAT_BACKEND_CACHE`), coordinating with the `model_warmth.py` preload loop (which re-warms within `ARAIL_AEROLLM_PRELOAD_INTERVAL_SEC`, default 300s, floor 30s, whenever `metal_memory_pressure() < 0.60`), and trusting the Rust `Runtime`'s Drop to release Metal memory — none verified this session. **However**, `model_warmth._tier1_resident()` (`model_warmth.py:45-49`) already reports whether `AeroLLMBackend._shared` holds an instance — so warmth is *probeable* and the badge must reflect the probe, not `installed` (F-WARMDOT). We design honest-absence for *freeing*, honest-presence for the *badge*, and we keep the *real* Load (a genuine cold→WARM warm-up).
4. **A4 — the Ollama load path is now bounded at the daemon, but the portal-side thread is not cancellable.** Recent commits bounded the warm-up ping (`think:false` + `num_predict`). But `_prepare_chat_model_load` runs the load in `asyncio.to_thread(...)` (`app.py:7209-7215`), which **cannot be cancelled or killed externally.** Every load-lifecycle contract in this doc is written to that hard constraint: we do not pretend to interrupt a running thread; we prevent it from doing harm (double residency, false `canceled`).
5. **A5 — free-memory readings are stable enough to render a non-flickering verdict** on an idle machine. If they jitter enough to flip a chip between `Good` and `Requires streaming` across refreshes, that is a *new* lie (disconfirming-evidence #3) and forces a smoothing sub-project before any chip ships. The ±0.82/±1.08 hysteresis bands in `_fit_verdict_label` should absorb normal churn; T-NOFLICK verifies it.
6. **A6 — MoE resident footprint ≈ full quantized weights on disk.** `gemma-4-26b-a4b` is 26.5B total / ~4B active, but Ollama loads *all* experts resident (~13.4–14.4 GB q4). The honest memory number is the disk/weights figure, not the active-param figure. `size_gb`/`expected_disk_gb` is the right basis (`_estimate_model_memory_gb` prefers it).
7. **A7 — no operator relies on the current false `{"ok": true}` eject response** as a scripting contract. Changing it to honest `ok:false` (aerollm/airllm) and `ok = (returncode==0)` (ollama) is a behavior change we accept (F-EJECTLIE, F-EJECT-OLLAMA-FALSE).
8. **A8 — at default `ARAIL_INFERENCE_CONCURRENCY=1` a single global semaphore serializes all heavy inference.** `scheduler.inference_slot()` is one `asyncio.Semaphore(_capacity())`, `_capacity()` clamps to `[1,4]` default `1` (`scheduler.py:91-114`). The preload loop already takes it (`aerollm-preload`, `model_warmth.py:72`); admin loads take it (`admin-model-load`, `app.py:5586,5678`); chat streaming takes it. Chat model-load currently does **not** — so at default config a chat load races the preload toward the memory ceiling (F-LOADRACE). Wrapping the load in the same slot closes this at default config. **At `>1` the operator opted into concurrent heavy ops** (a pre-existing scheduler property, not introduced here) — named as a review-dated follow-up, not silently relied on.

---

## Data flow

```
                          ┌─────────────────────────────────────────────┐
   OS truth               │  _local_memory_snapshot()  app.py:8145      │
   (psutil / nvidia-smi)──►  {label,total_gb,used_gb,free_gb,gpu_label} │
                          └───────────────┬─────────────────────────────┘
   FIX F-FALLBACKLIE: psutil-import-fail  │ free_gb   (NEVER free_gb=total_gb;
   ⇒ free_gb=0 ⇒ verdict "Unknown"        ▼            failed probe ⇒ 0 ⇒ Unknown)
   ollama /api/tags ─┐                                (tags size = REAL on-disk bytes)
   ollama ps  (warm) ├─► gallery_view() ─► gallery.installed[]  ── same source ──┐
   mlx dir scan      │   (chat/__init__)   {id,runtime,size_gb,modified,endpoint}│
   mlx-openai server ┘                                                           ▼
                          ┌──────────────────────────────────────────────────────────┐
                          │ _build_local_model_entry()  app.py:8243                    │
                          │   estimate_gb = _estimate_model_memory_gb(size_gb|params)  │
                          │   verdict     = _fit_verdict_label(estimate_gb, free_gb)   │  ◄── REAL fit
                          │   warm        = ollama_ps_resident(id)  (Ollama rows)      │  ◄── REAL warmth
                          │   → local_entries[] each carrying .fit + .warm             │
                          └───────────────┬──────────────────────────────────────────┘
                                          ▼
   GET /api/chat/models  ──►  compact_selector = {
                                  local_models.items = local_entries,   ← has fit + warm
              §2.1 FIX  ────────► hardware           = memory_snapshot,  ← nested (SOLE location)
                                  compute_sources, ... }
                              + top-level: gallery, optional_backends, model_load, ...
                              ✗ top-level `hardware` DELETED (BLOCK-1) — not a second unread field
                                          │
   ══════════════════ NETWORK BOUNDARY (JSON) ══════════════════
                                          │
   chat.html initModels()                 ▼
   OLD: State.models = d.gallery.installed        (no fit → 3296/3375 default 'good')   ✗ LIE
   NEW: State.models = d.compact.local_models.items                                     ✓ real fit
        + concat deepEntries(optional_backends):
            runtime='aerollm' resident   → badge "resident (aeroLLM)"  [warmth-probed]
            runtime='aerollm' cold       → badge "installed (aeroLLM)" · Load available
            runtime='airllm'  (opt-in)   → badge/notes say "AirLLM", NOT aeroLLM (finding 5)
            NO Unload/Eject button on either deep row; Load STAYS (real warm-up, finding 7)
                                          │
                                          ▼
   renderModelRail()  →  per-row: warm-dot(live) · name · size · [fit-chip=real] · WARM/cold
                         local column header:  "Local · GPU"      (NO "≤ 8B")     F-HEADER
                         deep  column header:  "Local · aeroLLM"  (NO "SSD (streamed)")  F-HEADER twin
                         expand → free RAM/VRAM, keep_alive, load ETA (progressive disclosure)
   telemetry: tele-hw/tele-vram ← d.compact.hardware   §2.1 (was undefined)

   ──── Unload path ────
   Ollama row  → POST /api/chat/eject {runtime:'ollama',model} → `ollama stop`
                 ⇒ {ok: (rc==0), freed:[…] if rc==0}    ✓ ok TRACKS returncode (F-EJECT-OLLAMA-FALSE)
   deep row    → NO eject button rendered.  Endpoint, if hit: honest per-runtime
                 aerollm/airllm ⇒ {ok:false, requires_restart:true,
                                   notes:["resident (<backend>) · frees on next portal restart"]}
                 (terminal return computes ok/requires_restart — NOT unconditional ok:true, finding 6)

   ──── Load path (Phase 0b, serialized + honest) ────
   POST /api/chat/model-load → _prepare_chat_model_load
        async with _CHAT_MODEL_LOAD_INFLIGHT (dedicated, cap 1)          ← one load at a time (F-CACHERACE, F-TIMEOUT-ORPHAN)
          async with scheduler.inference_slot("chat-model-load")         ← serialize vs preload/admin/stream (F-LOADRACE)
            re-snapshot free_gb; recompute verdict for target            ← fit is a click-time precondition (F-REFIT)
            state: idle → loading → ready | error   (NO "canceled" while a thread runs; F-CANCEL, F-INITREADY)
            eta_seconds = on_disk_bytes / throughput   (on_disk from tags, not manifest; F-CORRUPT, F-FAKEETA)
            _get_optional_chat_backend checks model identity            ← wrong-model never reports "ready" (F-SWITCH)
            wall-clock guard flips *reported* state to error but the
              inflight lock is NOT released until the thread settles    ← no second load ⇒ no double-residency OOM
            on error: friendly message, daemon-down banner, NO traceback (F-DAEMONDOWN)
```

---

## Interface contracts

### C1 — `compact_selector` payload (`app.py:7811-7839`)
- **Promises:** returns a dict that nests `hardware` (the snapshot object). `compact.local_models.items` carries `_build_local_model_entry` rows, each with a real `fit.verdict ∈ {Good, Marginal, Requires streaming, Unknown}` derived from real `free_gb`, and a real `warm` boolean for Ollama rows (F-WARMDOT).
- **Requires:** `memory_snapshot` computed before assembly (already true — `app.py:7772`).
- **Bad input:**
  - `_local_memory_snapshot()` returns `free_gb == 0` (probe failed, incl. the psutil-import fallback which **no longer** sets `free_gb=total_gb`) → `_fit_verdict_label` returns `"Unknown"`, telemetry shows the raw label + `?`, never a fabricated number and never `Good` (F-FALLBACKLIE).
  - Declared manifest `size_gb` disagrees with the model's real on-disk/tags size beyond tolerance, or the model is not resolvable → fit `Unknown`, ETA `null` (F-CORRUPT).
- **BLOCK-1 resolution — the top-level `hardware` key is DELETED in this same edit, not deferred.** The prior draft said the top-level key "may linger one release (prefer deleting)." That is an undated, ownerless follow-up that deliberately creates a duplicated field the frontend does not read — the literal F8 dead-field pattern this sprint exists to kill. The **only** reader of `hardware` is the frontend, and this same PR repoints it at `compact.hardware`; there is no external consumer to break (A7-class). Implementation-order step 1 nests-and-deletes in one move; F-DEADFIELD's grep asserts zero top-level `hardware`.

### C2 — rail data source (`chat.html` initModels ~3707, renderModelRail 3280-3324)
- **Promises:** `State.models` for the local/Ollama column is sourced from `d.compact.local_models.items` (real `fit`), then `deepEntries` are concatenated. **Both** `'good'` fallbacks — `renderModelRail` (`chat.html:3296`) **and** the active-mini-fit (`chat.html:3375`) — change so a missing verdict renders **`'Unknown'`, never `'good'`.** (The prior draft named only 3296; F-FAKEFIT greps for *any* fake green, so both must change.)
- **Requires:** `local_models.items` field names match the rail (`fit.verdict`, `size_gb`, `estimated_vram_gb`, `runtime`, `label`, `id`, `badge`, `warm`). Confirmed present / added by `_build_local_model_entry`.
- **Bad input:** empty `items` → existing `rail-empty` path. A deep entry with no fit → verdict copy per C4 (warmth-driven), never `'good'`.

### C3 — `_fit_verdict_label(required_gb, available_gb)` (`app.py:8116-8123`) — UNCHANGED
- **Promises:** `required_gb<=0 or available_gb<=0 → "Unknown"`; `<= avail*0.82 → "Good"`; `<= avail*1.08 → "Marginal"`; else `"Requires streaming"`. The 0.82/1.08 hysteresis bands are the anti-flicker guard (A5). We do **not** touch this function; the bug was that its output never reached the rail.

### C4 — aeroLLM / deep-entry copy — **warmth-driven, backend-accurate, Load kept**
Resolves aerollm-semantics findings 3, 5, 7 and the display half's F-OVERSELL:
- **Warmth, not `installed` (finding 3):** the badge is computed from real residency (`_tier1_resident()` for aeroLLM), not `o.installed`. Two states:
  - resident/warm → **`"resident (aeroLLM)"`**;
  - installed-but-cold (before first preload tick, or under memory pressure where preload is skipped) → **`"installed (aeroLLM) · load to warm"`**, warm-dot `cold`.
  A cold singleton must **not** claim residency — that would be the fake-green chip through the badge.
- **Load STAYS; only Unload/Eject is removed (finding 7):** VISION Decision 2 says aeroLLM-resident-because-it-fits has a real cold→WARM warm-up; "the *only* thing broken is Unload." So the deep row keeps its **Load** affordance (a genuine timed warm-up), removes **Unload/Eject**, and its cold-dot + Load + "installed (aeroLLM)" is now coherent (the prior draft's "cold dot + resident text + no Load" half-state is gone).
- **Never "streaming" for aeroLLM (F-OVERSELL):** `AERO_MOE_SELECT` (selective expert-streaming) is off and absent from `src/`; no aeroLLM row/header/badge/note may say "streaming"/"selective expert-streaming"/"SSD (streamed)"/"bit-exact". The exhaustive site list is enumerated in impl-order step 4.
- **AirLLM is AirLLM, not aeroLLM (finding 5):** a deep row's runtime is `o.id ∈ {aerollm, airllm}`. Copy uses the **row's actual backend**: `"resident (aeroLLM)"` vs `"resident (AirLLM)"` (or backend-neutral `"resident (<backend>)"`). We do **not** stamp aeroLLM copy onto an airllm row, nor "Layer-streamed via AirLLM" onto an aeroLLM row (the existing reverse smear at `chat.html:2076/3306`).
- **Preload honesty (finding 4):** the "frees on next portal restart" copy is qualified — `"frees on next portal restart (auto-preload re-warms within ~5 min if memory allows; set ARAIL_AEROLLM_PRELOAD=0 to keep it freed)"` — because `aerollm_preload_loop()` re-pins the singleton on a timer. T-RESTART runs with `ARAIL_AEROLLM_PRELOAD=0` so the free is deterministically observable (not a race against the next tick).

### C5 — `POST /api/chat/eject` (`app.py:6845-6911`) — **honest terminal return, ok tracks reality**
The prior draft said "remove the false-success interception so the honest note wins." That is **insufficient** (finding 6): the endpoint's terminal statement is an **unconditional** `return {"ok": True, "freed": freed, "notes": notes}` at `app.py:6911`. Removing the `if runtime in ("airllm","aerollm")` block only drops flow into the `elif` at 6902 that appends an honest *note* but still returns `ok:True`. **The terminal return itself must be edited.**
- **New contract — introduce `requires_restart=False` and compute `ok` at the end:**
  - `ollama` (with `model`): run `ollama stop`. **`ok = (returncode == 0 and no exception)`** — a non-zero rc or a thrown exception (daemon down, wrong model, timeout) now returns **`ok:false`** with the note, instead of the current `ok:true` (F-EJECT-OLLAMA-FALSE / F4). `freed` populated only on rc==0.
  - `airllm` | `aerollm`: **`ok=false, requires_restart=true`**, `freed=[]`, `notes=["resident (<backend>) · frees on next portal restart"]`. Uses the **row's backend name** (finding 5). Does NOT append a misleading `"<backend> cache"` to `freed` (deleting `_OPTIONAL_CHAT_BACKEND_CACHE[runtime]` frees nothing real — weights live in `AeroLLMBackend._shared` + `deep_policy._deep_router`).
  - `mlx-openai`, `mlx/cpu/cuda`: honest restart notes; `ok=false, requires_restart=true` (nothing was actually freed in-process).
  - unknown/blank (all-clear): clears the optional cache; `ok = bool(freed)`, plus a note that in-process backends need a restart.
- **Terminal return:** `{"ok": ok, "freed": freed, "notes": notes, "requires_restart": requires_restart}` — **never a bare `ok:True`.**
- **Concurrency:** all `_OPTIONAL_CHAT_BACKEND_CACHE` reads/deletes here go under the new cache lock (C6, F-CACHERACE) — the current check-then-`del` (6875-6876) and iterate-and-`del` (6907-6908) are TOCTOU races with the load path.
- **Defense in depth:** deep rows render no eject button, so this is reachable only by stale JS or a direct API call. It must still be honest when hit.

### C6 — load/unload lifecycle (`app.py:7009-7266`) — **Phase 0b, concurrency-safe + honest**
This is the half all three critiques flagged. It is **not** "wire an ETA" (§2.6 alone); it is a bounded executor-hardening. Contracts:

- **C6.1 — Initial/idle state (F-INITREADY / F7).** `_CHAT_MODEL_LOAD_STATE` initializes to **`state="idle"`, `message="No model loaded"`, `progress=0.0`, `model=None`** — not the current `state="ready", message="Model ready"` (`app.py:7012-7022`) which claims "ready" on cold start and after every restart with nothing loaded. States are exactly **`{idle, loading, ready, error}`**. There is **no `canceled` terminal state** (see C6.4).
- **C6.2 — One load at a time; concurrency-safe cache (F-CACHERACE / F6, F-LOADRACE / F3).** Add a dedicated `_CHAT_MODEL_LOAD_INFLIGHT` (async lock, capacity 1) and a `_OPTIONAL_CHAT_BACKEND_CACHE_LOCK` (threading lock). `_prepare_chat_model_load` acquires the inflight lock, then `async with scheduler.inference_slot("chat-model-load")` (serializes against `aerollm-preload`, `admin-model-load`, chat streaming at default capacity — A8). All cache mutations (load-path `[name]=backend`; eject `del`) go under the cache lock. A second Load while one is in flight is **refused** with `state=loading, message="a load is already in progress"` — not silently double-loaded.
- **C6.3 — Model-identity check (F-SWITCH / F5).** `_get_optional_chat_backend(name)` currently returns the cached instance keyed by **backend name**, ignoring the requested **model** (`app.py:7273`). It must compare the cached instance's model against the request: if they differ, it must **not** report `ready` for the wrong model. Because the singleton is single-model per `AEROLLM_MODEL` (A3) and cannot hot-swap, requesting a different aeroLLM model returns `state=error, message="aeroLLM already resident with <resident>; switching models requires a portal restart"` — an honest refusal, never a false `ready` for the previously-loaded model. *(The "doubled memory" variant in the critique assumes per-model keying of `_shared`; via `_get_optional_chat_backend` the cache is keyed by backend name, so a second construction does not occur through this path — the reachable bug is the wrong-model false-`ready`, which is what C6.3 fixes.)*
- **C6.4 — Cancel is honest: no `canceled` while a thread runs (F-CANCEL / F1).** The load runs in a non-cancellable `asyncio.to_thread` (A4). The current cancel endpoint (`app.py:7258-7266`) sets `state="canceled"` and returns while the thread keeps loading the model fully into memory — a lie of exactly the class this sprint kills. Resolution = **honest absence + honest endpoint**, mirroring §2.3:
  - The load widget renders **no Cancel affordance during a blocking load** (there is nothing we can truly cancel).
  - The endpoint, if hit, does **not** report `canceled`: it returns `{ok:false, state:"loading", note:"a load in progress cannot be interrupted; wait for it to finish, then Unload if unwanted"}`. It never claims the model was freed while the thread still holds it.
- **C6.5 — Timeout bounds harm, does not fake completion (F-TIMEOUT-ORPHAN / F2).** A wall-clock guard (`ARAIL_LOAD_MAX_SEC`, default 180) flips the **reported** state to `error` with a friendly message, **but the inflight lock (C6.2) is held until the background thread actually settles** — released in the thread's completion callback, not when the guard fires. Consequence: a timed-out load cannot be followed by a *second* Load (which is the double-residency → OOM vector on the 32 GB target). The `error` message is honest that the load may still be completing in the background and, if it does, the model can be Unloaded from the list. We do **not** claim the load stopped (we can't), and we do **not** re-enable a second load that would double memory. *(True interruptible cancellation with a completion-reconciler that auto-frees an orphaned load is a real sibling-scope change — named non-goal with a review-by date, not built here.)*
- **C6.6 — ETA basis is real bytes, degrades on corruption (F-FAKEETA / F-CORRUPT).** `eta_seconds = round(on_disk_bytes / throughput_bytes_per_sec)`, where `on_disk_bytes` comes from the model's **real on-disk/`ollama tags` size** (which the gallery already carries for installed Ollama rows), **not** the catalog manifest guess. `throughput` is a rolling median of past same-runtime loads, else a conservative default (`ARAIL_LOAD_THROUGHPUT_MBPS`, default ~500 MB/s). If real size is unknown or disagrees with the manifest beyond tolerance (partial/corrupt pull), `eta_seconds=null` and the UI shows "loading…" with no fabricated countdown. `progress` is **indeterminate** (a blocking `to_thread` load exposes no incremental signal) — spinner + ETA countdown, **never a fake filling bar**.
- **C6.7 — Fit is a click-time precondition, not a stale render-time snapshot (F-REFIT / F9).** Before initiating the load, `_prepare_chat_model_load` re-reads `_local_memory_snapshot()` and recomputes the target's verdict (the preload loop may have warmed a 7B since render). If the re-checked verdict is `Requires streaming`, the load is still allowed (operator's call) but the load-state message is honest: `"~14 GB needed, ~8 GB free — may swap or fail"`. No silent load against a stale "Marginal" chip.
- **C6.8 — Errors are operator-legible, never a raw traceback (F-DAEMONDOWN / F10).** The current `message=f"Load failed: {type(exc).__name__}: {exc}"` (`app.py:7230`) dumps a Python traceback to a non-expert, which the arail paranoid checklist forbids. Replace with a friendly message; detect the daemon-down case (connection refused / `ollama` not on PATH) → banner `"Ollama isn't running — start it with 'ollama serve', then retry."` Full traceback is logged server-side only.
- **Blocking:** chat input stays read-only until `ready` (per spec §6). No new blocking behavior beyond C6.2's single-load serialization.

### C7 — `backend_notice` (`app.py:6124-6146`) — DELETED
- The `_backend_notices` dict, the `backend_notice` variable, and the `"backend_notice"` response key are removed. The honest fit chip + `"resident (aeroLLM)"` badge supersede it. No template reads it today; deleting it removes the seventh unread field before it accretes. (§2.4.)

### C8 — References panel pointer (`chat.html:1810`) — corrected
- `src/arail/chat/gallery.py` (phantom) → `src/arail/chat/__init__.py` (`gallery_view()` / `detect_installed_models()`). Zero-cost; stops the next session re-grepping. (§2.5.)

---

## Failure modes

Every row has a test in the strategy below (test IDs in the right column double as the mapping). Rows above the divider are **display honesty (Phase 0)**; rows below are **load/unload lifecycle (Phase 0b)**.

| Failure | Detection | Recovery | Test |
|---|---|---|---|
| **F-BLANK** — `compact.hardware` undefined; telemetry `—` | Assert `d.compact.hardware.free_gb` present & numeric on cold `GET /api/chat/models` | Nest snapshot into `compact`; probe-fail → `free_gb=0` → `Unknown`+`?`, never `—`, never `Good` | T-COLD |
| **F-FALLBACKLIE** — psutil-import fallback sets `free_gb=total_gb` → fake `Good` | Force psutil import failure; assert verdict `Unknown`, not `Good`; assert `free_gb != total_gb` on fallback | Fallback leaves `free_gb=0` (Unknown); never `=total_gb` (`app.py:8164`) | T-FALLBACK |
| **F-FAKEFIT** — a `good` chip on a model whose size > free memory | Grep rendered rail for any `Good` where `estimated_vram_gb > free_gb` → 0 | Rail reads `compact.local_models.items`; **both** defaults (3296, 3375) → `Unknown` | T-FIT |
| **F-HEADER** — 26B under `≤ 8B`; deep rows under `SSD (streamed)` | Assert local header has no "8B"/"≤"; assert deep header has no "SSD"/"streamed" | `Local · GPU (≤ 8B)`→`Local · GPU` (1731/2175); `Local · SSD (streamed)`→`Local · aeroLLM` (1736/2187) + subtitle 1740, deep-header 2728 | T-HEADER |
| **F-EJECTLIE** — aeroLLM/airllm eject reports success, memory pinned | After eject: assert `ok==false`, `requires_restart==true`, `AeroLLMBackend._shared` still populated | Terminal return computes ok/requires_restart; deep rows render no eject button | T-EJECT-AERO |
| **F-OVERSELL** — copy claims "streaming"/"selective expert-streaming"/"SSD (streamed)"/"bit-exact" on aeroLLM rows while `AERO_MOE_SELECT` off | Grep rendered deep column + `models_catalog.yaml` for the full oversell string set on aeroLLM rows → 0 | Full site list corrected (impl step 4): catalog 93/111-115/126-128; chat.html 1736/1740/1817/2060/2076/2182/2187/2728/3306/3320/3722/3733/3803 | T-COPY |
| **F-MOEBASIS** — MoE fit off active-param (4B) not resident weights (13.4 GB) → falsely `Good` | Assert `gemma-4-26b-a4b` estimate ≥ disk size, not ~2 GB | `_estimate_model_memory_gb` prefers `size_gb`; test pins it | T-MOE |
| **F-DEADFIELD** — `backend_notice` **or** top-level `hardware` left unread | Grep template for `backend_notice`→0; grep response for a top-level `hardware`→0 | Delete server-side dict + key (C7); **delete** top-level `hardware` in §2.1 (C1, BLOCK-1) | T-DEADFIELD |
| **F-XSS** — model id/label/rationale injects markup | Feed id with `<img onerror>`; assert escaped in DOM | All row fields through `escapeHtml`; keep it on new fields (warm, badge, notes) | T-XSS |
| ── *load/unload lifecycle (Phase 0b)* ── | | | |
| **F-INITREADY** — cold/post-restart state claims `ready` with nothing loaded | Cold `GET /api/chat/model-load` → assert `state=="idle"`, `model==null` | Initialize state to `idle`/"No model loaded" | T-IDLE |
| **F-CANCEL** — Cancel reports `canceled` while the un-cancellable thread finishes loading | POST cancel mid-load → assert response NOT `canceled`; assert model still loads (thread not killed) and is Unloadable | Honest absence: no Cancel affordance during load; endpoint returns honest `loading` note, never `canceled` | T-CANCEL |
| **F-TIMEOUT-ORPHAN** — timeout flips state to `error`, orphan thread finishes → 2nd Load → double residency → OOM | Simulate hung load; after `ARAIL_LOAD_MAX_SEC` assert state `error` AND a 2nd Load is refused until the thread settles; assert no double residency | Inflight lock held until thread settles; timeout reports without killing or re-enabling a 2nd load | T-LOAD-BOUND |
| **F-LOADRACE** — chat load races the aeroLLM preload/admin-load toward the memory ceiling (no shared slot) | With preload active, start a heavy load; assert they serialize (one `inference_slot` holder at a time, default capacity) | `_prepare_chat_model_load` takes `scheduler.inference_slot("chat-model-load")` | T-LOADRACE |
| **F-SWITCH** — aeroLLM singleton already resident with model A; loading model B returns `ready` for A | Request a different aeroLLM model; assert `state=error` "requires restart", never `ready` for A | `_get_optional_chat_backend` checks model identity; honest refusal | T-SWITCH |
| **F-CACHERACE** — concurrent load+eject on unlocked `_OPTIONAL_CHAT_BACKEND_CACHE` → `KeyError`/500 | Hammer eject+load concurrently; assert no 500/`KeyError` | `_OPTIONAL_CHAT_BACKEND_CACHE_LOCK` around all cache mutations | T-CACHERACE |
| **F-EJECT-OLLAMA-FALSE** — `ollama stop` fails/non-zero but eject returns `ok:true` | Point at a dead daemon / wrong model; POST ollama eject → assert `ok==false` + honest note | `ok = (returncode==0 and no exception)`; terminal return not a bare `ok:true` | T-EJECT-OLLAMA-FAIL |
| **F-EJECTREAL** — Ollama eject claims success but model still resident (happy path) | Post-eject, `ollama ps` must NOT list it; RSS/VRAM drops | Keep `ollama stop`; assert real residency delta | T-EJECT-OLLAMA |
| **F-WARMDOT** — badge/dot claims `resident (aeroLLM)` while cold, or shows `cold` for a warm Ollama model | aeroLLM badge = `_tier1_resident()`; Ollama dot = live `ollama ps` — assert both track reality | Warmth is probed, not derived from `installed` / in-memory state | T-WARMDOT |
| **F-REFIT** — fit computed at render is stale by click time; load proceeds against a stale chip | Warm a 7B after render, then load; assert the load-state message reflects re-snapshot, not stale verdict | `_prepare_chat_model_load` re-snapshots + recomputes; honest message on Requires-streaming | T-REFIT |
| **F-DAEMONDOWN** — daemon-down surfaces a raw traceback; pulled models vanish silently | Kill daemon; assert the error is a friendly banner, no `Traceback`/exception-repr in the response | Friendly message + daemon-down banner; full traceback logged server-side only | T-DAEMONDOWN |
| **F-CORRUPT** — partial/corrupt model shows plausible fit + ETA until it fails | Truncate a model blob; assert fit `Unknown` + ETA `null` when real size disagrees with manifest | ETA from real on-disk/tags bytes; declared≠on-disk → `Unknown` | T-CORRUPT |
| **F-FAKEETA** — hardcoded `eta_seconds=15, progress=0.15` regardless of size | Assert `eta_seconds` scales with `on_disk_bytes`; 14 GB vs 1 GB differ | ETA = bytes/throughput; progress indeterminate (spinner), no fake bar | T-ETA |
| **F-FLICKER** — fit chip flips Good↔streaming across refreshes on idle box | Repeat `GET /api/chat/models` N× on idle box; verdict per id must be stable | 0.82/1.08 hysteresis; unstable → STOP (disconf. #3), smoothing sub-project | T-NOFLICK |
| **F-RESTART** — after portal restart, aeroLLM memory does NOT return | Baseline RSS, warm aeroLLM, restart (`ARAIL_AEROLLM_PRELOAD=0`), assert RSS returns toward baseline | Honest contract ("frees on next portal restart"); test disables preload to remove the race | T-RESTART |

---

## Test strategy

QA will execute this. Coverage on changed lines ≥ 80%. Per arail gating this touches someone-else's-machine security, so honesty/behavior tests dominate happy-path.

### Named suite: **Cold-Start / Restart / Free-Memory ("Persistence & Honesty")**
The mandated cross-process, real-OS suite for the bug class found twice this session (unbounded warm-up ping; lying eject). Not satisfied by "the UI didn't crash." Runs on the operator's own airgapped Mac and asserts screen-vs-terminal agreement.

- **T-COLD** — fresh portal, first `GET /api/chat/models`. Assert `compact.hardware.free_gb` numeric, within ±1 GB of `psutil.virtual_memory().available` / `nvidia-smi memory.free` at the same instant. No `—`, no fabricated value. *(F-BLANK)*
- **T-FALLBACK** — monkeypatch psutil import to fail; assert the darwin fallback yields `free_gb=0`→verdict `Unknown` (never `free_gb==total_gb`→`Good`). *(F-FALLBACKLIE)*
- **T-FIT** — with `gemma-4-26b-a4b` installed, its verdict ∈ {Marginal, Requires streaming, Unknown}, never `Good`; global invariant: no rendered `Good` has `estimated_vram_gb > free_gb`. Covers both the rail (3296) and active-mini (3375). *(F-FAKEFIT)*
- **T-HEADER** — local header has no "8B"/"≤"; **deep header has no "SSD"/"streamed".** *(F-HEADER, both twins)*
- **T-EJECT-OLLAMA** — load an Ollama model, confirm via `ollama ps`, POST eject, assert `ollama ps` no longer lists it AND footprint dropped. *(F-EJECTREAL)*
- **T-EJECT-OLLAMA-FAIL** — point ollama eject at a dead daemon / wrong model; assert `ok==false` + honest note (not `ok:true`). *(F-EJECT-OLLAMA-FALSE)*
- **T-EJECT-AERO** — assert the deep row renders **no** eject button; POST eject `{runtime:'aerollm'}` and `{runtime:'airllm'}` directly; assert `ok==false`, `requires_restart==true`, the note names the **correct backend**, and `_shared` still holds the instance. *(F-EJECTLIE, finding 5)*
- **T-RESTART** — with `ARAIL_AEROLLM_PRELOAD=0`: record RSS baseline, warm aeroLLM, record elevated RSS, restart, assert RSS returns toward baseline. *(F-RESTART, finding 4 — preload disabled so it's not a race)*
- **T-WARMDOT** — aeroLLM cold (before preload) → badge "installed (aeroLLM)", dot cold; after warm → "resident (aeroLLM)". Warm an Ollama model, `ollama stop` it out-of-band, refresh → dot flips to cold from the live `ollama ps` probe. *(F-WARMDOT)*
- **T-IDLE** — cold `GET /api/chat/model-load` → `state=="idle"`, `model==null`; never `"ready"`/"Model ready" with nothing loaded. *(F-INITREADY)*
- **T-CANCEL** — start a load, POST cancel mid-flight; assert the response is NOT `canceled`, the thread still completes (model becomes resident and Unloadable), and no UI Cancel affordance was offered during the blocking load. *(F-CANCEL)*
- **T-LOAD-BOUND** — simulate a hung load (black-hole port / patched sleep); assert state reaches `error` within `ARAIL_LOAD_MAX_SEC`, a **second** Load is refused until the thread settles, and no double residency occurs. *(F-TIMEOUT-ORPHAN)*
- **T-LOADRACE** — with the preload loop active (or a stubbed `aerollm-preload` slot holder), start a chat load; assert only one `inference_slot` holder runs at a time (they serialize, default capacity 1). *(F-LOADRACE)*
- **T-SWITCH** — with aeroLLM resident on model A, request a load of aeroLLM model B; assert `state=error` "requires restart", never `ready` reporting A. *(F-SWITCH)*
- **T-CACHERACE** — concurrently fire eject + load against `_OPTIONAL_CHAT_BACKEND_CACHE`; assert no 500 / `KeyError`. *(F-CACHERACE)*
- **T-REFIT** — render, then warm a 7B out-of-band, then load a Marginal model; assert the load-state message reflects the re-snapshot (honest "may swap/fail"), not the stale render-time chip. *(F-REFIT)*
- **T-DAEMONDOWN** — kill the ollama daemon, attempt a load; assert the operator-facing error is a friendly banner with no `Traceback`/exception-repr, and the full traceback is only in the server log. *(F-DAEMONDOWN)*
- **T-CORRUPT** — truncate a model's on-disk blob so real size ≠ manifest; assert fit `Unknown` and `eta_seconds==null`, no fabricated countdown. *(F-CORRUPT)*
- **T-NOFLICK** — 20 consecutive `GET /api/chat/models` on an idle box; verdict per id identical across all 20. Flip → disconfirming-evidence #3; STOP and open the smoothing sub-project. *(F-FLICKER)*

### Unit
- `_fit_verdict_label` boundary table at `0.82*avail`, `1.08*avail`, `0`, negative → {Good, Marginal, Requires streaming, Unknown}. *(C3)*
- `_local_memory_snapshot` fallback: psutil-fail path returns `free_gb=0` (not `total_gb`). *(F-FALLBACKLIE)*
- `_estimate_model_memory_gb` MoE: `gemma-4-26b-a4b` `size_gb=14.4` → estimate ≥ 14.4. *(F-MOEBASIS)*
- ETA derivation: monotonic in `on_disk_bytes`; 14 GB vs 1 GB differ; unknown/disagreeing size → `null`. *(F-FAKEETA, F-CORRUPT)*
- `_get_optional_chat_backend` identity: cached model A + request B → refusal, not A. *(F-SWITCH)*
- eject per-runtime contract: table over {ollama-ok, ollama-fail, aerollm, airllm, mlx-openai, blank} asserting `ok`/`freed`/`requires_restart`. *(F-EJECTLIE, F-EJECT-OLLAMA-FALSE)*

### Integration
- `GET /api/chat/models`: `compact.hardware` present, `local_models.items[*].fit.verdict` present, `backend_notice` **absent**, **no top-level `hardware`**. *(C1, C7, F-DEADFIELD)*
- Frontend render (jsdom/Playwright): `State.models` from `compact.local_models.items`; a row missing `fit` renders `Unknown`, never `Good`; a cold aeroLLM row renders "installed (aeroLLM)" + Load, no Unload. *(C2, C4)*

### Regression
- **F8 regression:** grep built template + server response for `backend_notice` → 0, and for a top-level `hardware` key → 0. *(T-DEADFIELD)*
- **`AERO_MOE_SELECT` overstatement:** grep `models_catalog.yaml` + rendered deep column for the full oversell string set on aeroLLM rows → 0. *(T-COPY)*
- **Re-run the exact live in-browser test** that surfaced the lies this session (VISION pre-committed pass/fail). If any of header / fake fit / blank telemetry / lying eject / **lying Cancel** still shows → wedge failed, does not ship.

### Performance
- Not a hot path. Guard: `GET /api/chat/models` p95 within +10% of baseline (added nesting is an O(1) re-key; the `ollama ps` warmth probe must be cached/short-timeout so it does not add latency on the request path — probe with a ≤1 s timeout, fall back to last-known on timeout). The derived-ETA computation is arithmetic, non-blocking.

### Security
- **T-XSS** — id/label/rationale/notes with `<img src=x onerror=alert(1)>` render escaped; new fields (fit summary, headroom copy, warm, backend notes) go through `escapeHtml`. *(F-XSS)*
- No new user-input surface, no auth change, no new dependency. The only subprocess is `ollama stop <model>` — `model` is validated by `_validate_local_model_id_relaxed` and passed as an argv element (not a shell string); confirm it stays validated before `subprocess.run`. New cache/inflight locks introduce no new I/O.

---

## Tech debt

| Added | Repaid |
|---|---|
| ETA uses a coarse throughput default until a rolling median accumulates — approximate for the first few loads. Bounded and honest (countdown, not a fake bar). **The spec's ±20% NVMe-probe accuracy target is DESCOPED, not deferred** (see INFO-6 resolution) — the derived ETA is the shipped behavior; there is no owed ±20% probe and no phantom follow-up. | **§2.1** telemetry blank fixed — snapshot nested (and top-level `hardware` deleted, not lingering). |
| At `ARAIL_INFERENCE_CONCURRENCY>1`, chat load + preload + admin load can co-run (shared semaphore, capacity>1) — a **pre-existing** scheduler property (admin+preload already share it), not introduced here. **Review-by 2026-08-10** (backstop; the default capacity=1 path is safe via C6.2). | **§2.2** root-cause fixed — rail reads the list with real fit; the `'good'` default dies (both sites). |
| Timeout bounds *harm* (no double residency) but does not truly interrupt the thread; a timed-out load may still finish and become resident (Unloadable). True interruptible-cancel-with-reconciler is a named non-goal. | **§2.3** lying eject removed — honest absence + honest terminal return (ok tracks reality for ollama; ok:false+requires_restart for aerollm/airllm). |
| | **§2.4 / F8** dead `backend_notice` deleted (repays 6-week debt). |
| | **§2.5** phantom `gallery.py` pointer corrected. |
| | **§2.6** hardcoded ETA → derived ETA (real on-disk bytes); six-state doc trimmed to `{idle,loading,ready,error}`. |
| | **Header lies** (`≤ 8B` **and** `SSD (streamed)`), **Cancel lie**, **fallback lie**, **daemon-down traceback**, **cache race**, **load race** — all closed. |

**Net: strongly negative (debt repaid).** The six gaps (§2.1–2.6) plus the header/Cancel/eject/fallback/race lifecycle lies are closed; the only debt added is an approximate-until-warmed ETA (an honest improvement over a hardcoded constant) and the operator-opt-in high-concurrency co-residency (pre-existing, dated).

> **No env-flag dormant lane is added.** The prior draft listed a "reserved non-goal hook for frontier layer-streaming" in this column — **removed.** See non-goal "aeroLLM true frontier layer-streaming": the concept is named in prose only, with **no `AERO_MOE_SELECT`-gated code and nothing reserved in `src/`** (BLOCK-2 resolution). Naming a concept in a doc is not a dormant lane; a flag-gated code path would be, and none is added.

### Folded into this sprint (was a discovered out-of-scope item)
- **Gemma license mislabel — the false claim is corrected THIS sprint; the full disclosure package is a dated hand-off.** `models_catalog.yaml:238-239` describes `gemma-4-26b-a4b` as "official QAT q4_0 GGUF (**Apache-2.0**)". Gemma ships under the **Gemma Terms of Use**, not Apache-2.0 (workspace CLAUDE.md "Gemma disclosure exception"; license/attribution is on the paranoid checklist). This is a copy-honesty falsehood of exactly the class win-condition #4 targets, and **impl step 4 already edits this file** — so the false token is corrected now: `"(Apache-2.0)"` → `"Built with Gemma · Gemma Terms of Use (ai.google.dev/gemma/terms)"`. Test T-COPY's grep extends to assert no Gemma row is labeled "Apache-2.0". **The remaining full-disclosure compliance for this catalog entry** (NOTICE bundling, `licenses/GEMMA-*` files, verbatim §3.1(4) notice, whether a browse-gallery entry needs the same package as the default-floor model) is a genuinely larger job than a string edit. **Owner: architect (license/disclosure). Date: 2026-08-10 (a real calendar date, not an event).** This is no longer an undated deferral of a live false claim — the false claim dies this sprint; only the compliance-completeness audit is dated. *(This supersedes the prior draft's self-labeled-"dated"-but-undated "G1 or next catalog sprint, whichever first" deferral, which ASK-3 correctly flagged: "G1" was also a category error — G1 arms the `qkz-project-aware-2b` 2B default-floor, a different model from this 26B catalog entry.)*

---

## Explicit resolution of the six-gap brief (§2.3, §2.4, §2.6) + the load-lifecycle critiques

Resolved *here, in design*, not left open. (The brief lives in VISION.md → "Wedge"; there is no committed `PROMPT.md`.)

**§2.3 — aeroLLM eject honesty → REMOVE THE (UN)LOAD-BUTTON LIE, KEEP THE REAL LOAD.**
The singleton cannot be hot-freed this sprint (A3). Decision:
1. Deep rows render **no Unload/Eject** affordance; they **keep Load** (a real cold→WARM warm-up per VISION Decision 2 — the prior draft wrongly removed Load too). Expand copy: `"resident (aeroLLM) · frees on next portal restart (auto-preload re-warms within ~5 min unless ARAIL_AEROLLM_PRELOAD=0)"`.
2. Endpoint (C5) computes an honest terminal return — **editing the unconditional `return {"ok": True}` at `app.py:6911`**, not merely removing an interception (finding 6). aerollm/airllm → `ok:false, requires_restart:true`, backend-accurate note (finding 5). ollama → `ok = (returncode==0)` (F4).
Satisfies win-condition #3; disconfirming-evidence #4 is the tripwire.

**§2.4 — `backend_notice` fate → DELETE THE DEAD CODE.** Remove `_backend_notices`, `backend_notice`, the response key (`app.py:6124-6146`). Regression grep asserts zero occurrences so it cannot return as field #7. (C7.)

**§2.6 — six-state load machine → TRIM THE DOC + a real, concurrency-safe executor.** Do **not** build the six-state machine. `docs/maximus.plan.md §5` is edited to document the states that actually ship: **`idle → loading → ready | error`** (no `canceled` terminal state — Cancel is honest-absence, C6.4). ETA is derived from real on-disk bytes (C6.6). The executor is hardened for concurrency/timeout/identity (C6.1–C6.8). Doc and code agree; no third undocumented behavior.

**Load-lifecycle critiques (F1–F12) → each mapped in the ledger below.** The key correction vs the first draft: the load/unload half was under-audited and about to ship a Cancel lie (F1) and an Ollama-eject-fail lie (F4) of the exact class this sprint exists to kill. Those, plus the timeout OOM path (F2), the un-serialized load (F3), the wrong-model false-ready (F5), and the cache race (F6), are now closed contracts (C5, C6), gated as Phase 0b.

---

## Non-goals (every deferral has owner + trigger **and** a review-by date — never undated)

Per disconfirming-evidence #5 (the attempt-#7 tripwire): every deferral has an owner, a reopen trigger, **and a review-by date** as the did-the-trigger-actually-fire backstop. A trigger alone is an event that may never fire — precisely the void this sprint documents; the date catches it. Any REVIEW.md follow-up lacking all three blocks ship.

- **New Models tab / any net-new surface** — gated behind disconfirming-evidence #1 (fidelity ships and the operator still can't decide in <10s). Reopen with data, not a guess. **Owner: visionary. Trigger: disconf-#1 fires post-Phase-0. Review-by: 2026-08-10.**
- **Agent-binding editor UI** — this sprint surfaces tiering as a **read-only chip only** ("serves: fast"). No editor. **Owner: visionary. Review-by: 2026-08-10.**
- **The read-only "serves: <tier>" chip itself, if cut** — it is the first thing cut if the wedge overruns, and it is the *entire* surviving footprint of the brief's ask that agent tier-consumption be operator-visible. **If cut, it does NOT vanish undated:** it lands under the same visionary slot. **Owner: visionary. Trigger: cut for scope. Review-by: 2026-08-10.** (Resolves ASK-5 — "first to cut" must not mean "silently dropped.")
- **"Symbolic chain of thought / knowledge tiering" vision** — exists nowhere in code; new vision on top of `resolve()`. **Owner: visionary. Review-by: 2026-08-10.**
- **aeroLLM true frontier layer-streaming (`AERO_MOE_SELECT`)** — off and absent from `src/`. **No fake Load/Unload/WARM, and — per BLOCK-2 — NO reserved code hook and NO `AERO_MOE_SELECT`-gated code path.** The concept is named **in prose only**; if/when the flag ships real code in the aerollm repo, reopen with a fresh visionary/architect pass. **Owner: architect (cross-repo). Trigger: `AERO_MOE_SELECT` ships real code in aerollm `src/`. Review-by: 2026-08-10.**
- **Real aeroLLM singleton hot-free + true interruptible cancel/reconciler** — requires a sibling-repo (Rust runtime) change to guarantee Drop→Metal-free plus preload-loop coordination; the completion-reconciler that auto-frees an orphaned/canceled load rides on it. **Owner: architect + operator. Trigger: disconf-#4 fires (honest-absence proven worse than the lie). Review-by: 2026-08-10.**
- **Nucleus ↔ aeroLLM integration** — net-new Nucleus-side work; graduated artifacts already appear via `register-artifact` tagged `"fast"` and get the same real fit chips (zero-cost, in scope). Bidirectional consumption is out. **Owner: architect (cross-repo) + operator (priority). Trigger: aeroLLM ships HTTP bindings. Review-by: 2026-08-10.**
- **`ARAIL_INFERENCE_CONCURRENCY>1` heavy co-residency** — pre-existing scheduler property; default capacity=1 is safe (C6.2). **Owner: architect. Review-by: 2026-08-10.**
- **Gemma full-disclosure compliance package** — see Tech debt (folded item). The false Apache-2.0 label is fixed this sprint; the NOTICE/`licenses/`/§3.1(4) package is dated. **Owner: architect. Date: 2026-08-10.**

---

## Recommended implementation order

**Phase 0 (display fidelity)** ships as its **own PR, first** — the ~80% that is deletions and wiring. **Phase 0b (load/unload lifecycle)** is a **second, small-but-real PR** that must land before any load-widget/ETA UI is trusted. Neither is smuggled into the other; the split matches the three critiques' shared conclusion (display half is safe to build; load/unload half needed the contracts above first).

### Phase 0 — display fidelity (own PR)
1. **§2.1 — nest the snapshot AND delete the top-level key** (`app.py:7811-7839` + the top-level emission ~`7865`): put `memory_snapshot` into `compact.hardware`; **delete** the top-level `hardware` in the same edit (BLOCK-1). Land T-COLD + the F-DEADFIELD "no top-level hardware" grep. Also close the psutil-fallback lie (`app.py:8164`, F-FALLBACKLIE) — land T-FALLBACK.
2. **§2.2 — point the rail at the truthful list** (`chat.html` ~3707 + defaults at **3296 and 3375**): `State.models = d.compact.local_models.items`, preserve the `deepEntries` fold, change **both** `'good'` defaults to `'Unknown'`. Land T-FIT. **HARD GATE: if this is not a cheap data-source swap, STOP and report (disconf-#2).**
3. **§2.2 headers — both twins** (`chat.html:1731/2175` and `1736/2187` + subtitle 1740 + deep-header 2728): `Local · GPU (≤ 8B)`→`Local · GPU`; `Local · SSD (streamed)`→`Local · aeroLLM`. Land T-HEADER.
4. **§3 / F-OVERSELL copy — full site sweep** (not one site): correct every aeroLLM-attributed streaming claim so T-COPY (which greps *all* of them) can pass. Sites — `models_catalog.yaml`: 93 (comment), 111-115 (comment "native selective … 32 experts / 4 active, bit-exact"), 126-128 (`gpt-oss-20b` "native selective expert-streaming"→"resident (aeroLLM)"); `chat.html`: 1740, 1817, 2060, 2076/3306 (streamed-badge), 2182/2187, 2728, 3306/3320, 3722 (deepEntries verdict `o.installed?'streaming'`→warmth-driven per C4), 3733, 3803. **Also fold the Gemma license fix** here (line 238-239 `(Apache-2.0)`→`Built with Gemma · Gemma Terms of Use`). Land T-COPY.
5. **§2.3 — honest eject (endpoint + no deep-row button)** (`app.py:6845-6911`): **edit the terminal `return {"ok": True}`** to compute `ok`/`requires_restart` per C5 (ollama `ok=(rc==0)`; aerollm/airllm `ok:false`+restart, backend-accurate note); remove the eject button on deep rows; **keep the Load button** (C4/finding 7). Land T-EJECT-AERO, T-EJECT-OLLAMA-FAIL; keep T-EJECT-OLLAMA green.
6. **§2.4 — delete `backend_notice`** (`app.py:6124-6146`). Land T-DEADFIELD.
7. **§2.5 — fix References pointer** (`chat.html:1810`): phantom `gallery.py`→`__init__.py`.
8. **Warmth probe** (`_build_local_model_entry` + deep badge): Ollama rows carry `warm` from a short-timeout `ollama ps` probe; aeroLLM badge from `_tier1_resident()` (C4/F-WARMDOT). Land T-WARMDOT.
9. **Run Persistence & Honesty (display subset)** + the live four-lies re-run. Green → Phase 0 ships.

### Phase 0b — load/unload lifecycle honesty (second PR; HARD GATE)
10. **Idle state + locks** (`app.py:7009-7022`, cache + inflight): initialize `state="idle"` (C6.1); add `_OPTIONAL_CHAT_BACKEND_CACHE_LOCK` (C6.2/F-CACHERACE) and `_CHAT_MODEL_LOAD_INFLIGHT` (C6.2). Land T-IDLE, T-CACHERACE.
11. **Serialize the load** (`app.py:7191-7215`): wrap in `scheduler.inference_slot("chat-model-load")` (C6.2/F-LOADRACE). Land T-LOADRACE.
12. **Honest Cancel + bounded timeout** (`app.py:7258-7266` + `_prepare_chat_model_load`): no Cancel affordance during load; endpoint stops reporting `canceled` (C6.4/F-CANCEL); wall-clock guard reports `error` while holding the inflight lock until the thread settles (C6.5/F-TIMEOUT-ORPHAN). Land T-CANCEL, T-LOAD-BOUND.
13. **Model identity + real ETA + re-snapshot + friendly errors** (`app.py:7269-7281`, `7191-7237`): `_get_optional_chat_backend` identity check (C6.3/F-SWITCH); ETA from real on-disk bytes with corrupt-degrade (C6.6/F-CORRUPT, F-FAKEETA); re-snapshot fit at load time (C6.7/F-REFIT); friendly error + daemon-down banner, no traceback (C6.8/F-DAEMONDOWN); trim `docs/maximus.plan.md §5` to `{idle,loading,ready,error}`. Land T-SWITCH, T-ETA, T-CORRUPT, T-REFIT, T-DAEMONDOWN.
14. **Run the full Persistence & Honesty suite** (all T-* incl. T-RESTART with `ARAIL_AEROLLM_PRELOAD=0`). Green and no remaining lying affordance → Phase 0b ships.

Then, **strictly inside the one Chat-tab list** (only after 0 and 0b hold): the expand-for-numbers content per row and the read-only "serves: <tier>" chip (first to cut, dated fallback above). **Nothing else** — tab restructure, binding editor, streaming UI, Nucleus integration are the named non-goals.

**Hard gate restated:** if Phase 0 cannot close (§2.2 needs a real refactor — disconf-#2 — or the fit chip flickers — disconf-#3) **or Phase 0b's executor is bigger than the C6 contracts size it**, **stop and say which gap held.** Additive UI (or a load widget) on a lying floor is exactly how this becomes attempt #7.

---

## Critique-resolution ledger

Every finding from the three pre-build critiques is fixed or explicitly justified — nothing silently dropped.

### failure-modes (F1–F12) + ground-truth note
- **Ground-truth citation** — FIXED. Header no longer cites a non-existent `PROMPT.md`; the six-gap `§`-labels are re-anchored to VISION.md "Wedge".
- **F1 Cancel lie** — FIXED (C6.4): honest absence; endpoint never reports `canceled` while the thread runs; new F-CANCEL row + T-CANCEL.
- **F2 timeout fights orphan → double-residency OOM** — FIXED (C6.5): inflight lock held until the thread settles; no second load; T-LOAD-BOUND asserts no double residency, not just `state=error`.
- **F3 load races preload, no shared slot** — FIXED (C6.2, A8): load takes `inference_slot("chat-model-load")`, serializing against `aerollm-preload`/`admin-model-load` at default capacity; `>1` is operator opt-in, dated. F-LOADRACE + T-LOADRACE.
- **F4 ollama eject ok:true on failure** — FIXED (C5): `ok = (returncode==0)`; terminal return no longer bare `ok:true`. F-EJECT-OLLAMA-FALSE + T-EJECT-OLLAMA-FAIL. (Prior "ollama Unchanged" corrected.)
- **F5 aeroLLM singleton already constructed → wrong-model ready** — FIXED (C6.3): identity check; honest refusal. Double-memory variant justified as unreachable via `_get_optional_chat_backend` (keyed by backend name). F-SWITCH + T-SWITCH.
- **F6 concurrent load+unload cache race** — FIXED (C6.2/C5): `_OPTIONAL_CHAT_BACKEND_CACHE_LOCK`. F-CACHERACE + T-CACHERACE.
- **F7 initial/post-restart false `ready`** — FIXED (C6.1): `idle` state. F-INITREADY + T-IDLE.
- **F8 restart: portal vs daemon disagree; warm-dot** — FIXED (C4/step 8): warm-dot derived from live `ollama ps` (Ollama) and `_tier1_resident()` (aeroLLM). F-WARMDOT + T-WARMDOT.
- **F9 near-OOM: fit stale at click time** — FIXED (C6.7): re-snapshot + recompute before load; honest message. F-REFIT + T-REFIT.
- **F10 daemon-down raw traceback** — FIXED (C6.8): friendly message + banner; traceback server-side only. F-DAEMONDOWN + T-DAEMONDOWN.
- **F11 corrupt/partial model looks loadable** — FIXED (C6.6/C1): ETA from real on-disk bytes; declared≠on-disk → `Unknown`/`null`. F-CORRUPT + T-CORRUPT.
- **F12 snapshot fallback lies (`free_gb=total_gb`)** — FIXED (A2/C1): fallback leaves `free_gb=0`→`Unknown`. F-FALLBACKLIE + T-FALLBACK.

### scope-creep-and-follow-ups
- **BLOCK-1 top-level `hardware` lingers** — FIXED: deleted in §2.1/step 1 (C1); F-DEADFIELD greps it. "Prefer deleting" → deleted now.
- **BLOCK-2 reserved streaming hook = dormant lane** — FIXED: removed from Tech-debt "Added"; no `AERO_MOE_SELECT`-gated code, nothing reserved in `src/`; concept named in prose only; non-goal carries a review-by date.
- **ASK-3 Gemma mislabel "dated" but undated** — FIXED: the false Apache-2.0 label is corrected THIS sprint (step 4); the full disclosure package is a real dated hand-off (2026-08-10, architect). Stopped calling it "dated" without a date; dropped the "G1 or next catalog sprint" double-event (also a G1 category error).
- **ASK-4 four event-gated non-goals lack dates** — FIXED: every non-goal now carries a review-by date (2026-08-10) as the did-it-fire backstop, event kept as reopen condition.
- **ASK-5 "serves" chip cut is silently dropped** — FIXED: cut path routed to owner + dated slot (visionary / 2026-08-10).
- **INFO-6 ETA ±20% accuracy ambiguity** — FIXED: ±20% NVMe-probe target **descoped explicitly** (not deferred, no phantom follow-up); derived ETA is the shipped behavior; the "if a probe is added" hedge is removed from Performance/§2.6/Tech-debt.

### aerollm-semantics-fidelity
- **1 oversell scoped to 1 of ~13 sites** — FIXED: step 4 enumerates the full site set; T-COPY greps all.
- **2 `SSD (streamed)` header twin left standing** — FIXED: F-HEADER/step 3 kill both headers.
- **3 badge keyed off `installed` not warmth** — FIXED (C4): badge from `_tier1_resident()`; cold → "installed (aeroLLM)", warm → "resident (aeroLLM)".
- **4 "frees on restart" undercut by preload; T-RESTART races it** — FIXED (C4/T-RESTART): copy qualified with the preload caveat; test runs `ARAIL_AEROLLM_PRELOAD=0` for determinism.
- **5 AirLLM mislabeled as aeroLLM** — FIXED (C4/C5): copy uses the row's actual backend name; no aeroLLM stamp on airllm rows and vice-versa.
- **6 C5 mechanism won't produce ok:false** — FIXED (C5): the terminal `return {"ok": True}` is edited to compute `ok`/`requires_restart`; "remove the interception" alone was insufficient.
- **7 C4 removes Load, contradicting §3/VISION** — FIXED (C4): Load KEPT (real warm-up); only Unload/Eject removed; cold-dot + Load + "installed (aeroLLM)" is coherent.
- **8 reserved hook unspecified (dormant lane)** — FIXED: same as BLOCK-2; prose-only concept, no code, dated review.
