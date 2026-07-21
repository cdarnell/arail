# Vision (draft — "progressive-disclosure" angle): A dedicated Models tab that gives the truth a home

**Date:** 2026-07-20
**Product:** arail
**Wedge size:** one sprint (Phase 0 ledger + a minimal Models tab; tab is the container bet, not the wedge)
**Angle champion:** progressive disclosure — simple by default, real numbers on expand — on a dedicated surface.

> This is one competing vision draft, not the final VISION.md. It argues FOR a
> dedicated model-selection tab with progressive disclosure, as hard as that
> angle honestly deserves — including where it deserves a caveat. It commits to
> four explicit decisions the sprint brief (`PROMPT.md`) demands: (1) tab vs
> unified list, (2) load/unload semantics per backend, (3) agent-tiering surface,
> (4) Nucleus scope.

---

## The one-sentence thesis

The Chat-tab dropdown has failed five times not because the team can't wire a
picker, but because **a ~320px dropdown has no room to carry the truth** — so the
truth (real free RAM/VRAM, real fit verdicts, real load state) keeps getting
computed server-side and orphaned before it reaches the screen. A dedicated
**Models tab with progressive disclosure** is not "more UI"; it is a *forcing
function for honesty* — it gives the real numbers a home, and it makes a missing
number a **visible blank** (an obvious bug) instead of a **fake-green chip** (a
hidden lie). That is the specific pathology `PROMPT.md §2` documents, and a
dropdown structurally cannot fix it.

---

## User

Two concrete personas, served by one surface — which is exactly why progressive
disclosure is the design answer, not a nice-to-have.

**Primary — the friends-and-family ARAIL user (ARAIL's actual reason to exist).**
Concretely: the operator's sibling running a forked "PeanutLab" on a 24 GB Apple
M-series MacBook, `LAB_MODE=airgapped`. This session, this person opened the app,
saw `gemma-4-26b-a4b` (26.5B total / 13.4 GB on disk) rendered under a
**"LOCAL · GPU (≤ 8B)"** header with a green **"good"** fit chip, clicked **Load**,
and got either an OOM or a lie. They do not know what VRAM is. They need three
answers in plain language: *Can my machine run this? Is it running right now? How
do I turn it off?*

**Secondary — the operator / power user (Charles, on a workstation).** Wants the
*real* numbers on demand — free VRAM, on-disk bytes, `keep_alive` state, the load
ETA, and "which model does each agent actually use" — without digging into a
global settings panel two clicks deep that nothing in this session's testing ever
surfaced as "here's how agents pick models."

Progressive disclosure is literally the mechanism that serves both from one
screen: **level 1** answers the sibling's three questions in words; **level 2**
(one click) answers the operator's with numbers.

## Problem

Not "we need a prettier picker." The actual, underlying pain:

**The model surface lies, so the user cannot form a correct mental model of what
their machine is doing.** Every symptom in `PROMPT.md §2` is a variant of this:

- Fit chips are fake-green regardless of size — the rail reads `State.models`
  (from `gallery.installed`), a list that **never carries a `fit` field**, and
  line `chat.html:3296` defaults every missing verdict to `'good'`. The real
  verdicts (`_fit_verdict_label`, real `free_gb`) land in `compact.local_models.items`
  — a *different list the rail never reads* (§2.2).
- Memory numbers show `—` because `_local_memory_snapshot()` is returned as a
  top-level `hardware` key but the frontend reads `d.compact.hardware`, which is
  never nested (§2.1).
- **Unload reports success while memory stays pinned.** `/api/chat/eject` deletes
  a cache entry but never touches `AeroLLMBackend._shared`; the WARM dot goes
  clear and the memory stays resident until the whole portal restarts (§2.3).
- The two aeroLLM regimes are conflated, so the catalog copy oversells
  "selective expert-streaming" (`AERO_MOE_SELECT`) that is **confirmed off
  everywhere in the repo** (§3).

The throughline (`PROMPT.md §1`): the backend truth *exists* — that's why the UI
*looks* like it should be trustworthy — but it never reaches the screen, because
the surface it targets was never built with room to hold it. Five sprints tried
to cram honesty into the dropdown and left "documented follow-ups" that nobody
returned to.

## Win condition

Concrete, measurable, falsifiable on the operator's own 24 GB Mac, airgapped:

1. **No fake-fit.** `gemma-4-26b-a4b` (26.5B / 13.4 GB) on a 24 GB machine renders
   **"requires streaming"** or **"marginal"** — never **"good"**, and never under a
   **"≤ 8B"** header. Verified by loading it and reading the chip.
2. **No dashes.** `tele-hw` / `tele-vram` render real values from
   `_local_memory_snapshot()` on both the simple and expanded views — never `—`.
3. **No lying buttons.** Every **Unload** button that exists actually frees memory,
   verified by process-RSS delta against `ollama ps`. If a model type cannot be
   freed in-process this sprint, it has **no Unload button** and the copy reads
   "frees on next portal restart." Zero exceptions.
4. **Operator can answer "which model does each agent use?" in under 15 seconds,
   from the Models tab, with zero settings-panel clicks.** Witnessed.
5. **Pre-committed trust threshold:** the operator uses the tab and does **not**
   say "this is lying to me" — the exact reaction the last five attempts earned.

## The four explicit decisions (the brief demands these; I refuse to leave them implicit)

### Decision 1 — Tab vs. unified list: **DEDICATED "Models" TAB.**

I am championing the tab, and here is the honest case, weighed against the
operator's own words ("start in the Chat tab and get that right first"):

- **Why a tab wins the honesty fight.** The dropdown is a constrained surface;
  `chat-studio.spec.md §3` gives the entire local-model story ~320px shared with
  Compute Source and Custom Endpoint. Real memory detail does not fit there,
  which is *precisely why* five sprints orphaned it server-side. A tab gives the
  truth room, and — critically — turns a *missing* number into a **visible blank
  panel** (an obvious, un-shippable bug) rather than a **fake-green chip** (a lie
  that ships). The tab makes it structurally harder to reproduce §2.
- **Why this respects "get the Chat tab right first," not defies it.** The Chat
  tab keeps a **deliberately minimal** picker: the loaded model's name, a real
  status dot, and a **"Manage models →"** link that opens the Models tab. The Chat
  tab's model affordance becomes *simple and honest* (show what's loaded, link
  out) instead of *overloaded and lying* — which is the version of "right" that
  actually serves the persona. "Right" for the Chat tab is not "cram the whole
  memory truth into a dropdown"; that's the thing that keeps failing.
- **The honest caveat (I am a forcing function, not a salesman).** A tab is *more*
  surface to keep in sync, and five sprints already failed at *wiring*. A tab that
  reads the wrong list is still a tab that lies. Therefore the tab is **explicitly
  not the wedge** and **must not ship on top of an un-reconciled data path** — see
  the wedge and the hard gate below. The tab's value is *conditional* on Phase 0
  closing.
- **This is a documented deviation, not silent drift.** `chat-studio.spec.md §3`
  currently prescribes a dropdown-in-Chat, not a tab. Choosing the tab **requires
  rewriting §3** as part of this sprint's deliverables. If the architect finds the
  deviation can't be paid for, fall back to the dropdown — the progressive-disclosure
  *content model* (below) is portable to either container. The container is the
  bet; the content model is not on trial.

### Decision 2 — What "load" and "unload" mean, per backend (do NOT force one mental model)

`PROMPT.md §3` proves these are genuinely different regimes; conflating them is
"the most likely way this sprint quietly becomes attempt #7." So:

- **Ollama-resident models** (`llama-ai-eng`, `gemma-4-26b-a4b`, `deepseek-r1:14b`,
  everything in `ollama list`): **Load** = Ollama reads weights into GPU/RAM (real,
  timed — ~30s cold for a 14 GB q4). **Unload** = `ollama stop` / `keep_alive 0`,
  genuinely frees. The existing **Load / Unload / WARM** affordance is
  *architecturally correct here* — do not touch the model, only wire the truth to
  it. Progressive disclosure: **level 1** shows a Load/Unload toggle + a plain line
  ("loaded · using ~14 GB · frees when you unload"); **level 2** shows free
  RAM/VRAM, the `keep_alive` timer, and a real load ETA.
- **aeroLLM-resident models** (today's real case: `gpt-oss-20b-MLX-4bit`,
  `Qwen2.5-7B-4bit`): held in a process-wide singleton (`_shared`) with a real
  preload loop (`model_warmth.py`, gated on `metal_memory_pressure() < 0.60`).
  "Load" is a real one-time heavy event, so the cold→WARM mental model *holds*. But
  the badge MUST read **"resident (aeroLLM)"**, NOT "streaming" — because
  `AERO_MOE_SELECT` is confirmed off everywhere in the repo. **Unload** must EITHER
  really free `_shared` OR the button must not exist and the copy must say "frees
  on next portal restart." This sprint's mandate: **make it honest; no lying
  button** (architect decides in-process feasibility against the Rust runtime; the
  vision does not permit a false success).
- **aeroLLM true frontier layer-streaming** (the 671B-on-24GB research vision):
  **NOT a live product mode this sprint.** It has *no load/unload/WARM concept by
  design* — every call pays the per-layer disk cost. Since `AERO_MOE_SELECT` is off
  everywhere, it is not a running mode. The tab reserves an explicit, **labeled
  "streaming — not enabled"** placeholder (so the concept is honestly named) but
  renders **no fake Load/Unload/WARM** for it. This is the one line I will not let
  blur.

### Decision 3 — Agent tiering surfaces this sprint, **read-only.**

`PROMPT.md §4` confirms the tiering system is real and already consumed: five
profiles (`fast`, `reasoning`, `long_context`, `tool_use`, `build`), `bind()` /
`resolve()`, `FALLBACK_CHAIN`, live consumers (`researcher.py`, `deep_policy.py`,
`browser.py`, `forge.py`, Buddy transitively). **Do not rebuild it.** This sprint's
UI surfaces it as a **read-only progressive-disclosure panel** in the Models tab:

- **Level 1:** one plain line — "Agents use *llama-ai-eng* for fast tasks,
  *ai-engineer* for reasoning."
- **Level 2:** the full five-profile → model binding table + the fallback chain +
  the last `FallbackEvent`, sourced live from `ModelRegistry`.

**Rebind/edit UI is OUT this sprint** (surfacing is cheap and closes the operator's
"I can't see how agents pick models" gap; editing is a named follow-up). The
operator's **"symbolic chain of thought / knowledge tiering"** framing is *new
scope* (§4 confirms it exists nowhere) → a **named follow-up**, built on top of
`resolve()`/the five profiles, never a parallel mechanism. Owner + revisit date go
in the ledger (unlike every §1 follow-up).

### Decision 4 — Nucleus: **OUT this sprint, as a named follow-up** — with one cheap honest slice kept in.

`PROMPT.md §4` is unambiguous: Nucleus uses **AirLLM**, not aeroLLM; there are no
`aerollm`/`arail` imports in Nucleus; the working cross-repo integration runs the
**other direction** (ARAIL drives Nucleus over HTTP and registers graduated
artifacts back via `POST /api/models/register-artifact`, tagged `"fast"`).
"Nucleus will also use this model story" is net-new Nucleus-side integration that
does not exist — scoping it here makes it the seventh unfinished item.

- **Deferred (named follow-up, owner + date in ledger):** teacher-inference-via-aeroLLM
  and any Nucleus consumption of this surface.
- **Kept in (cheap, honest, in-scope):** the Models tab *shows* Nucleus-graduated
  artifacts that are **already registered and tagged `"fast"`** — a read, not new
  integration — with a "graduated from Nucleus" label. That honors the operator's
  intent at the price of a label, without opening a cross-repo lane.

## Wedge

**The wedge is not the tab.** The wedge is **one honest data path, rendered in the
simplest possible progressive-disclosure surface**, running entirely on the
operator's 24 GB Mac, airgapped, with `ollama` + the resident aeroLLM path — no
cloud, no `AERO_MOE_SELECT`, no Nucleus:

1. **Phase 0 — close the §2 ledger (no new features):** nest `_local_memory_snapshot`
   into `compact.hardware`; reconcile the two model lists so the rail reads real
   `fit` data (kill the `'good'` default); make eject honest-or-gone; fix the dead
   `gallery.py` pointer; decide `backend_notice` (wire or delete) and the load
   state machine (build or trim the doc). This alone makes the *existing* UI stop
   lying and **ships separately, first.**
2. **A minimal Models tab** rendering only: two cards (everyday + deep) with a
   real fit chip, a real memory line (**level 1**), a one-click "show memory
   detail" panel (**level 2**), and honest per-backend Load/Unload.

Agent-tiering read-panel and the Nucleus-artifact label are **stretch — cut first**
if the sprint tightens. The thing under test is the **progressive-disclosure
content model** (simple words by default, real numbers on expand, honest per-backend
copy). The **tab is its container** — a separable, revertible bet.

**Hard gate:** if Phase 0 cannot close (`PROMPT.md §2`), **stop and say so** — do
not design or ship the tab on a lying foundation. The brief is explicit: "If phase
0 can't be finished, say so explicitly and stop — don't design on top of it."

## Disconfirming evidence (pre-committed)

- **Data-fix failed:** if, after Phase 0, the reconciled single list *still* shows
  a fake "good" chip for the 26B model on the operator's machine, the plumbing
  didn't land — **stop, do not proceed to the tab.**
- **Container bet wrong:** if the operator sees the dedicated tab and says "I
  wanted this in the Chat dropdown, not a new tab," we **revert the container** to
  the Chat-tab dropdown and keep the progressive-disclosure content model (it's
  portable). The tab is falsifiable; the content model is not on trial.
- **Level-2 over-built:** if neither the operator nor two friends-and-family
  testers expand "show memory detail" in the first two weeks, trim level 2 — the
  simple view was enough.
- **Attempt-#7 tripwire:** if the closing REVIEW.md contains ANY "documented
  follow-up, not a stop-ship" lacking an owner + date, the sprint has reproduced
  the exact failure pattern of F8 / `__TODO_DEEP_MODEL__` / router `live_model()`
  — it must not ship until that item is folded in or cut.

## Displacement

Saying yes to "make the surface honest" spends ARAIL time that then isn't spent on:

- **The Gemma-4-26B-MoE deep-model-identity question** — this very worktree's
  branch, and by `PROMPT.md §1`'s throughline, arguably the *sixth* attempt at the
  deep-model identity churn. This sprint **explicitly defers** re-picking the deep
  model. That is the *correct* displacement: stop re-choosing the model in the deep
  slot until the surface can tell the truth about whatever sits there.
- **The true-frontier-streaming aeroLLM mode** (`AERO_MOE_SELECT`) stays off and
  un-surfaced → named follow-up.
- **Nucleus teacher-inference-via-aeroLLM** → named follow-up (Decision 4).
- **Cross-product:** aerollm's CUDA backend and aerollm-distill get no attention
  this sprint (ARAIL-only). If the answer to "what does this displace?" were
  "nothing," it would be false — every prior sprint that *added a dormant lane
  instead of closing one* is the displacement pattern the brief warns about. This
  sprint's whole premise is to close, not add.

## Recommended next step

**Proceed to `/architect` (design mode) — behind a hard gate.** Phase 0 (the §2
ledger) closes and ships *first, separately*; the architect designs the Models tab
only on top of a single reconciled honest data list, and must rewrite
`chat-studio.spec.md §3` to record the dropdown→tab deviation. Named follow-ups
(agent-tiering rebind UI, "knowledge tiering" framing, Nucleus teacher-inference)
each get an owner + revisit date in the sprint ledger — no undated deferrals.

**If Phase 0 cannot close, do not proceed — stop and report which gap held.** The
tab is worthless on a foundation that lies, and shipping it anyway is exactly how
this becomes attempt #7.
