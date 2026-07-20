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

(filled in as each step lands — see below)

## Architect feedback required

(empty unless a gap is found — see bottom of this file if populated)

## Final state

(filled in at handoff)
