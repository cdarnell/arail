# Vision: Unified-List Fidelity — make the one model list tell the truth

**Date:** 2026-07-20
**Product:** arail
**Wedge size:** one sprint
**Angle:** unified-list-fidelity (stay inside `docs/chat-studio.spec.md` §3's single list; make its fit/memory data real, live, and trustworthy — add no new tab)

---

## The thesis, stated plainly

Five sprints built real backend truth about memory and fit. None of it reaches
the screen. The screen currently lies in three specific, verified places. The
operator does not need a new surface — they need the surface they already have
to stop lying. This angle refuses to add a tab, refuses to redesign the layout,
and spends the entire sprint making the existing unified list honest. That is
the smallest thing that could possibly close a problem five sprints left open,
and it is the one thing none of the five actually did.

I verified all three lies against live code before writing this (not just the
brief):

- `compact_selector` (`app.py:7811-7839`) builds no `hardware` key, yet
  `chat.html:3765` reads `d.compact.hardware`. Always `undefined`. Telemetry
  shows `—`.
- `renderModelRail` (`chat.html:3296`) reads
  `const verdict = m.fit && m.fit.verdict ? m.fit.verdict : 'good'` off a list
  (`State.models` ← `gallery.installed`) that never carries a `fit` field. Every
  model — including a 26B MoE that does not fit — renders a green **good** chip.
- `/api/chat/eject` (`app.py:6874-6880`) intercepts `aerollm` at the top `if`,
  deletes a cache entry, returns `"ok": true`, and never touches
  `AeroLLMBackend._shared`. The multi-GB singleton stays pinned. The correct
  "cannot hot-eject, restart the portal" branch below it is unreachable.

`AERO_MOE_SELECT` appears nowhere in `src/` — confirmed by grep. The catalog's
claim that gpt-oss-20b runs "selective expert-streaming" is marketing a switch
that is off.

---

## User

A maximus-tier ARAIL operator on a 32 GB Apple M-series laptop who just ran
`ollama pull gemma-4-26b-a4b` (26.5B total params, 13.4 GB on disk), opens the
Chat tab, and has ten seconds to decide: load the 26B or stay on the always-on
`llama-ai-eng`. This is the exact machine and exact model from this session's
live test. Today the screen tells them the 26B is a green **good** fit, shows
`—` for free memory, and — if they load it and later hit Eject — reports success
while the memory stays pinned until they restart the whole portal. They cannot
make the decision the UI exists to help them make, and after one round of
catching the screen contradicting `ollama ps`, they stop believing any of it.

This is not "developers" and not "researchers." It is one person, on one
airgapped machine, trying to answer one question — *will this fit, and can I get
my memory back* — that the current screen answers with three falsehoods.

## Problem

The pain is **trust in the memory picture**, not layout. The operator asked, in
their own words, to "understand the memory situation" and to have "the ability
to unload it." The layout the spec already prescribes (`chat-studio.spec.md` §3:
one list, fit chips, headroom line) is fine. What is broken is that every number
on it is fake or missing:

- Fit is defaulted, not computed → the list actively misinforms.
- Free memory is blank → the operator has no denominator to reason with.
- Unload is a button that lies → the one destructive action they were promised
  does nothing observable and reports victory.

Users describe solutions ("add a model tab," "make it intuitive"). The extracted
problem underneath is narrower and uglier: **the screen has real data available
one function-call away and shows the user a fabrication instead.** Every prior
sprint mistook this for a design problem and re-scoped the layout. It is a
wiring-and-honesty problem. That misdiagnosis is why there have been six
attempts.

## Win condition

Pre-committed, measurable, witnessable on the operator's own machine:

1. **Zero faked fit chips.** Every row's verdict is derived from real
   `free_gb` vs real model size. Falsification test: load `gemma-4-26b-a4b` on a
   machine where it does not fit and confirm the chip reads *requires
   streaming* / *marginal* — never *good*. If any row shows a verdict that was
   not computed from live memory, the sprint fails this criterion.
2. **Telemetry is never `—` when the OS can answer.** `tele-hw` / `tele-vram`
   show real `psutil` / `nvidia-smi` / metal-pressure numbers, and those numbers
   match `ollama ps` / Activity Monitor RSS within ±1 GB at the moment of read.
3. **Every Unload button that exists, works — or does not exist.** For every
   model type the UI offers Unload/Eject, pressing it frees memory verified
   against `ollama ps` / process RSS. For the one case that cannot be hot-freed
   today (the aeroLLM singleton), the button is *absent* and replaced by honest
   copy ("frees on next portal restart"). Binary pass/fail per model type. No
   button reports success without effect. Full stop.
4. **Still one list, no new tab.** `chat-studio.spec.md` §3 is honored, not
   silently deviated from. Any copy that oversells a capability that is off
   (the `AERO_MOE_SELECT` "streaming" claim) is corrected to "resident
   (aeroLLM)."
5. **The trust round-trip.** The operator picks the 26B, reads the fit chip and
   memory line, decides, loads, uses, unloads, and confirms in a terminal that
   the memory returned — **without the screen contradicting the terminal even
   once.** This is the witnessable win: one clean session where the screen and
   the truth never disagree.

If (1)–(3) land and (5) holds for one real session, the hypothesis — *fidelity
alone rebuilds trust* — is proven. Nothing here requires a cloud account;
everything is checkable on the airgapped target machine, which is the correct
friction profile for this user.

## Wedge

Phase 0 of the brief, and nothing more, is the wedge. It is the cheapest
possible test of the whole hypothesis, and it is three edits to code that
already exists:

- **Nest the snapshot.** Put the already-computed `_local_memory_snapshot()`
  into `compact.hardware`. One line. Telemetry stops showing `—`.
- **Read the list that has the truth.** Reconcile the two model lists (or point
  `renderModelRail` at `compact.local_models.items`, which already carries real
  `_fit_verdict_label` verdicts from real `free_gb`). The `'good'` default dies.
  The 26B shows its true verdict.
- **Stop the lying button.** Remove the aeroLLM Eject affordance (the singleton
  cannot be hot-freed in-process today) and render "frees on next portal
  restart" in its place. Delete the unreachable dead branch or make it reachable
  — pick one, no third undocumented behavior.

Shippable in one sprint, as its own PR, before any redesign — exactly as the
brief's Phase 0 demands, so its value is not buried inside a bigger change. This
is the whole bet: if making three numbers real makes the operator trust the
screen, we were right about the diagnosis. If it does not, we learn that cheaply
and the redesign question reopens with evidence instead of a sixth guess.

## Disconfirming evidence

Pre-committed failure signals, so we do not rationalize after the fact:

- **The verdict is present but not actionable.** If the operator sees a real
  *marginal* / *requires streaming* chip and still cannot decide in <10s because
  there is no reason string ("14 GB needed, 8 GB free"), then the problem was
  never fidelity — it was explanation. Shelve the fidelity-only frame; reopen
  layout with the architect.
- **The honest number is too noisy to show.** If live free-memory readings jitter
  enough (metal pressure / psutil churn) that the fit chip flips between *good*
  and *streaming* on refresh, then the source truth is itself untrustworthy and a
  flickering chip is a *new* lie. That falsifies "just wire it up" and forces a
  measurement/smoothing sub-project before any chip ships.
- **Honest absence is worse than the lie.** If removing the aeroLLM Eject button
  confuses the operator more than the false-success did ("why can't I unload the
  second model?"), then honest-absence is the wrong move and we need real
  singleton-freeing (a Rust-runtime change in the sibling repo) before this UI is
  both honest *and* usable — a bigger, separately-scoped bet.
- **The hard shelve trigger.** If Phase 0 ships and the operator's very next
  model-selection session still ends with them opening a terminal to confirm what
  the screen claimed, the fidelity bet failed to build trust. Stop, do not layer
  more UI, escalate to the architect for a different frame.

## Displacement

Saying yes to fidelity-first is saying no, this sprint, to the shiny things —
and that is the entire point, because the shiny things are what pulled the last
five sprints off target:

- **aeroLLM true streaming (`AERO_MOE_SELECT` / frontier layer-streaming) gets
  no UI this sprint.** We surface the resident truth that runs today, not the
  671B-on-24GB vision. This is the honest, deliberate cost: we choose "tell the
  truth about what runs now" over "build the frontier story." Displacing the
  streaming narrative is the discipline the brief is begging for.
- **The Gemma-4-26B-MoE deep-model-identity question — this worktree's original
  task — is deliberately *not* resolved.** This sprint makes whatever model is
  present honest; it does not pick the deep model. That is a displacement and a
  de-risking at once: it stops attempt #6 from becoming the *third* consecutive
  sprint to churn the deep-model identity (35B → 30B → `__TODO_DEEP_MODEL__` →
  re-confirm Qwen → World-hint sidestep).
- **Within ARAIL, spec §4/§5/§8 (tunables panel, dual-model compare, fine-tune
  wizard) wait.** They are spec'd, they are real work, and none of them is the
  trust problem. Milestones M3–M5 of the migration plan get less attention.
- **Cross-product:** engineering hours here are hours not on aeroLLM's CUDA
  backend or aerollm-distill. Named and accepted.

Interrogating "is it really displacement?": yes, unambiguously. The gravitational
pull in this problem area has always been toward the frontier-streaming /
deep-model story. This angle's displacement *is* its thesis: it says "not now" to
that story on purpose.

---

## Explicit decisions (the four the brief forces)

### 1. Tab vs. unified list → **UNIFIED LIST. No new tab.**

`chat-studio.spec.md` §3 already prescribes a single list with per-row fit chips
and a headroom line — no tab split. A dedicated tab is not a design improvement
here; it is the precise re-scope-from-scratch move that §1 documents as the
failure pattern. Adding a tab would mean the sixth attempt *also* invents new
surface instead of closing the open gaps under the existing one. **We stay in the
Chat tab, inside the one list, and we do not touch the layout.** If a future
sprint proves fidelity is insufficient (see disconfirming evidence #1), *then*
the tab question reopens with data. This sprint deviates from the spec in exactly
zero places, so there is no doc-drift to reconcile.

### 2. What "load"/"unload" means — per backend, not one forced model

Two backends, two genuinely different truths. The UI must not force one mental
model onto both (that conflation is §3's named trap).

**Ollama-resident models** (`llama-ai-eng`, `gemma-4-26b-a4b`, `deepseek-r1:14b`,
everything in `ollama list`): binary resident / not, governed by `keep_alive`.
Load = Ollama reads weights into GPU/RAM, a real timed event (~30s cold for a
14 GB q4). Unload = `ollama stop`, genuinely frees memory. **The existing
Load / Unload / WARM affordance is architecturally correct here and stays
unchanged.** The only gap for this backend is fidelity (fit chip + live memory) —
which the wedge fixes. Nothing else to design.

**aeroLLM models** — decide for the case that actually runs today:
- Today's production reality is the **resident singleton** (`_shared` in
  `backends.py:1488-1506`, with a real preload loop in `model_warmth.py` gated on
  metal pressure < 0.60). "Load" is a real one-time heavy event; the cold→WARM
  mental model basically holds. **Design for this case now.**
- **The badge reads "resident (aeroLLM)", never "streaming."** `AERO_MOE_SELECT`
  is off and absent from `src/`; the catalog copy claiming selective
  expert-streaming is corrected to match reality this sprint (guardrail: no copy
  that markets an off switch).
- **Unload for aeroLLM: the button does not exist this sprint.** The in-process
  singleton cannot be hot-freed today. Rather than ship a button that lies
  (§2.3), we remove it and show "frees on next portal restart." A working
  hot-eject requires a Rust-runtime capability check in the sibling repo — that
  is a named follow-up, not this sprint.
- **The true frontier-streaming case (no load state, per-token disk cost, a
  "streaming" indicator instead of a load bar) is explicitly NOT built.** We
  leave one scoped, named hook for it and do not pretend today's UI handles it.
  Conflating the two regimes again is the single most likely way this becomes
  attempt #7, and we refuse it by name.

### 3. Agent tiering in this sprint's UI → **read-only surface, in the same list; the "symbolic chain of thought" concept deferred**

The five-profile `ModelRegistry` binding (`fast`, `reasoning`, `long_context`,
`tool_use`, `build`) is **real and already consumed** by every built-in agent
(`researcher.py`, `deep_policy.py`, `browser.py`, `forge.py`). We do not rebuild
it. In scope this sprint: a **read-only chip on the unified list** — "serves:
fast" / "serves: reasoning" — read from the existing `/api/models` binding data,
so the operator can finally *see*, on the one list, which model each agent tier
resolves to. Today that truth is a settings panel two clicks deep that no test
this session ever surfaced. Making it visible on the list directly serves this
angle's thesis (the one list should tell the whole truth) and is cheap.

Hard boundary — **out of scope, named follow-up:**
- Any *binding editor* UI (changing which model serves a profile from the chat
  list). Read-only only.
- The operator's **"symbolic chain of thought" / "knowledge tiering"** framing.
  §4 confirms this exists nowhere in code or docs — it is a new vision, not a
  hidden feature. It belongs on top of the real `resolve()` mechanism, and it
  needs its own visionary pass. **Follow-up owner: visionary. Revisit date:
  first sprint after this ships (target 2026-08-10).** Not a checkbox here.

The read-only chip is explicitly the **first thing cut** if the wedge + fit
fidelity overruns the sprint. It is additive, not load-bearing.

### 4. Nucleus integration → **out of scope. Named follow-up with owner + date.**

§4's ground truth: Nucleus uses AirLLM for teacher inference today, imports no
aeroLLM/arail anywhere, and the "Nucleus will consume aeroLLM once HTTP bindings
land" line is aspirational. The *working* integration runs the other direction —
ARAIL drives Nucleus's pipeline and registers graduated artifacts back into
ARAIL's registry tagged `"fast"` (`models_api.py:90-143`). "Nucleus building
pipeline will also use this model story" is **new integration work on the Nucleus
side that does not exist**, and dropping it "in addition to" the chat work is
exactly how a seventh unfinished item would be born.

- **In scope, free:** Nucleus-graduated artifacts already register as local
  models tagged `"fast"`, so they already appear in the unified list. We do **not
  special-case them** — they get the same real fit chips as any other registered
  local model. That is the honest, zero-cost Nucleus surface for this sprint.
- **Out of scope, named follow-up:** bidirectional "Nucleus consumes ARAIL's
  model story" integration. **Owner: architect (cross-repo scoping) + operator
  (priority call). Revisit: separate sprint, not before the fidelity wedge ships
  and holds.** No env-flag dormant lane, no undated "in addition to."

---

## A word on the two ambiguous spec items the brief flags

- **`backend_notice` (F8, six weeks open, `app.py:6128-6137`, never rendered):**
  this angle **deletes the dead server-side code.** The honest fit chip + the
  "resident (aeroLLM)" badge supersede the "honest AirLLM label" string. Leaving
  a seventh unread field is the pattern; we cut it.
- **The load state machine (`maximus.plan.md` §5 six states vs. the hardcoded
  `eta_seconds=15, progress=0.15` in `app.py:7191-7237`):** the operator asked to
  "understand the memory situation *during* load." My directional call for the
  architect: **wire real ETA (`on_disk_bytes / measured_throughput`) for Ollama
  loads, and trim the doc's six-state machine to the states we actually
  implement.** No third undocumented behavior. This is an architect decision to
  finalize; I am setting the direction, not the mechanism.

---

## Recommended next step

**Proceed to `/architect` (design mode)** with this draft as the spec, on one
condition the brief itself imposes: **Phase 0 (the wedge) ships as its own PR
first, before the architect designs anything additive.** If Phase 0's three
fixes cannot all be finished — specifically if the aeroLLM eject cannot be made
honest (fixed *or* button removed) — then per the brief, we **stop and say so
explicitly** rather than designing on top of a lying button.

Architecture mode should then design, strictly inside the one list: the
resident-model card (Load/Unload, real memory from the now-wired
`compact.hardware`, real fit chips), the honest aeroLLM card (badge "resident
(aeroLLM)", no Eject button), and the read-only tier chip. It must include the
named restart/cold-start/actually-frees-memory test strategy the brief demands —
the exact bug class already found twice this session.

This is the disciplined bet: no new tab, no new dormant lane, no oversold copy,
no button that lies, and every deferred item carries an owner and a date. If it
still fails to build trust, the disconfirming evidence tells us so cheaply — and
attempt #7, if it is ever needed, starts from a proven-false hypothesis instead
of a sixth blank page.
