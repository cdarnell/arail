# Vision: Model selection UX — minimal-honest-first

**Date:** 2026-07-20
**Product:** arail
**Wedge size:** one sprint (in truth, less — the wedge is mostly wiring)
**Angle:** minimal-honest-first — make every existing affordance truthful before adding anything new. Bias toward deleting or disabling broken buttons over redesigns. The win is trust, not polish.

---

## The thesis, stated plainly

This is attempt #6. The other five failed the same way: real backend machinery gets built, the wiring to the screen breaks or never happens, it gets filed as a "follow-up," and the next sprint re-scopes the whole problem from scratch. Naming churns, dormant env-lanes pile up, nobody goes back.

You do not beat that pattern by designing a better screen. You beat it by refusing to add one square pixel of new surface until the surface that already exists stops lying. The current Chat model UI shows the operator four separate false claims at once — and every one of them is backed by *real, correct backend code that simply never reaches the DOM*. That is not an intuition problem you can lay out your way around. Intuition built on a lying screen is worse than no screen, because it miscalibrates the user with confidence.

So this angle's whole argument is: **the redesign is not the deliverable. Truthfulness is the deliverable. The redesign is a hypothesis we are not yet allowed to test, because we cannot even see whether layout is the problem while the data underneath the layout is fake.**

I verified all six gaps against live worktree code before writing this. They are real, today, in this branch. Receipts are inline below.

## User

The ARAIL operator on an Apple-Silicon Mac with fixed unified memory (the machine this was tested on live this session), who just added `gemma-4-26b-a4b` (26.5B total / 13.4 GB q4 on disk) to the catalog and opened the Chat tab to select it. On that screen, right now, he is shown:

1. a section header reading **"LOCAL · GPU (≤ 8B)"** *over a 26B model*,
2. a green **"good"** fit chip on that 26B model (chat.html:3296 defaults every missing verdict to `'good'`),
3. **"Session Telemetry"** showing `—` for hardware and free VRAM (chat.html:3765 reads `d.compact.hardware`, which is never populated),
4. an **Eject** button that returns `{"ok": true}` and frees nothing (app.py:6874-6880 clears a cache dict; the real singleton stays pinned).

By extension the user is *anyone who forks the blueprint* — the friend or family member ARAIL exists for — who has strictly less patience than the operator and cannot grep the source to discover that the green chip is a lie. The operator is the one hitting the bug live; the forker is the one whose trust we actually spend when we ship it.

This persona is concrete enough to falsify the design against: put gemma-4-26b in front of them and ask "will it fit, and how do I get the memory back?" Today the screen answers both questions wrong.

## Problem

The requested feature is "a genuinely intuitive model selection screen." That is a solution. The problem underneath it is not that the screen is ugly or unintuitive — **it is that the screen is untruthful, and the user cannot trust a single memory-related signal it shows.**

Concretely, the one decision this UI exists to support — *"will this model run on my machine, and how do I reclaim memory when I'm done?"* — is exactly the decision every current affordance sabotages:

- Fit verdicts are hardcoded to `'good'` when the real `fit` data isn't in the list the rail reads. The rail reads `State.models` ← `d.gallery.installed`, which never carries a `fit` field; the list that *does* carry real `free_gb`-based verdicts (`compact.local_models.items`) is never read by the rail (§2.2).
- Memory telemetry is blank because `_local_memory_snapshot()` is returned as a top-level `"hardware"` key (app.py:7865) while the frontend reads `d.compact.hardware` — a nesting the `compact_selector` never performs (§2.1).
- Eject reports success and pins memory until a full portal restart, for the exact case (the streamed/aeroLLM model) the operator called out *by name* when asking for the ability to unload (§2.3).

You cannot design intuition on top of that. Layout polish on a lying data layer produces a *more convincing* lie, which is strictly worse. The problem to solve is trust, and trust is binary per-signal: one visible lie taxes every true thing next to it.

## Win condition

The win is **zero on-screen claims in the Chat model UI that contradict ground truth**, verified by script, not by eyeballing. Pre-committed, measurable thresholds:

1. **Telemetry matches reality.** `tele-hw` / `tele-vram` show real free RAM/VRAM within tolerance of `vm_stat` / `nvidia-smi`, never `—`, on a cold portal.
2. **Every fit chip is computed, never defaulted.** `gemma-4-26b-a4b` shows "requires streaming" or "won't fit" (a real verdict from real `free_gb`), *not* "good"; and it is not filed under a "≤ 8B" header. Threshold: grep the rendered rail for any `'good'` chip whose model size exceeds measured free memory — must return zero.
3. **Every button that exists does what it says.** Press Eject on any model the UI offers Eject for; memory measurably drops, verified by `ollama ps` / process RSS — OR the button does not exist and honest copy stands in its place. No button reports success without effect.
4. **The catalog stops overselling.** `gpt-oss-20b`'s "AeroLLM's native selective expert-streaming backend" copy becomes honest ("resident (aeroLLM)") because `AERO_MOE_SELECT` is off everywhere in `src/` (confirmed — grep returns nothing).
5. **Witnessed win.** The operator opens the Chat tab, selects gemma-4-26b, and reads whether it fits *from the screen* — without opening a terminal to check. If he trusts the screen enough to *not grep*, we won.

**Pre-committed pass/fail for the wedge:** re-run the exact live in-browser test that surfaced these four lies this session. If any of the four (telemetry dashes, fake fit chip, misfiled section, lying eject) still shows, the wedge failed and does not ship as "done."

## Wedge

**Phase 0 from the brief, shipped ALONE as its own PR, before any redesign.** This is the cheapest possible test of the whole thesis, it runs entirely on the operator's own machine with no cloud account, and it is the floor everything else must stand on:

- **§2.1** Nest the existing `_local_memory_snapshot()` into `compact`. Telemetry stops showing dashes. (~1 line of real change.)
- **§2.2** Make the rail read the list that already has real `fit` verdicts (reconcile `d.gallery.installed` with `compact.local_models.items`, or point the rail at the latter). Fit chips become real; the 26B "≤ 8B / good" misfile disappears. This is the root-cause fix, not a chip-color patch.
- **§2.3** aeroLLM Eject: the in-process singleton (`AeroLLMBackend._shared`, backends.py:1488-1506) cannot be freed without a portal restart this sprint. **Minimal-honest-first ruling: delete the Eject button for aeroLLM and show "resident (aeroLLM) · frees on next portal restart."** Do not build hot-eject. Removing a false button *is* the honest move; the honest branch at app.py:6902-6904 already says the true thing — surface its message, make it reachable.
- **§2.4** F8 `backend_notice`: decide now, do not defer a seventh time. Minimal-honest-first bias: if this sprint's honest badges supersede it, **delete the dead server-side code** (app.py:6128-6137). Do not leave a seventh unread field.
- **§2.5** Fix the chat.html:1810 pointer from the phantom `src/arail/chat/gallery.py` to the real `gallery_view()` in `src/arail/chat/__init__.py`. Costs nothing; stops the next session from re-grepping.
- **§3 catalog copy** Change gpt-oss-20b's "selective expert-streaming" to honest "resident (aeroLLM)" copy.
- **§2.6 load state machine** Do NOT build the six-state machine. Trim `docs/maximus.plan.md` §5 to match the `loading`/`ready`/`error` reality that ships today, so the doc stops describing a third, undocumented behavior. Building the state machine is deferred, not this wedge.

That is the entire wedge. It is deletions, wirings, and one doc trim. If it turns out any item needs more than wiring — specifically if §2.2's two lists cannot be reconciled cheaply — that is a signal the sprint is bigger than claimed; surface it and stop, do not quietly expand (that quiet expansion is precisely how sprint 1's "Phase-2, do NOT expand" note got ignored anyway).

## Four decisions this angle commits to (explicitly, so they cannot drift)

**(1) Tab vs. unified list → UNIFIED LIST IN THE CHAT TAB. No dedicated tab.**
`chat-studio.spec.md §3` already prescribes a single list with fit chips. A dedicated tab is a deviation that would require rewriting that spec — and minimal-honest-first refuses net-new surface before the existing surface is truthful. The operator's own verbatim intent says "start in the Chat tab and get that right first." A new tab is exactly the object sprint #7 would build on top of the same unfrozen lies. **We fix the list that exists.** The dedicated-tab question is reserved for *after* the disconfirming-evidence test below proves honesty alone wasn't enough — not before.

**(2) load / unload semantics → THREE distinct meanings, kept distinct in copy. Never one mental model forced onto both backends.**
- *Ollama-resident* (gemma-4-26b, llama-ai-eng, deepseek-r1:14b, …): Load = real weight read (~30s cold, confirmed live); Unload = `ollama stop`, genuinely frees. **The existing Load/Unload/WARM affordance is architecturally correct here — keep it.** The only fix is real fit chips + real memory numbers (§2.1/2.2). No load-model change.
- *aeroLLM resident-because-it-fits* (gpt-oss-20b, Qwen2.5-7B — TODAY's actual production path): Load = a real one-time heavy warm-up; the cold→WARM mental model genuinely holds. Badge says **"resident (aeroLLM)"**, NOT "streaming." Unload is a lie in-process → **this sprint removes the Eject button and shows "frees on next portal restart."** We design for THIS case now, because the catalog and production code (`model_warmth.py`, gated on `metal_memory_pressure() < 0.60`) both point at it.
- *aeroLLM true frontier layer-streaming* (the `research/aerollm/00-04` vision, 671B on 24GB, `AERO_MOE_SELECT` — off everywhere in ARAIL): has **no resident/warm/load concept by design** — every call pays per-layer disk cost. **This sprint builds NO UI for this case.** It is a named follow-up (below). We explicitly forbid the resident-case UI from wearing streaming clothes, and forbid catalog copy from claiming streaming while the resident path runs. Conflating these two regimes again is the single most likely way this becomes attempt #7 — we refuse it by name.

**(3) Agent tiering in this sprint's UI → NOT surfaced as new UI. Named follow-up.**
The tiering system is real and already consumed: `ModelRegistry` binds five profiles (`fast`/`reasoning`/`long_context`/`tool_use`/`build`) via `bind()`/`resolve()`, emits a `FallbackEvent` on every degradation (never silent), and is consumed live by `researcher.py`, `deep_policy.py`, `browser.py`, `_builtin_drafter.py`, `forge.py`; Buddy inherits it transitively. **It is not lying — it is buried two clicks deep in a settings panel.** Invisible-but-working ranks *below* visible-but-lying on the honesty floor's priority order, so surfacing it is deferred as net-new UI. The operator's "symbolic chain of thought / knowledge tiering" framing does **not** exist in code today; if we build toward it, we extend `resolve()` and the five profiles — we do NOT invent a parallel mechanism. Recorded as a named follow-up with owner + date (below), unlike every undated follow-up in §1.

**(4) Nucleus integration → OUT of scope this sprint. Named follow-up with owner + trigger.**
Ground truth (§4): Nucleus uses AirLLM for teacher inference today; there are zero `aerollm`/`arail` imports in `nucleus/`, `nucleus-prototype/`, or `qkz/`; the "aeroLLM once HTTP bindings land" line in CLAUDE.md is aspirational. The real working integration runs the *other* direction (ARAIL drives Nucleus's pipeline via `nucleus_client.py`; graduated artifacts register back via `POST /api/models/register-artifact`, tagged `"fast"`). So "Nucleus will also use this model story" is **net-new cross-repo integration that does not exist**, not a checkbox. Folding it in unscoped makes it the seventh unfinished item — exactly the §1 pattern. Deferred to a named follow-up whose revisit *trigger* is concrete: "when aeroLLM ships HTTP bindings" (an aerollm-repo milestone), not a floating date.

## Disconfirming evidence (pre-committed)

The thesis is: *truthfulness alone, with zero redesign, buys back the trust.* Here is what would prove that thesis wrong, committed before the build:

1. **The honesty fix ships and the operator still can't decide.** After Phase 0, the operator runs the pick-a-model workflow twice. If on the second run he still cannot answer "will gemma-4-26b fit?" *from the screen* in under 10 seconds, then the problem was never truthfulness — it was genuinely information architecture — and minimal-honest-first is falsified. Escalate to a real redesign (tab or unified-list restructure). This is the ONLY condition under which we build new surface.
2. **The "cheap wiring" premise breaks.** If §2.2's two model lists cannot be reconciled without a meaningful refactor, the "one sprint, mostly wiring" claim is wrong; surface it and re-scope rather than quietly expanding.
3. **The singleton turns out to be freeable.** If the underlying Rust runtime *can* release `_shared` in-process, then deleting the Eject button was the wrong honest move — wire a real Unload instead. (We chose deletion because the code today says it cannot; if that's false, honesty points the other way.)

Pre-committing these prevents the post-hoc rationalization that let F8 sit for six weeks: if the wedge fails its test, we say so in the retro, we do not relabel it "documented follow-up."

## Displacement

This is deliberately restraint, so displacement is the whole point.

- **This worktree's own Gemma-4-26B-MoE "deep model identity" work is displaced.** Per §1, that is very likely attempt #6 at the unresolved deep/streamed-model-identity question (35B → 30B → `__TODO_DEEP_MODEL__` → re-confirm Qwen → World-hint sidestep). This angle explicitly does NOT resolve "what is the 2nd/deep model" beyond making the *current* catalog honest. Gemma-4-26B gets a truthful fit chip and an honest badge; it does not get a new identity story this sprint.
- **Deferred, each as a named follow-up (owner: operator; not the undated void of §1):** true frontier-streaming aeroLLM UI (trigger: `AERO_MOE_SELECT` actually enabled); the six-state load machine (trigger: disconfirming-evidence #1 fires); agent-tiering surfacing + the "knowledge tiering" vision extension (trigger: after the honesty floor ships and holds one week); Nucleus↔aeroLLM integration (trigger: aeroLLM HTTP bindings land); any dedicated Models tab or redesign (trigger: disconfirming-evidence #1 fires).
- **Across QuKaiZen's three products:** time on ARAIL's model-UX honesty is time not on aerollm's CUDA backend and not on Nucleus's pipeline. That trade is worth it precisely because ARAIL is the blueprint others fork — a blueprint whose buttons lie poisons trust for all three products, and no downstream feature is worth building on a floor that isn't true.

The honest answer to "what does this displace" is *a lot*, on purpose. The last five sprints displaced nothing and closed nothing. This one displaces every net-new ambition in favor of a floor that finally holds.

## Recommended next step

**Proceed to `/architect` — but on a short leash.** The architect designs, in this order and no further:

1. **Phase 0 (the honesty floor) as its own shippable PR, first and separate** — so its value is not buried inside a bigger redesign and the redesign is not blocked on it. This is 80% of the deliverable.
2. **The resident-model card and the aeroLLM card, honest copy only** — real memory numbers from the now-wired `compact.hardware`, real fit chips from the now-wired per-model data, "resident (aeroLLM)" badge, no Eject button for aeroLLM. Include a named test strategy for "does this survive a portal restart / cold start / actually free memory" — the exact bug class already fixed twice this session.
3. **Nothing else.** Tab-vs-list restructure, agent-tiering surfacing, streaming UI, and Nucleus are all gated behind disconfirming-evidence #1. The architect must write them into ARCHITECTURE.md as explicit non-goals with the named follow-up owners/triggers above — not silence, not "documented follow-up."

If Phase 0 cannot be finished cheaply, the architect stops and says so, rather than designing new UI on top of an un-frozen floor. That refusal *is* the deliverable of the leash.
