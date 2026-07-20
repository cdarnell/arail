# Architecture: Model selection UX — unified-list fidelity, disclosed honestly

**Date:** 2026-07-20
**Spec:** [VISION.md](./VISION.md) at `8b2c9cab334a05ab440d04185cbf024d7aae70f2`
**Ground truth:** [PROMPT.md](../../../../../sprints/2026-07-20-model-ux-unification/PROMPT.md) (§2 gaps, §3 backend semantics, §5 phase plan)
**Mode:** design
**Leash:** Phase 0 (fidelity floor) ships as its own PR first. Additive UI is gated behind disconfirming-evidence #1. If §2.2 needs a real refactor, stop and report — do not expand quietly.

---

## Restatement

This is attempt #6 at the same screen, and the previous five all died the same way: correct backend truth about memory/fit is computed server-side, never reaches the DOM, gets filed as a "follow-up," and the next sprint redesigns the layout from a blank page. The one Chat-tab model list currently shows **five simultaneous false claims** — a `Local · GPU (≤ 8B)` header over a 26B model, a green `good` fit chip on that 26B (frontend defaults every missing verdict to `'good'`), `—` for free RAM/VRAM (the snapshot is computed but nested one level too high in the payload), an Eject button that returns `{"ok": true}` while the multi-GB aeroLLM singleton stays pinned, and a `backend_notice`/catalog copy that oversells a streaming capability (`AERO_MOE_SELECT`) that is off and absent from `src/`. Every one of those is backed by *correct code that never renders*. The deliverable is **truthfulness of the list that already exists** — wire the computed truth to the screen, delete the lies that can't be made true this sprint, and keep it one list in the Chat tab (no new tab). No new surface until fidelity is proven insufficient. If I can't restate it, the four things that must be honest are: **fit chip, free-memory line, Unload button, and backend badge copy.**

---

## Assumptions

Hidden assumptions kill systems. These are the ones this design rests on; each has a failure-mode row and a test.

1. **A1 — `gallery.installed` and `compact.local_models.items` share one source.** Confirmed: `local_entries` is built by iterating `gallery.get("installed", [])` (`app.py:7773-7786`) and enriching each row with `_build_local_model_entry` (which adds the real `fit`). So the "two lists" are one list, one enriched. This is what makes §2.2 cheap. **If this were two independently-sourced lists, the "one sprint, mostly wiring" premise would be wrong** (disconfirming-evidence #2 → stop and re-scope).
2. **A2 — `_local_memory_snapshot()` reflects real OS truth within ±1 GB at read time.** It reads `psutil.virtual_memory()` (Apple Silicon unified memory) or `nvidia-smi` (CUDA). We assume `psutil` is installed (it is a hard dep). On macOS the `available` field is the honest free figure operators compare against Activity Monitor.
3. **A3 — the aeroLLM singleton cannot be hot-freed this sprint.** Freeing it requires clearing three caches (`AeroLLMBackend._shared[key]`, `deep_policy._deep_router`, `_OPTIONAL_CHAT_BACKEND_CACHE`), coordinating with the `model_warmth.py` preload loop (which re-warms within `ARAIL_AEROLLM_PRELOAD_INTERVAL_SEC`, default 300s, whenever `metal_memory_pressure() < 0.60`), and trusting the Rust `Runtime`'s Drop to actually release Metal memory — none verified this session. `_close()` exists (`backends.py:1647-1662`) but is `atexit`-registered only. **We design honest-absence, not hot-free.**
4. **A4 — the Ollama load path is now bounded.** Recent commits bounded the warm-up ping (`think:false` + `num_predict`). We assume `_get_runtime_backend(...)` cannot hang indefinitely. The load state machine adds a defense-in-depth timeout regardless (see failure mode F-LOAD-HANG).
5. **A5 — free-memory readings are stable enough to render a non-flickering verdict** on an idle machine. If they jitter enough to flip a chip between `Good` and `Requires streaming` across refreshes, that is a *new* lie (disconfirming-evidence #3) and forces a smoothing sub-project before any chip ships. We assume the ±0.82/±1.08 hysteresis bands in `_fit_verdict_label` already absorb normal churn; the test T-NOFLICK verifies it.
6. **A6 — MoE resident footprint ≈ full quantized weights on disk.** `gemma-4-26b-a4b` is 26.5B total / ~4B active, but Ollama loads *all* experts resident (~13.4–14.4 GB q4). The honest memory number is the disk/weights figure, not the active-param figure. We assume `size_gb`/`expected_disk_gb` is the right basis for the estimate (it is — `_estimate_model_memory_gb` prefers it).
7. **A7 — no operator relies on the current false `{"ok": true}` eject response** as a scripting contract. Changing it to an honest `ok:false` for aerollm/airllm is a behavior change we accept.

---

## Data flow

```
                          ┌─────────────────────────────────────────────┐
   OS truth               │  _local_memory_snapshot()  app.py:8145      │
   (psutil / nvidia-smi)──►  {label,total_gb,used_gb,free_gb,gpu_label} │
                          └───────────────┬─────────────────────────────┘
                                          │ free_gb
   ollama /api/tags ─┐                    ▼
   mlx dir scan      ├─► gallery_view() ─► gallery.installed[]  ── same source ──┐
   mlx-openai server ┘   (chat/__init__)   {id,runtime,size_gb,modified,endpoint}│
                                                                                 ▼
                          ┌──────────────────────────────────────────────────────────┐
                          │ _build_local_model_entry()  app.py:8243                    │
                          │   estimate_gb = _estimate_model_memory_gb(size_gb|params)  │
                          │   verdict     = _fit_verdict_label(estimate_gb, free_gb)   │  ◄── REAL fit
                          │   → local_entries[] each carrying .fit{verdict,summary,…}  │
                          └───────────────┬──────────────────────────────────────────┘
                                          ▼
   GET /api/chat/models  ──►  compact_selector = {
                                  local_models.items = local_entries,   ← has fit
              §2.1 FIX  ────────► hardware           = memory_snapshot,  ← NEW nesting
                                  compute_sources, ... }
                              + top-level: gallery, optional_backends, model_load, ...
                                          │
   ══════════════════ NETWORK BOUNDARY (JSON) ══════════════════
                                          │
   chat.html initModels()                 ▼
   OLD: State.models = d.gallery.installed        (no fit → line 3296 defaults 'good')  ✗ LIE
   NEW: State.models = d.compact.local_models.items                                     ✓ real fit
        + concat deepEntries(optional_backends)  → badge:'deep', verdict "resident (aeroLLM)", NO eject
                                          │
                                          ▼
   renderModelRail()  →  per-row: warm-dot · name · size · [fit-chip=real] · WARM/cold
                         local column header: "Local · GPU"  (NO "≤ 8B")  §2.2 header fix
                         expand → free RAM/VRAM, keep_alive, load ETA (progressive-disclosure content)
   telemetry: tele-hw/tele-vram ← d.compact.hardware   §2.1 (was undefined)

   ──── Unload path ────
   Ollama row  → POST /api/chat/eject {runtime:'ollama',model} → `ollama stop` → REAL free  ✓
   aeroLLM row → NO eject button rendered.  Endpoint, if hit: {ok:false, requires_restart:true,
                 notes:["resident (aeroLLM) · frees on next portal restart"]}  §2.3 honest

   ──── Load path ────
   POST /api/chat/model-load → _prepare_chat_model_load
        eta_seconds = on_disk_bytes / throughput_estimate   §2.6 (was hardcoded 15)
        states: loading → ready | error | canceled   §2.6 (doc trimmed from 6 states)
        bounded by timeout (F-LOAD-HANG)
```

---

## Interface contracts

### C1 — `compact_selector` payload (`app.py:7811-7839`)
- **Promises:** returns a dict that now nests `hardware` (the same object currently returned top-level at `app.py:7865`). `compact.local_models.items` continues to carry `_build_local_model_entry` rows, each with a real `fit.verdict ∈ {Good, Marginal, Requires streaming, Unknown}` derived from real `free_gb`.
- **Requires:** `memory_snapshot` computed before `compact_selector` is assembled (already true — `app.py:7772`).
- **Bad input:** if `_local_memory_snapshot()` returns `free_gb == 0` (probe failed), `_fit_verdict_label` returns `"Unknown"` (not `Good`) — telemetry shows the raw label + `?`, never a fabricated number. The top-level `hardware` key MAY remain for one release for back-compat but the nested one is authoritative; prefer removing the top-level to avoid a second unread field (see Tech debt).

### C2 — rail data source (`chat.html` initModels ~3707, renderModelRail 3280-3324)
- **Promises:** `State.models` for the local/Ollama column is sourced from `d.compact.local_models.items` (real `fit`), then `deepEntries` (aeroLLM/airllm from `optional_backends`) are concatenated with `badge:'deep'`. The `verdict = m.fit && m.fit.verdict ? … : 'good'` fallback at line 3296 is changed so the default is **`'Unknown'`, never `'good'`** — a missing verdict must render as a visible non-committal chip, never a fabricated green pass.
- **Requires:** `local_models.items` field names match what the rail reads (`fit.verdict`, `size_gb`, `estimated_vram_gb`, `runtime`, `label`, `id`, `badge`, `streamed`). Confirmed present in `_build_local_model_entry`.
- **Bad input:** empty `items` → existing `rail-empty` "none" path. A deep entry with no fit → verdict copy `"resident (aeroLLM)"` (static, not computed) — see C4.

### C3 — `_fit_verdict_label(required_gb, available_gb)` (`app.py:8116-8123`) — UNCHANGED
- **Promises:** `required_gb<=0 or available_gb<=0 → "Unknown"`; `<= avail*0.82 → "Good"`; `<= avail*1.08 → "Marginal"`; else `"Requires streaming"`. The hysteresis bands (0.82/1.08) are the anti-flicker guard (A5).
- We do **not** touch this function. It is correct and already emits the honest verdict; the whole bug is that its output never reached the rail.

### C4 — aeroLLM / deep-entry copy
- **Promises:** deep entries render badge/verdict **`"resident (aeroLLM)"`**, never `"streaming"` (frontend `deepEntries` map currently hardcodes `verdict: 'streaming'` at `chat.html:3722` — change to `'resident (aeroLLM)'` for installed aerollm). No Load/Unload/Eject button on the aeroLLM row (see C5). Expand copy: `"resident (aeroLLM) · frees on next portal restart"`.
- **Rationale:** `AERO_MOE_SELECT` is off and absent from `src/` (grep confirms). Calling it "streaming" markets an opt-in-and-off capability as the default — the §6 guardrail forbids exactly this.

### C5 — `POST /api/chat/eject` (`app.py:6845-6911`) — honest per-runtime
- **Promises per runtime:**
  - `ollama` (with `model`): runs `ollama stop <model>`; on rc==0 returns `{ok:true, freed:["ollama:<model>"]}`. **Genuinely frees.** Unchanged.
  - `airllm` | `aerollm`: **stops claiming success.** Returns `{ok:false, freed:[], requires_restart:true, notes:["resident (aeroLLM) · frees on next portal restart"]}`. Does NOT append a misleading `"<runtime> cache"` to `freed` (that `del _OPTIONAL_CHAT_BACKEND_CACHE[runtime]` frees nothing real because the weights live in `AeroLLMBackend._shared` + `deep_policy._deep_router`). This makes the honest branch at `app.py:6902-6904` reachable — resolve by removing the false-success `if runtime in ("airllm","aerollm")` interception so the honest note wins.
  - `mlx-openai`, `mlx/cpu/cuda`: unchanged honest restart notes.
- **Requires:** a `model` for `ollama`.
- **Bad input:** unknown/blank runtime → clears the optional cache (existing catch-all), unchanged.
- **Defense in depth:** the aeroLLM row will not render an eject button, so this branch is only reachable by a stale cached JS or a direct API call. It must still be honest when hit.

### C6 — `POST /api/chat/model-load` state machine (`app.py:7191-7266`) — trimmed + honest ETA
- **Promises:** states are exactly `{loading, ready, error, canceled}` (the six-state `docs/maximus.plan.md §5` machine is trimmed in the doc to match — see §2.6 resolution). While `loading`, `eta_seconds` is **derived**: `eta_seconds = round(on_disk_bytes / throughput_bytes_per_sec)` where `throughput` is a rolling median of past same-runtime loads, else a conservative default (`ARAIL_LOAD_THROUGHPUT_MBPS`, default ~500 MB/s cold GPU load). `progress` is **indeterminate** (no incremental signal is available from a blocking `asyncio.to_thread` call) — the UI shows a spinner + ETA countdown, **not a fake filling bar** (a fake bar is itself a small lie this sprint exists to remove).
- **Requires:** `on_disk_bytes` known for the target model (from `size_gb` * 1024³, already on the entry). If unknown, `eta_seconds = null` and the UI shows "loading…" with no fabricated number.
- **Bad input / timeout:** the `asyncio.to_thread(_get_runtime_backend|_get_optional_chat_backend|...)` load is wrapped so it cannot pin the state at `loading` forever — on exception → `error` with the exception string (existing); a hard wall-clock guard (`ARAIL_LOAD_MAX_SEC`, default 180) transitions to `error` with a "load exceeded budget" message rather than hanging (F-LOAD-HANG).
- **Blocking:** unchanged — chat input is read-only until `ready` (per spec §6). No new blocking behavior.

### C7 — `backend_notice` (`app.py:6124-6146`) — DELETED
- The `_backend_notices` dict, the `backend_notice` variable, and the `"backend_notice"` response key are removed. The honest fit chip (C2/C3) + `"resident (aeroLLM)"` badge (C4) supersede it. No template reads it today; deleting it removes the seventh unread field before it accretes. (§2.4 resolution.)

### C8 — References panel pointer (`chat.html:1810`) — corrected
- `src/arail/chat/gallery.py` (phantom) → `src/arail/chat/__init__.py` (`gallery_view()` / `detect_installed_models()`). Zero-cost; stops the next session re-grepping. (§2.5.)

---

## Failure modes

Every row has a test in the strategy below (test IDs in the right column double as the mapping).

| Failure | Detection | Recovery | Test |
|---|---|---|---|
| **F-BLANK** — `compact.hardware` still undefined; telemetry shows `—` | Assert `d.compact.hardware.free_gb` present & numeric on cold `GET /api/chat/models` | Nest snapshot into `compact`; if probe fails, `free_gb=0` → verdict `Unknown` + `?`, never `—` and never `Good` | T-COLD |
| **F-FAKEFIT** — a `good` chip renders on a model whose size > free memory | Grep rendered rail for any `Good` chip where `estimated_vram_gb > free_gb` → must be 0 | Rail reads `compact.local_models.items`; default verdict is `Unknown` not `good` | T-FIT |
| **F-HEADER** — 26B model renders under a `≤ 8B` header | Assert local-column header text has no "≤ 8B" / "8B" substring | Static header copy `Local · GPU (≤ 8B)` → `Local · GPU` (`chat.html:1731,2175`) | T-HEADER |
| **F-EJECTLIE** — aeroLLM eject reports success, memory stays pinned | After eject call for aerollm: assert `ok==false`, `requires_restart==true`, and `AeroLLMBackend._shared` still populated | Endpoint returns honest note; frontend renders no eject button for deep rows | T-EJECT-AERO |
| **F-EJECTREAL** — Ollama eject claims success but model still resident | Post-eject, `ollama ps` must NOT list the model; RSS/VRAM drops | Keep `ollama stop`; test asserts real residency delta, not just `ok:true` | T-EJECT-OLLAMA |
| **F-OVERSELL** — copy claims "streaming"/"selective expert-streaming" while `AERO_MOE_SELECT` off | grep rendered payload + `models_catalog.yaml` for "selective expert-streaming"/"streaming" on aerollm rows → 0 | `gpt-oss-20b` catalog copy → "resident (aeroLLM)"; deepEntries verdict → "resident (aeroLLM)" | T-COPY |
| **F-LOAD-HANG** — a stalled Ollama pins load state at `loading` forever | Load state must reach `ready`/`error`/`canceled` within `ARAIL_LOAD_MAX_SEC` | Wall-clock guard transitions to `error`; ETA derived, not hardcoded | T-LOAD-BOUND |
| **F-FAKEETA** — hardcoded `eta_seconds=15, progress=0.15` shown regardless of model size | Assert `eta_seconds` scales with `on_disk_bytes`; a 14 GB model and a 1 GB model differ | ETA = bytes/throughput; progress indeterminate (spinner), no fake bar | T-ETA |
| **F-FLICKER** — fit chip flips Good↔streaming across refreshes on idle machine | Repeat `GET /api/chat/models` N times on idle box; verdict for a given id must be stable | 0.82/1.08 hysteresis bands; if unstable → STOP (disconf. #3), smoothing sub-project | T-NOFLICK |
| **F-RESTART** — after portal restart, aeroLLM memory does NOT return | Baseline RSS, warm aeroLLM, restart, assert RSS returns toward baseline | This is the honest contract ("frees on next portal restart"); verify it's true | T-RESTART |
| **F-MOEBASIS** — MoE fit computed off active-param (4B) not resident weights (13.4 GB) → falsely `Good` | Assert `gemma-4-26b-a4b` estimate ≥ its disk size, not ~2 GB | `_estimate_model_memory_gb` prefers `size_gb`/`expected_disk_gb`; test pins it | T-MOE |
| **F-DEADFIELD** — `backend_notice` (or new top-level `hardware`) left as an unread field | grep template for `backend_notice` → 0; server no longer emits it | Delete server-side dict + key (C7); prefer removing top-level `hardware` | T-DEADFIELD |
| **F-XSS** — model id / label / rationale injects markup into the rail | Feed a model id containing `<img onerror>`; assert escaped in DOM | All row fields already routed through `escapeHtml`; keep it on new fields | T-XSS |

---

## Test strategy

QA will execute this. Coverage on changed lines ≥ 80%. Weighting per arail gating: this touches security-adjacent (someone else's machine), so honesty/behavior tests dominate over happy-path.

### Named suite: **Cold-Start / Restart / Free-Memory ("Persistence & Honesty")**
This is the mandated suite for the bug class found and fixed twice this session (the unbounded Ollama warm-up ping; the aeroLLM eject that lied about freeing memory). It is a **cross-process, real-OS suite** — it is not satisfied by "the UI didn't crash." It runs on the operator's own airgapped Mac and asserts screen-vs-terminal agreement.

- **T-COLD** (cold portal) — start portal fresh, first `GET /api/chat/models`. Assert `compact.hardware.free_gb` numeric and within ±1 GB of `psutil.virtual_memory().available` (macOS) / `nvidia-smi --query-gpu=memory.free` (CUDA), read at the same instant. No `—`, no fabricated value. *(F-BLANK)*
- **T-FIT** — with `gemma-4-26b-a4b` installed, assert its rendered verdict ∈ {Marginal, Requires streaming, Unknown} and never `Good`; and a global invariant: no rendered `Good` chip has `estimated_vram_gb > free_gb`. *(F-FAKEFIT)*
- **T-HEADER** — assert the local-column header string contains no "8B" / "≤". *(F-HEADER)*
- **T-EJECT-OLLAMA** — load an Ollama model, confirm resident via `ollama ps`, POST eject, then assert `ollama ps` no longer lists it AND process/VRAM footprint dropped. A button that exists must actually free. *(F-EJECTREAL)*
- **T-EJECT-AERO** — assert the aeroLLM row renders **no** eject button; then POST eject `{runtime:'aerollm'}` directly and assert `ok==false`, `requires_restart==true`, honest note present, and `AeroLLMBackend._shared` still holds the initialized instance (we did NOT claim to free what we didn't free). *(F-EJECTLIE)*
- **T-RESTART** — record RSS baseline, warm aeroLLM (via preload or a deep call), record elevated RSS, restart the portal, assert RSS returns toward baseline. Proves the "frees on next portal restart" copy is true, not a second lie. *(F-RESTART)*
- **T-LOAD-BOUND** — simulate a hung Ollama (point at a black-hole port / patch `_get_runtime_backend` to sleep) and assert the load state reaches `error` within `ARAIL_LOAD_MAX_SEC`, never pinned at `loading`. Directly guards the "request that hangs indefinitely" class. *(F-LOAD-HANG)*
- **T-NOFLICK** — 20 consecutive `GET /api/chat/models` on an idle machine; assert the verdict for each installed id is identical across all 20 (no Good↔streaming flip). If it flips → this is disconfirming-evidence #3; STOP and open the smoothing sub-project. *(F-FLICKER)*

### Unit
- `_fit_verdict_label` boundary table: `(required, available)` at `0.82*avail`, `1.08*avail`, `0`, negative → {Good, Marginal, Requires streaming, Unknown}. *(C3, F-FAKEFIT)*
- `_estimate_model_memory_gb` for an MoE: `gemma-4-26b-a4b` with `size_gb=14.4` → estimate ≥ 14.4 (not the 4B-active figure). *(F-MOEBASIS / T-MOE)*
- ETA derivation: `eta_seconds` monotonic in `on_disk_bytes`; a 14 GB vs 1 GB model produce different ETAs; unknown size → `null`. *(C6, F-FAKEETA / T-ETA)*
- eject endpoint per-runtime contract: table-driven over {ollama, aerollm, airllm, mlx-openai, blank} asserting the `ok`/`freed`/`requires_restart` shape from C5. *(F-EJECTLIE)*

### Integration
- `GET /api/chat/models` end-to-end: assert `compact.hardware` present, `compact.local_models.items[*].fit.verdict` present, `backend_notice` **absent** from the response body. *(C1, C7, F-DEADFIELD / T-DEADFIELD)*
- Frontend render (jsdom or Playwright): `State.models` populated from `compact.local_models.items`; a row missing `fit` renders `Unknown`, never a green `Good`. *(C2, F-FAKEFIT)*

### Regression
- **F8 regression:** grep the built template + server response for `backend_notice` → 0 occurrences. This field sat unread for six weeks; assert it is gone, not merely still-unrendered. *(T-DEADFIELD)*
- **`AERO_MOE_SELECT` overstatement:** grep `models_catalog.yaml` + rendered payload for "selective expert-streaming" and bare "streaming" on aerollm rows → 0. *(T-COPY)*
- **Re-run the exact live in-browser test that surfaced the four lies this session** (VISION pre-committed pass/fail). If any of the four (header, fake fit, blank telemetry, lying eject) still shows → wedge failed, does not ship.

### Performance
- Not a hot path; no throughput regression expected. One guard: `GET /api/chat/models` latency must not regress meaningfully from the added nesting (it's a dict re-key, O(1)). Assert p95 within +10% of baseline. The NVMe/throughput ETA probe (if a rolling probe is added) must be non-blocking on the request path.

### Security
- **T-XSS** — model id/label/rationale containing `<img src=x onerror=alert(1)>` must render escaped in the rail (all fields through `escapeHtml`). New fields (fit summary, headroom expand copy) must go through the same escape. *(F-XSS)*
- No new user-input surface, no auth change, no new dependency, no file/network I/O beyond the already-present `ollama stop` subprocess (which takes a `model` string already validated by `_validate_local_model_id_relaxed`). Confirm the eject `model` param remains validated before reaching `subprocess.run` (it is passed as an argv element, not a shell string — no injection).

---

## Tech debt

| Added | Repaid |
|---|---|
| ETA throughput estimate uses a coarse default until enough loads accumulate a rolling median — approximate, not measured, for the first few loads. Bounded and honest (shows a countdown, not a fake bar), but not the spec's ±20% NVMe-probe accuracy. | **§2.1** telemetry blank fixed — snapshot nested. |
| One scoped, explicitly-labeled non-goal hook is *reserved* (not built) for true frontier layer-streaming, so the concept is named without faking UI for it. | **§2.2** root-cause fixed — rail reads the list with real fit; the `'good'` default dies. |
| `top-level hardware` key may linger one release for back-compat (prefer deleting now). | **§2.3** lying eject removed — honest absence + honest endpoint. |
| | **§2.4 / F8** dead `backend_notice` deleted (repays 6-week-old debt). |
| | **§2.5** phantom `gallery.py` pointer corrected. |
| | **§2.6** hardcoded ETA replaced with derived ETA; six-state doc trimmed to shipped reality. |
| | **Header lie** (`≤ 8B`) — fifth false claim, fixed. |

**Net: strongly negative (debt repaid).** Five documented gaps (§2.1–2.6) plus the header lie are closed; the only debt added is an approximate-until-warmed ETA, which is itself an honest improvement over a hardcoded constant.

### Discovered, explicitly OUT of scope — named so it is not a seventh silent follow-up
- **Gemma license mislabel:** `models_catalog.yaml:239` labels `gemma-4-26b-a4b` "Apache-2.0". Gemma ships under the **Gemma Terms of Use**, not Apache-2.0 (see workspace CLAUDE.md "Gemma disclosure exception"). This is a copy-honesty bug of a *different class* (license, not memory/fit); folding it in is scope drift against the leash. **Owner: architect (license/disclosure). Trigger: the Gemma default-floor sprint (G1) OR the next sprint touching the catalog — whichever comes first. Not an env-flag dormant lane; a dated hand-off.** Recorded here, per the anti-attempt-#7 discipline, rather than left in a REVIEW.md as an undated follow-up.

---

## Explicit resolution of PROMPT.md §2 items 3, 4, 6 (required by this sprint's brief)

These are resolved *here, in design*, not left open.

**§2.3 — aeroLLM eject honesty → REMOVE THE BUTTON (honest absence).**
The singleton cannot be hot-freed this sprint (A3: three caches + a re-warming preload loop + unverified Rust-Drop→Metal-free). Decision:
1. Frontend renders **no eject/unload affordance** on aeroLLM (deep) rows; expand copy reads `"resident (aeroLLM) · frees on next portal restart"`.
2. Endpoint (C5) stops returning false success for `aerollm`/`airllm`: returns `{ok:false, freed:[], requires_restart:true, notes:[…]}`. The previously-unreachable honest branch at `app.py:6902-6904` is made reachable by removing the false-success interception. **One behavior, documented — not a third undocumented path.**
This directly satisfies win-condition #3 ("every Unload button that exists, works — or does not exist") and disconfirming-evidence #4 is the tripwire (if honest-absence confuses the operator more than the lie did, real singleton-freeing becomes a separately-scoped sibling-repo bet).

**§2.4 — `backend_notice` fate → DELETE THE DEAD CODE.**
Remove `_backend_notices`, `backend_notice`, and the `"backend_notice"` response key (`app.py:6124-6146`). The honest fit chip + `"resident (aeroLLM)"` badge supersede it. F8 has been unread for six weeks; deletion (not re-wiring) is the resolution, and the regression test asserts zero occurrences so it cannot silently return as field #7. (C7.)

**§2.6 — six-state load machine → TRIM THE DOC to the shipped reality; wire a real ETA.**
Do **not** build the six-state machine. `docs/maximus.plan.md §5` is edited so its loader state machine documents the states that actually ship: `loading → ready | error | canceled`. The hardcoded `eta_seconds=15, progress=0.15` is replaced with `eta_seconds = on_disk_bytes / throughput_estimate` (rolling median, conservative default). Progress stays indeterminate (spinner + countdown) because a blocking `asyncio.to_thread` load exposes no incremental signal — and a fake filling bar would be a new lie. Doc and code agree; no third undocumented behavior. (C6.)

---

## Non-goals (with owners + triggers — never undated)

Per disconfirming-evidence #5 (the attempt-#7 tripwire): every deferral below has an owner and a trigger. Any REVIEW.md follow-up lacking one blocks ship.

- **New Models tab / any net-new surface** — gated behind disconfirming-evidence #1 (fidelity ships and the operator *still* can't decide in <10s). Reopen with data, not a guess. **Owner: visionary. Trigger: disconf-#1 fires post-Phase-0.**
- **Agent-binding editor UI** — this sprint surfaces tiering as a **read-only chip only** ("serves: fast"), first thing cut if the wedge overruns. No editor. **Owner: visionary. Revisit: 2026-08-10.**
- **"Symbolic chain of thought / knowledge tiering"** vision — exists nowhere in code; new vision on top of `resolve()`. **Owner: visionary. Revisit: 2026-08-10.**
- **aeroLLM true frontier layer-streaming UI** (`AERO_MOE_SELECT`) — off and absent from `src/`. No fake Load/Unload/WARM. One labeled non-goal hook reserved only to name the concept. **Owner: architect (cross-repo). Trigger: `AERO_MOE_SELECT` actually enabled.**
- **Real aeroLLM singleton hot-free** — requires a sibling-repo (Rust runtime) change to guarantee Drop→Metal-free plus preload-loop coordination. **Owner: architect + operator. Trigger: disconf-#4 fires (honest-absence proven worse than the lie).**
- **Nucleus ↔ aeroLLM integration** — net-new Nucleus-side work; graduated artifacts already appear via `register-artifact` tagged `"fast"` and get the same real fit chips (zero-cost, in scope). Bidirectional consumption is out. **Owner: architect (cross-repo scoping) + operator (priority). Trigger: aeroLLM ships HTTP bindings.**
- **Gemma license mislabel** — see Tech debt. **Owner: architect. Trigger: G1 or next catalog-touching sprint.**

---

## Recommended implementation order

Phase 0 (the fidelity floor) ships as its **own PR, first and separate** — 80% of the deliverable. Order within it is chosen so each step is independently testable and the cheapest, highest-trust fixes land first.

1. **§2.1 — nest the snapshot** (`app.py:7811-7839`): put `memory_snapshot` into `compact.hardware`. Land T-COLD. (~1 line + test.) *Telemetry stops showing `—`.*
2. **§2.2 — point the rail at the truthful list** (`chat.html` ~3707 + renderModelRail default at 3296): `State.models = d.compact.local_models.items`, preserve the `deepEntries` fold, change the `'good'` default to `'Unknown'`. Land T-FIT. *This is the root-cause fix — HARD GATE: if this is not a cheap data-source swap, STOP and report (disconf-#2).*
3. **§2.2 header** (`chat.html:1731,2175`): `Local · GPU (≤ 8B)` → `Local · GPU`. Land T-HEADER.
4. **§3 / F-OVERSELL copy** (`models_catalog.yaml:126-127` + deepEntries verdict `chat.html:3722`): "selective expert-streaming" / "streaming" → "resident (aeroLLM)". Land T-COPY.
5. **§2.3 — honest eject** (`app.py:6845-6911` endpoint + remove eject button on deep rows in `chat.html`): endpoint returns honest `ok:false`+restart note; no button rendered. Land T-EJECT-AERO, keep T-EJECT-OLLAMA green.
6. **§2.4 — delete `backend_notice`** (`app.py:6124-6146`): remove dict + var + key. Land T-DEADFIELD.
7. **§2.5 — fix References pointer** (`chat.html:1810`): phantom `gallery.py` → `__init__.py`.
8. **§2.6 — real ETA + doc trim** (`app.py:7191-7237` + `docs/maximus.plan.md §5`): derived `eta_seconds`, timeout guard, trim the six-state doc. Land T-ETA, T-LOAD-BOUND.
9. **Run the Persistence & Honesty suite in full** (T-COLD…T-NOFLICK, T-RESTART) plus the re-run of the exact live four-lies test. If all green and the four lies are gone → Phase 0 closes and ships.

Then, **strictly inside the one Chat-tab list** (second PR, only after Phase 0 holds): the expand-for-numbers progressive-disclosure content per row (free RAM/VRAM, `keep_alive`, load ETA) and the read-only "serves: <tier>" chip (first to cut). **Nothing else** — tab restructure, binding editor, streaming UI, and Nucleus integration are the named non-goals above.

**Hard gate restated:** if Phase 0 cannot close — specifically if §2.2 needs a real refactor (disconf-#2) or the fit chip flickers (disconf-#3) — **stop and say which gap held.** Additive UI on a lying floor is exactly how this becomes attempt #7.
