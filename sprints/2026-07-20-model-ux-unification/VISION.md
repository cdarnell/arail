# Vision: Model selection UX — unified-list fidelity, disclosed honestly

**Date:** 2026-07-20
**Product:** arail
**Wedge size:** one sprint

> This is the final, synthesized vision for sprint `2026-07-20-model-ux-unification`.
> It merges three competing framings (minimal-honest-first, progressive-disclosure,
> unified-list-fidelity). Where they disagreed, I made a call and said why — including
> rejecting progressive-disclosure's dedicated-tab bet while keeping its content model.
> The four decisions the sprint brief forces are committed explicitly in their own
> section and are not negotiable downstream without superseding this file.

---

## The thesis

This is attempt #6 at the same problem, and the previous five all failed the same way:
real backend truth about memory and fit gets *computed correctly server-side*, never
reaches the DOM, gets filed as a "follow-up," and the next sprint re-scopes the layout
from a blank page. The screen the operator sees today shows **four false claims at once,
each backed by correct code that simply never renders**:

1. a `LOCAL · GPU (≤ 8B)` header over a 26B model,
2. a green **good** fit chip on that 26B model (`chat.html:3296` defaults every missing
   verdict to `'good'`),
3. `—` for free RAM/VRAM (`chat.html:3765` reads `d.compact.hardware`, which
   `compact_selector` at `app.py:7811-7839` never populates),
4. an Eject button that returns `{"ok": true}` and frees nothing (`app.py:6874-6880`
   clears a cache dict; `AeroLLMBackend._shared` stays pinned).

You do not beat that pattern with a better layout. Layout polish on a lying data layer
produces a *more convincing* lie. The deliverable this sprint is **truthfulness of the
one list that already exists** — not a new surface. The redesign is a hypothesis we are
not yet allowed to test, because we cannot see whether layout is the problem while the
data underneath it is fabricated.

## User

A maximus-tier ARAIL operator on a 32 GB Apple-Silicon Mac, `LAB_MODE=airgapped`, who
just ran `ollama pull gemma-4-26b-a4b` (26.5B total / 13.4 GB q4 on disk), opens the Chat
tab, and has ten seconds to decide: load the 26B, or stay on the always-on
`llama-ai-eng`. This is the exact machine and exact model from this session's live test.

By extension, the user is **anyone who forks the blueprint** — the friend or family
member ARAIL exists for — who has strictly less patience than the operator and cannot
grep the source to discover that the green chip is a lie. The operator hits the bug live;
the forker is whose trust we actually spend when we ship it. Concrete enough to falsify
against: put `gemma-4-26b-a4b` in front of them and ask "will it fit, and how do I get
the memory back?" Today the screen answers both wrong.

## Problem

The requested feature — "a genuinely intuitive model selection screen" — is a solution.
The problem underneath is not that the screen is ugly. **It is that the screen is
untruthful, and the operator cannot trust a single memory-related signal it shows.** The
one decision this UI exists to support — *will this model run on my machine, and how do I
reclaim memory when I'm done?* — is exactly the decision every current affordance
sabotages: fit is defaulted not computed, free memory is blank, and Unload reports
victory while memory stays pinned. Trust is binary per-signal: one visible lie taxes
every true thing next to it. This was misdiagnosed as a design problem five times. It is
a wiring-and-honesty problem, and that misdiagnosis is why there have been six attempts.

## Win condition

Pre-committed, measurable, witnessable on the operator's own airgapped machine — no cloud
account required, which is the correct friction profile for this user:

1. **Zero faked fit chips.** Every row's verdict is derived from real `free_gb` vs real
   model size. `gemma-4-26b-a4b` renders *requires streaming* / *marginal* — never
   *good*, never under a `≤ 8B` header. Falsification: grep the rendered rail for any
   `'good'` chip whose model size exceeds measured free memory — must return zero.
2. **Telemetry is never `—` when the OS can answer.** `tele-hw` / `tele-vram` show real
   `_local_memory_snapshot()` values matching `ollama ps` / Activity Monitor RSS within
   ±1 GB at read time, on a cold portal.
3. **Every Unload button that exists, works — or does not exist.** For every model type
   the UI offers Unload/Eject, pressing it measurably frees memory (verified against
   `ollama ps` / process RSS). For the one case that cannot be hot-freed today (the
   aeroLLM singleton), the button is *absent* and replaced by honest copy ("frees on next
   portal restart"). Binary pass/fail per model type. No button reports success without
   effect.
4. **Still one list, no new tab; no oversold copy.** `chat-studio.spec.md §3` is honored,
   not silently deviated from. The `AERO_MOE_SELECT` "selective expert-streaming" claim
   on `gpt-oss-20b` is corrected to "resident (aeroLLM)" because that flag is off and
   absent from `src/`.
5. **The trust round-trip (the witnessed win).** The operator picks the 26B, reads the
   fit chip and memory line, decides, loads, uses, unloads, and confirms in a terminal
   that memory returned — **without the screen contradicting the terminal even once.** If
   he trusts the screen enough to *not grep*, we won.

**Pre-committed pass/fail for the wedge:** re-run the exact live in-browser test that
surfaced the four lies this session. If any of the four still shows, the wedge failed and
does not ship as "done."

## Wedge

**Phase 0 from the brief, shipped ALONE as its own PR, before any additive design.** It
is the cheapest test of the whole thesis, runs entirely on the operator's own machine
with no cloud, and is the floor everything else must stand on. It is deletions, wirings,
and one doc trim:

- **§2.1 — nest the snapshot.** Put the already-computed `_local_memory_snapshot()` into
  `compact.hardware`. Telemetry stops showing `—`. (~1 line.)
- **§2.2 — read the list that has the truth.** Reconcile the two model lists so
  `renderModelRail` reads real `_fit_verdict_label` verdicts from real `free_gb` (point
  the rail at `compact.local_models.items`, or merge `fit` into `gallery.installed`). The
  `'good'` default dies; the 26B shows its true verdict and leaves the `≤ 8B` header.
  This is the root-cause fix, not a chip-color patch.
- **§2.3 — stop the lying button.** Remove the aeroLLM Eject affordance (the in-process
  singleton `AeroLLMBackend._shared` cannot be hot-freed this sprint) and render "resident
  (aeroLLM) · frees on next portal restart" — the honest branch at `app.py:6902-6904`
  already says this; make it reachable. Delete the unreachable dead branch or make it
  reachable — pick one, no third undocumented behavior.
- **§3 — catalog copy.** Change `gpt-oss-20b`'s "selective expert-streaming" to "resident
  (aeroLLM)".
- **§2.4 — F8 `backend_notice` (`app.py:6128-6137`, six weeks unread).** Delete the dead
  server-side code; the honest fit chip + "resident (aeroLLM)" badge supersede it. Do not
  leave a seventh unread field.
- **§2.5 — fix the `chat.html:1810` pointer** from the phantom `src/arail/chat/gallery.py`
  to the real `gallery_view()` in `src/arail/chat/__init__.py`. Costs nothing; stops the
  next session re-grepping.
- **§2.6 — load state machine.** Wire a real ETA for Ollama loads
  (`on_disk_bytes / measured_throughput`, replacing the hardcoded `eta_seconds=15,
  progress=0.15` at `app.py:7191-7237`) and **trim `docs/maximus.plan.md §5`'s six-state
  machine to the `loading`/`ready`/`error` states that actually ship.** No third
  undocumented behavior. Do not build the six-state machine.

**Presentation within the list — steal progressive-disclosure's content model, reject its
container.** Each row is honest-simple by default (loaded model name, real status dot, a
plain line like "loaded · using ~14 GB · frees when you unload") with real numbers (free
RAM/VRAM, `keep_alive` timer, load ETA) available on a one-click expand. This is the best
idea in the progressive-disclosure framing, and it lives *inside the existing list rows* —
it does not require a new tab.

**Hard gate:** if Phase 0 cannot close — specifically if §2.2's two lists cannot be
reconciled cheaply, or the aeroLLM eject cannot be made honest (fixed *or* removed) —
**stop and say which gap held.** Do not design additive UI on top of a lying floor. That
refusal *is* the deliverable of the leash. If §2.2 needs a meaningful refactor, the
"one sprint, mostly wiring" claim was wrong; surface it and re-scope rather than quietly
expanding — quiet expansion is exactly how prior "do NOT expand" notes got ignored.

## The four decisions the brief forces (committed; do not drift)

### 1. Tab vs. unified list → **UNIFIED LIST IN THE CHAT TAB. No dedicated tab.**

`chat-studio.spec.md §3` already prescribes a single list with per-row fit chips and a
headroom line. **This sprint deviates from that spec in zero places, so there is no
doc-drift to reconcile.** The spec does NOT need updating.

I considered and **reject** the progressive-disclosure framing's dedicated Models tab. Its
strongest argument — "a tab gives the truth room and turns a missing number into a visible
blank (bug) instead of a fake-green chip (lie)" — does not survive this codebase's actual
constraint. A missing number becomes a visible blank the moment the *data path* is
reconciled (§2.2), regardless of container; the tab does not earn that, the wiring does.
And the tab framing's own honest caveat concedes the fatal point: "five sprints already
failed at wiring; a tab that reads the wrong list is still a tab that lies," and "the tab
is explicitly not the wedge." A new tab is net-new surface — precisely the
re-scope-from-scratch move §1 documents as the failure pattern, and the most likely way
this becomes attempt #7. We fix the list that exists. The Chat-tab picker becomes *simple
and honest* (what's loaded, real dot, expand for numbers), which is the version of "get
the Chat tab right first" that actually serves the persona. The dedicated-tab question is
reserved for *after* disconfirming-evidence #1 proves fidelity alone was insufficient —
reopened with data, not guessed a sixth time.

### 2. Load / unload semantics → **THREE distinct regimes, kept distinct in copy. Never one mental model forced onto both backends.**

Conflating these is §3's named trap and the single most likely path to attempt #7. We
refuse it by name.

- **Ollama-resident** (`llama-ai-eng`, `gemma-4-26b-a4b`, `deepseek-r1:14b`, everything in
  `ollama list`): binary resident/not, governed by `keep_alive`. Load = Ollama reads
  weights into GPU/RAM, a real timed event (~30s cold for a 14 GB q4, confirmed live).
  Unload = `ollama stop`, genuinely frees. **The existing Load / Unload / WARM affordance
  is architecturally correct here and stays unchanged.** The only gap is fidelity (real
  fit chip + live memory), which the wedge fixes.
- **aeroLLM resident-because-it-fits** (today's real production path: `gpt-oss-20b-MLX-4bit`,
  `Qwen2.5-7B-4bit`): held in the process-wide singleton `_shared` with a real preload
  loop (`model_warmth.py`, gated on `metal_memory_pressure() < 0.60`). Load is a real
  one-time heavy warm-up, so the cold→WARM mental model holds. **Badge reads "resident
  (aeroLLM)", never "streaming."** Unload is a lie in-process → **this sprint removes the
  Eject button and shows "frees on next portal restart."** We design for THIS case now,
  because the catalog and production code both point at it.
- **aeroLLM true frontier layer-streaming** (the `research/aerollm/00-04` vision, 671B on
  24 GB, `AERO_MOE_SELECT` — off and absent from `src/`): has **no resident/warm/load
  concept by design** — every call pays per-layer disk cost. **This sprint builds NO UI
  for this case.** One scoped, explicitly-labeled hook may be reserved so the concept is
  honestly named, but no fake Load/Unload/WARM renders for it. Named follow-up below.

### 3. Agent tiering → **surfaced this sprint as a READ-ONLY chip on the list. No editor. "Knowledge tiering" concept deferred.**

The five-profile `ModelRegistry` binding (`fast`, `reasoning`, `long_context`, `tool_use`,
`build`; `bind()`/`resolve()`; `FallbackEvent` never silent) is **real and already
consumed** by `researcher.py`, `deep_policy.py`, `browser.py`, `forge.py`,
`_builtin_drafter.py` (Buddy transitively). We do not rebuild it. In scope: a **read-only
chip on the unified list** — "serves: fast" / "serves: reasoning" — read from the existing
binding data, so the operator can finally *see* which model each tier resolves to. Today
that truth is a settings panel two clicks deep that no test this session surfaced. This
directly serves the thesis (the one list should tell the whole truth) and is cheap.

I side with the two framings that surface it over the one that defers it entirely: visible
truth is on-thesis and cheap enough to include. But it is **explicitly the first thing cut
if the wedge + fidelity overruns** — additive, not load-bearing.

Out of scope, named follow-up: any *binding editor* UI (read-only only this sprint), and
the operator's **"symbolic chain of thought / knowledge tiering"** framing, which §4
confirms exists nowhere in code — it is new vision, built on top of `resolve()`, needing
its own visionary pass. **Owner: visionary. Revisit: first sprint after this ships, target
2026-08-10.** Not a checkbox here.

### 4. Nucleus → **OUT of scope. Named follow-up with owner + trigger. One cheap honest slice kept in.**

Ground truth (§4): Nucleus uses AirLLM for teacher inference; zero `aerollm`/`arail`
imports in `nucleus/`, `nucleus-prototype/`, or `qkz/`; the "aeroLLM once HTTP bindings
land" line in CLAUDE.md is aspirational. The real working integration runs the *other*
direction — ARAIL drives Nucleus's pipeline (`nucleus_client.py`) and graduated artifacts
register back via `POST /api/models/register-artifact` tagged `"fast"`
(`models_api.py:90-143`). "Nucleus will also use this model story" is net-new Nucleus-side
integration that does not exist; folding it in unscoped makes it the seventh unfinished
item.

- **In scope, free:** Nucleus-graduated artifacts already register as local models tagged
  `"fast"`, so they already appear in the unified list. We do **not special-case them** —
  they get the same real fit chips as any other registered local model. Zero-cost honest
  Nucleus surface.
- **Out of scope, named follow-up:** bidirectional "Nucleus consumes ARAIL's model story"
  / teacher-inference-via-aeroLLM. **Owner: architect (cross-repo scoping) + operator
  (priority call). Trigger: aeroLLM ships HTTP bindings** (an aerollm-repo milestone), and
  not before the fidelity wedge ships and holds. No env-flag dormant lane, no undated
  "in addition to."

## Disconfirming evidence (pre-committed)

The thesis: *fidelity alone, with zero new surface, rebuilds the trust.* What would prove
it wrong, committed before the build:

1. **Fidelity ships and the operator still can't decide.** After Phase 0, the operator
   runs the pick-a-model workflow twice. If he still cannot answer "will `gemma-4-26b-a4b`
   fit?" *from the screen* in under 10 seconds — e.g. because a real *marginal* chip lacks
   a reason string ("14 GB needed, 8 GB free") — then the problem was information
   architecture, not fidelity. This is the ONLY condition under which we build new surface
   (reason strings first; a tab only if that also fails).
2. **The "cheap wiring" premise breaks.** If §2.2's two lists cannot be reconciled without
   a meaningful refactor, "one sprint, mostly wiring" is wrong; surface it and re-scope.
3. **The honest number is too noisy to show.** If live free-memory readings jitter enough
   (metal pressure / psutil churn) that the fit chip flips between *good* and *streaming*
   on refresh, a flickering chip is a *new* lie — forcing a measurement/smoothing
   sub-project before any chip ships.
4. **Honest absence is worse than the lie.** If removing the aeroLLM Eject button confuses
   the operator more than the false-success did, honest-absence was wrong and we need real
   singleton-freeing (a Rust-runtime change in the sibling repo) — a bigger, separately
   scoped bet.
5. **Attempt-#7 tripwire.** If the closing REVIEW.md contains ANY "documented follow-up,
   not a stop-ship" lacking an owner + date/trigger, the sprint reproduced the exact F8 /
   `__TODO_DEEP_MODEL__` failure pattern — it must not ship until that item is folded in
   or cut.

Pre-committing these prevents the post-hoc rationalization that let F8 sit six weeks.

## Displacement

Restraint is the point, so displacement is large and deliberate — the last five sprints
displaced nothing and closed nothing:

- **This worktree's own Gemma-4-26B-MoE "deep model identity" work is displaced.** By §1's
  throughline this is arguably the sixth attempt at the deep/streamed-model identity churn
  (35B → 30B → `__TODO_DEEP_MODEL__` → re-confirm Qwen → World-hint sidestep). This sprint
  makes whatever model sits in the deep slot *honest*; it does **not** re-pick the deep
  model. That is displacement and de-risking at once.
- **aeroLLM true frontier-streaming (`AERO_MOE_SELECT`) stays off and un-surfaced** →
  named follow-up (trigger: flag actually enabled). We tell the truth about what runs now
  over building the frontier story.
- **Agent-binding editor + "knowledge tiering" vision** → named follow-up (owner:
  visionary, revisit 2026-08-10).
- **Nucleus↔aeroLLM integration** → named follow-up (owner: architect + operator, trigger:
  aeroLLM HTTP bindings).
- **Within ARAIL:** spec §4/§5/§8 (tunables panel, dual-model compare, fine-tune wizard)
  and migration milestones M3–M5 wait.
- **Cross-product:** hours here are hours not on aerollm's CUDA backend or aerollm-distill.
  Named and accepted — precisely because ARAIL is the blueprint others fork, and a
  blueprint whose buttons lie poisons trust for all three products.

## Recommended next step

**Proceed to `/architect` (design mode) — on a short leash, behind a hard gate.**

1. **Phase 0 (the fidelity floor) ships as its own PR, first and separate** — 80% of the
   deliverable, so its value is not buried inside a bigger change and nothing additive
   blocks on it.
2. Then, **strictly inside the one Chat-tab list:** the resident-model row (Load/Unload,
   real memory from the now-wired `compact.hardware`, real computed fit chip, expand-for-
   numbers), the honest aeroLLM row (badge "resident (aeroLLM)", no Eject, "frees on next
   portal restart"), and the read-only tier chip (first to cut). Include the named
   restart / cold-start / actually-frees-memory test strategy — the exact bug class found
   twice this session.
3. **Nothing else.** Tab restructure, binding-editor UI, streaming UI, and Nucleus
   integration are gated behind disconfirming-evidence #1 and written into ARCHITECTURE.md
   as explicit non-goals with the named owners/triggers above — not silence, not
   "documented follow-up."

**If Phase 0 cannot close, do not proceed — stop and report which gap held.** Additive UI
on a lying foundation is exactly how this becomes attempt #7.
