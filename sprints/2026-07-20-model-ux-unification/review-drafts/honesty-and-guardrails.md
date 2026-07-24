# Review (lens: honesty-and-guardrails): Model selection UX — unified-list fidelity

**Date:** 2026-07-20
**Build:** [BUILD_LOG.md](../BUILD_LOG.md) at `692b460`
**Architecture:** [ARCHITECTURE.md](../ARCHITECTURE.md)
**Lens:** honesty-and-guardrails — the three PROMPT.md §6 guardrails.
Note: there is **no committed PROMPT.md** (ARCHITECTURE.md line 5 documents this and re-anchors the six-gap brief to VISION.md → "Wedge"). The three guardrails are taken verbatim from the review task and checked against the accumulated sprint diff `qukaizen/gemma4-ollama-think-fix...HEAD`.

## Verdict: WEAK_PASS

No BLOCK findings. One honesty-relevant ASK (a pre-existing, self-correcting warm-dot flicker on failed eject) is logged below as a dated follow-up so it does not itself become an undated deferral.

---

## Guardrail 1 — "no button that reports success without the real effect happening"

**PASS.** Every mutating affordance now reports what actually happened.

- **Eject endpoint `/api/chat/eject` (`app.py`, terminal return).** The unconditional `return {"ok": True, ...}` is gone; the terminal return computes `ok`/`requires_restart` per runtime:
  - `ollama`: `ok = (returncode == 0 and no exception)` — a dead daemon / wrong model now returns `ok:false` with an honest note.
  - `aerollm`/`airllm`: always `ok:false, requires_restart:true`, `freed=[]` — the wrapper cache is not where the resident weights live (A3), so nothing is ever falsely reported as freed.
  - `mlx-openai`/`mlx`/`cpu`/`cuda`: `ok:false, requires_restart:true`.
  - blank/unknown: `ok = bool(freed)`, with a note that in-process deep backends still need a restart.
  Input `model` is validated via `_validate_local_model_id_relaxed` before `subprocess.run(["ollama","stop",...])` (builder-discovered gap, fixed inline) — no shell string, no injection surface.
- **Deep-row eject affordance removed (`chat.html`).** `ejectBtn = isDeep ? null : ...`; the active/mini card also suppresses `eject A`/`eject B` for deep rows (`isDeepActive`/`bIsDeep`). The one case that cannot be hot-freed no longer offers a button that would lie — honest absence, per VISION win-condition #3.
- **Active-card eject (`ejectModel`, `chat.html:3557`).** Correctly gates every UI mutation on `d.ok`; on failure it shows `eject failed: ...` and clears nothing. Clean.
- **Load state machine (`_prepare_chat_model_load`).** `ready` is set only in the success `else` branch. A wall-clock timeout flips the *reported* state to `error` with copy that explicitly says the model "may still be loading in the background" — never a false completion. The inflight lock is released by the task's done-callback (not by the timeout), so a timed-out load cannot be followed by a second doubly-resident load.
- **Cancel endpoint (`api_chat_model_load_cancel`).** No longer fabricates a `canceled` state. Returns `ok:false` with an honest note ("a load in progress cannot be interrupted…"); `_CHAT_MODEL_LOAD_STATE` is never mutated. The dormant `loader-strip`/`ls-cancel` markup in `chat.html` has an inserted comment warning against wiring it to expect a `canceled` transition.
- **Idle init state.** `_CHAT_MODEL_LOAD_STATE` initializes to `state="idle", message="No model loaded"` — cold start no longer claims `ready` with nothing loaded.

### ASK-1 (pre-existing, self-correcting) — rail-card eject clears the warm dot before confirming `d.ok`
`chat.html:3401` calls `State.warmModels.delete(m.id)` **unconditionally**, then line 3402 flashes honest text (`d.ok ? 'ejected …' : 'eject failed: …'`). On a failed Ollama eject the *textual* report is honest, but the warm dot flips to cold while the model is still resident, until the next `GET /api/chat/models` re-seeds `State.warmModels` from the live `ollama ps` probe (`chat.html:3830`). This is:
- **not introduced by this sprint** (the unconditional delete predates the diff; the sprint only changed the `ejectBtn` selector), and
- **self-correcting** on the next model-list fetch, and
- inconsistent with its sibling `ejectModel()` which correctly gates on `d.ok`.
Because the sprint's own thesis is "one visible lie taxes every true thing," the transient cold-dot-on-failed-eject is worth closing even though the button's text is honest. Recommend gating the `warmModels.delete` on `d.ok` (one-line change, mirrors `ejectModel`). **Owner: builder. Review-by: 2026-08-10.** Not blocking: honest text + self-healing probe.

---

## Guardrail 2 — "no capability claimed in UI copy that is not actually turned on"

**PASS.** The `AERO_MOE_SELECT` oversell is gone everywhere it was attributed to aeroLLM, and streaming is attributed only to the backend that actually does it.

- **`models_catalog.yaml`:** `gpt-oss-20b-MLX-4bit` description "native selective expert-streaming backend … bit-exact" → "resident (aeroLLM) once loaded"; the deep-placeholder and section comments corrected the same way. No catalog row claims a capability that is off in `src/`.
- **`chat.html` headers:** `Local · GPU (≤ 8B)` → `Local · GPU` (the column renders the 26B MoE); `Local · SSD (streamed)` → `Local · aeroLLM` (aeroLLM keeps the model resident, it does not stream). Both twins (rail + picker) and the subtitle changed.
- **Deep-row copy is warmth-driven and backend-accurate:** aeroLLM → `resident (aeroLLM)` / `installed (aeroLLM) · load to warm`; the frontend `deepEntries` verdict branches on backend id (`aerollm` → Resident/Ready-to-load, else Streaming) instead of the old `o.installed ? 'streaming'`. AirLLM copy ("layer-streamed") is accurate for AirLLM (the opt-in backend that genuinely layer-streams) — not an aeroLLM oversell.
- **Residual "expert-streaming" strings** (`chat.html:1754`, `3783`) are in comments that explicitly state the feature is **off and absent from `src/`** — honest disclosure, not a claim. The `streamed-badge` title now reads "AeroLLM resident · AirLLM layer-streamed", correctly splitting the two backends.
- **Warmth is probed, not asserted:** Ollama rows carry `warm` from a live `/api/ps` probe (≤1s timeout, last-known fallback — never "all cold" on failure, which would be its own lie); aeroLLM `resident` from `model_warmth._tier1_resident()`; the stale `"streamed": True` on the aeroLLM optional-backend was corrected to `False`.
- **`backend_notice`** (the dead over-labeling field) deleted server-side; regression grep asserts zero occurrences.
- **Gemma license mislabel** (`models_catalog.yaml:238-239`) corrected: "(Apache-2.0)" → "Built with Gemma · Gemma Terms of Use (ai.google.dev/gemma/terms)", satisfying the workspace Gemma disclosure exception for the false-claim portion.

---

## Guardrail 3 — "no undated follow-up left in this sprint's own docs"

**PASS.** Every deferral in the sprint's own docs carries owner + review-by date.

- **ARCHITECTURE.md Non-goals** (9 items) each carry `Owner:` + `Review-by: 2026-08-10` (several also carry a reopen trigger). The attempt-#7 tripwire (disconfirming-evidence #5) is honored.
- **Gemma full-disclosure compliance package** (NOTICE/`licenses/`/§3.1(4)) is dated: **Owner: architect, Date: 2026-08-10** — the false label dies this sprint; only the compliance-completeness audit is dated.
- **ETA ±20% NVMe-probe accuracy** is explicitly **descoped, not deferred** (INFO-6) — no phantom follow-up owed.
- **BUILD_LOG.md "Architect feedback required"** is empty; the six discovered items were all fixed inline and documented, none left as an open follow-up.
- **`docs/maximus.plan.md §5`** now separates "What actually ships today" (the 4-state `idle → loading → ready | error` machine) from the six/seven-state SSE design, which is relabeled "future design — not implemented" — closing a capability-implied-by-doc gap that itself borders on guardrail 2.
- Grep of `ARCHITECTURE.md` + `docs/maximus.plan.md` for follow-up / non-goal / deferred / revisit language returned **zero lines lacking a date**.

---

## Required actions before merge

None blocking. One dated follow-up to fold into REVIEW.md so it does not become an undated deferral:

1. **ASK-1** — gate the rail-card eject's `State.warmModels.delete(m.id)` (`chat.html:3401`) on `d.ok`, matching `ejectModel()`. Pre-existing, self-correcting on next probe, honest text today. **Owner: builder. Review-by: 2026-08-10.**
