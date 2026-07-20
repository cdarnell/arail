# Build log: model selection UX — unified-list fidelity, disclosed honestly

**Architecture:** [ARCHITECTURE.md](./ARCHITECTURE.md) at `938ff9d468e1369e69f2b7f8f0613d0ee1184fa5` (ledger-fix commit, already landed)
**Started:** 2026-07-20

## Recap: what already shipped (ledger commit `938ff9d`, not redone here)

Implementation-order items 1, 2, 4, 7 (§2.1 nest+delete top-level `hardware`
and close the psutil-fallback lie; §2.2 rail data source + both `'good'`
fallbacks at 3296/3375; §2.4 delete `backend_notice`; §2.5 fix the phantom
`gallery.py` References pointer) plus the discovered `endpoint`
back-compat fix. This log covers everything **after** that commit.

## Plan

Matches ARCHITECTURE.md's own "Recommended implementation order" verbatim.
Steps 1/2/4/6/7 are done (ledger commit). Remaining:

| # | Files | Change | Test | Commit ref |
|---|---|---|---|---|
| 3 | `chat.html` | Header twins: `Local · GPU (≤ 8B)`→`Local · GPU`, `Local · SSD (streamed)`→`Local · aeroLLM` (both rail + picker + subtitle + picker-B) | T-HEADER | TBD |
| 4 | `chat.html`, `models_catalog.yaml` | F-OVERSELL full site sweep (no "streaming"/"selective expert-streaming"/"bit-exact" on aeroLLM copy) + Gemma Apache-2.0 mislabel fix | T-COPY | TBD |
| 5 | `app.py:6835-6900` | C5 honest eject: edit the terminal `return {"ok": True}` to compute `ok`/`requires_restart` per-runtime | T-EJECT-AERO, T-EJECT-OLLAMA-FAIL | TBD |
| 8 | `app.py`, `chat.html` | Warmth probe: `warm` from live `ollama ps` (short-timeout), `resident` from `_tier1_resident()`; deep rows lose eject, gain warmth-driven badge copy | T-WARMDOT | TBD |
| 9 | — | Run Persistence & Honesty (display subset) — verification, folded into step 3-8 commits' own test runs | — | — |
| 10 | `app.py` | C6.1 idle init state + `_OPTIONAL_CHAT_BACKEND_CACHE_LOCK` + `_CHAT_MODEL_LOAD_INFLIGHT` | T-IDLE, T-CACHERACE | TBD |
| 11 | `app.py` | C6.2 serialize load via `scheduler.inference_slot("chat-model-load")` | T-LOADRACE | TBD |
| 12 | `app.py`, `chat.html` | C6.4 honest Cancel (no `canceled` state) + C6.5 bounded timeout holding the inflight lock until the thread settles | T-CANCEL, T-LOAD-BOUND | TBD |
| 13 | `app.py`, `docs/maximus.plan.md` | C6.3 model-identity refusal, C6.6 real ETA, C6.7 re-snapshot fit at click time, C6.8 friendly errors; trim doc §5 to `{idle,loading,ready,error}` | T-SWITCH, T-ETA, T-CORRUPT, T-REFIT, T-DAEMONDOWN | TBD |
| 14 | — | Full suite run + regression grep | — | TBD |

Each row lands as its own commit (or a tightly-coupled pair when the
architecture itself splits backend/frontend for the same contract, e.g.
step 8's server probe vs. client rendering may be two commits).

## Execution

### Step 3 — F-HEADER, both twins
`chat.html`: `Local · GPU (≤ 8B)` → `Local · GPU`; `Local · SSD (streamed)`
→ `Local · aeroLLM` at all four sites (rail-card headers ×2, picker-popup
section headers ×2), plus the deep rail-card subtitle. No plan delta.
Test: `tests/test_model_ux_phase0_headers.py` (T-HEADER).
Commit: `bf34aee`.

### Step 4 — F-OVERSELL full site sweep + Gemma license fix
`chat.html`: fixed every aeroLLM-attributed streaming/layer-stream/SSD
claim (col-chip-B tooltip+hint, References panel, both streamed-badge
titles, comparison-strip cell + cs-why note + setCompare comment,
picker-B header, disabled-B-button tooltip, and the central
`deepEntries.fit.verdict` mapping — now branches on backend id instead
of `o.installed ? 'streaming' : ...`). Extended `fitClass()` with
`resident`/`not install` branches so the new verdict vocabulary gets a
sane chip color. `models_catalog.yaml`: fixed the deep-model-placeholder
comment and the gpt-oss-20b-MLX-4bit entry (dropped the "native
selective expert-streaming backend"/"bit-exact" claims — AERO_MOE_SELECT
is off and absent from src/). Folded in the Gemma Apache-2.0 mislabel
fix per ARCHITECTURE.md's "Folded into this sprint" note.
No plan delta. Test: `tests/test_model_ux_phase0_oversell_copy.py` (T-COPY).
Commit: `c2fc531`.

### Step 5 — C5 honest `/api/chat/eject`
`app.py`: rewrote the terminal `return {"ok": True, ...}` to compute
`ok`/`requires_restart` per runtime (aerollm/airllm always `ok=false`;
ollama tracks the real subprocess returncode; mlx-openai/mlx/cpu/cuda
always `ok=false, requires_restart=true`; blank/unknown `ok=bool(freed)`).

**Delta from plan (discovered gap, fixed inline, not a redesign):**
ARCHITECTURE.md's Security section assumed `model` was "validated by
`_validate_local_model_id_relaxed`... before `subprocess.run`" — it
wasn't; eject passed the raw body field straight to `ollama stop`. Added
the validation call as part of this same edit (same function, same
contract, zero design risk) rather than leaving the assumption false.
Test: `tests/test_model_ux_phase0_eject_honesty.py` (T-EJECT-AERO,
T-EJECT-OLLAMA-FAIL + the validation regression). T-EJECT-OLLAMA
(happy-path real-daemon check) is out of unit-test reach per
ARCHITECTURE.md's own Test Strategy — QA's Persistence & Honesty suite
runs it on real hardware.
Commit: `d01bcd6`.

### Step 8 — F-WARMDOT warmth probe
`app.py`: added `_ollama_ps_resident_ids()` (live `/api/ps`, ≤1s
timeout, cached-last-known fallback — Performance guard) feeding a new
`warm` field on Ollama-runtime local entries; added a real `resident`
field to `optional_backends` (`model_warmth._tier1_resident()` for
aeroLLM, wrapper-cache presence for AirLLM); corrected aeroLLM's dead
`"streamed": True` field to `False` in the same edit (F-OVERSELL,
directly adjacent to the line being touched).
`chat.html`: seeds `State.warmModels` from this server truth on every
model-list fetch instead of only from the current session's own
load/eject clicks; deep rows (aeroLLM/AirLLM) now get warmth-driven,
backend-accurate badge copy and never render an Unload/Eject button in
either the rail card or the active/mini card (C4/C5 finding 6) — Load
only.
No plan delta beyond the `streamed: False` inline fix noted above.
Test: `tests/test_model_ux_phase0_warmth_probe.py` (T-WARMDOT).
Commit: `7bc0ef2`.

### Step 9 — Persistence & Honesty (display subset) checkpoint
Added one end-to-end integration test replaying VISION.md's exact
scenario (gemma-4-26b-a4b, 13.45 GB, 7.1 GB free) through a single
`GET /api/chat/models` call, asserting the full gap-closure list holds
together (hardware nested once, fit chip never "Good", estimate based
on real disk size not active-params, warm/resident present, no
`backend_notice`, no header lies) — the automated form of the Test
Strategy's "re-run the exact live in-browser test" gate.
Test: `tests/test_model_ux_phase0_integration.py`.
Commit: `7447107`.

**Phase 0 (display fidelity) is closed as of `7447107`.**

## Architect feedback required

(empty — no plan gap surfaced; the one discovered item, step 5's missing
`_validate_local_model_id_relaxed` call, was a factual gap between
ARCHITECTURE.md's stated assumption and the code, fixed inline per the
"low-risk, same-contract, document it" rule, not a design question.)

## Final state

(filled in at handoff, after Phase 0b)
