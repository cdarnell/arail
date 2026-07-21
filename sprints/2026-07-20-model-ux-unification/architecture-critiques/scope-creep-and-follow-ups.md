# Architecture critique — lens: scope-creep-and-follow-ups

**Reviewer:** architect (paranoid pre-build)
**Target:** `sprints/2026-07-20-model-ux-unification/ARCHITECTURE.md`
**Ground truth:** `sprints/2026-07-20-model-ux-unification/PROMPT.md` §6 (and §4, §2.4)
**Verdict:** NOT CLEAN. The doc is deeply self-aware about the anti-follow-up
discipline, and most of its deferrals genuinely comply. But it launders **three
undated deferrals in owner-shaped language**, and one of them re-creates the exact
F8 unread-field bug this whole sprint exists to kill. These must be resolved before
build, because §6 forbids them and the doc's own thesis (attempt #7 avoidance)
condemns them.

The §6 rule being applied:
- Bullet 1: "No new 'dormant lane' behind an env flag without a **committed date**
  to either activate or delete it."
- Bullet 4: "No 'follow-up' ... that isn't also either fixed this sprint or given an
  **explicit owner + next sprint slot**."

An **event trigger** ("when X fires", "when the flag is enabled") is neither a
committed date nor a next-sprint slot. An event that never fires is precisely the
void §1 documents (F8, `__TODO_DEEP_MODEL__`, router `live_model()`). The doc leans
heavily on event triggers and calls that compliance. It mostly isn't.

---

## BLOCK-1 — The `top-level hardware` key is permitted to linger as a second unread field, with no owner and no date. This is F8, re-created, in the sprint whose entire purpose is to kill F8.

**Where:** C1 "Bad input" (line 88) and Tech debt "Added" column (line 194).

- Line 88: "The top-level `hardware` key **MAY remain for one release** for back-compat
  but the nested one is authoritative; **prefer** removing the top-level..."
- Line 194: "`top-level hardware` key **may linger one release** for back-compat
  (**prefer** deleting now)."

This is an undated, ownerless follow-up wearing a "prefer" hedge. "MAY remain for
one release" has:
- no owner,
- no date,
- no next-sprint slot,
- and it deliberately creates a **duplicated field that the frontend does not read**
  (the nested one is authoritative per C1).

That is the literal definition of F8: a server-side field that sits unread. The
sprint's own restatement (line 13) counts "a seventh unread field" as a failure
condition, and F-DEADFIELD (line 143) explicitly widens the dead-field grep to
"**or new top-level `hardware`**" — meaning the architect already knows this is the
same class of bug and still left the door open with "prefer" instead of "delete."

**Required fix:** Delete the top-level `hardware` key **in this sprint, in the same
step (§2.1) that nests it** (implementation-order step 1, line 243). There is no
back-compat consumer — the only reader is the frontend, which this same PR is
repointing at `compact.hardware`. "Prefer deleting now" must become "delete now."
If for some reason it genuinely must linger, it needs owner + a dated deletion slot,
not "one release." As written, this ships the exact bug the sprint is named after.

---

## BLOCK-2 — The reserved "frontier layer-streaming non-goal hook" is a new dormant lane gated on an env flag (`AERO_MOE_SELECT`) with an event trigger and no committed activate/delete date.

**Where:** Tech debt "Added" (line 193), Non-goals (line 232).

- Line 193: "One scoped, explicitly-labeled non-goal hook **is reserved (not built)**
  for true frontier layer-streaming, so the concept is named without faking UI for it."
- Line 232: "One labeled non-goal hook **reserved** only to name the concept.
  **Owner: architect (cross-repo). Trigger: `AERO_MOE_SELECT` actually enabled.**"

Two problems:

1. **It is a dormant lane behind an env flag with no date.** §6 bullet 1 forbids
   exactly this: a lane whose activation is gated on `AERO_MOE_SELECT` (an
   opt-in-and-off env flag — see PROMPT §3, line 226) with only an *event* trigger
   ("when the flag is enabled") and no committed date to activate or delete. This is
   structurally identical to §1 sprint 3's self-hosted GGUF ladder and sprint 5's
   Phase B, both of which §6 bullet 1 cites as still-sitting-there failures. Naming
   it a "non-goal hook" does not exempt it from the env-flag-dormant-lane rule; it is
   the same shape.

2. **It is ambiguous whether it is code or a label — and that ambiguity is itself a
   violation of the anti-attempt-#7 clarity discipline.** "Reserved (not built)"
   (line 193) suggests it is only a named concept, but it appears in the Tech debt
   **"Added"** column (i.e. it adds something to the codebase) and Non-goal #4 (line
   232) gates it on an env flag (implying a code path). Which is it? A comment that
   names the concept is fine. An env-flag-gated code path reserved for later is a
   dormant lane. The doc must not straddle this.

**Required fix:** Either (a) it is purely a comment/doc line naming the concept with
**no env-flag-gated code and no `AERO_MOE_SELECT` branch** — in which case say so
explicitly, remove it from the Tech-debt "Added" column, and drop the env-flag
trigger language; or (b) it is a code hook, in which case it is a dormant lane and
§6 forbids it without a committed date to activate or delete. Given the sprint's
leash, (a) is the only acceptable form. Make it unambiguous.

---

## ASK-3 — The Gemma license mislabel calls itself "a dated hand-off" but is given no date. It is an event-triggered deferral of a known, live, legally-sensitive disclosure bug.

**Where:** Tech debt "Discovered, explicitly OUT of scope" (line 203) and Non-goals
(line 235).

- Line 203: "**Owner: architect (license/disclosure). Trigger: the Gemma
  default-floor sprint (G1) OR the next sprint touching the catalog — whichever comes
  first. Not an env-flag dormant lane; a dated hand-off.**"

The doc explicitly claims this is "a **dated** hand-off" — but there is **no date**.
"G1 or next catalog-touching sprint, whichever comes first" is two event triggers, not
a date. Self-labeling a deferral "dated" while providing no date is exactly the kind
of paperwork-compliance that lets undated follow-ups pass review. Under §6 bullet 4,
a follow-up needs an "explicit owner + **next sprint slot**." "G1" is a named slot and
gets closest to compliance — but it is immediately diluted by "OR the next sprint
touching the catalog," which is an open-ended event that may never occur.

Aggravating factor: this is **not** a cosmetic copy nit. `models_catalog.yaml:239`
labels a Gemma model "Apache-2.0"; the workspace CLAUDE.md "Gemma disclosure
exception" makes Gemma-Terms disclosure a **required** legal obligation, and
license/attribution is on the aerollm paranoid checklist. Deferring a *known,
already-discovered* license mislabel on an event trigger that "may never fire" is the
riskiest category to leave undated.

**Required fix:** Either (a) give it a real committed date (or bind it firmly to G1
as the single owning slot and delete the "or next catalog-touching sprint" escape
hatch), or (b) reconsider folding the one-line catalog string fix into this sprint —
it is a one-token copy change (`Apache-2.0` → the Gemma-Terms label), in the same
`models_catalog.yaml` this sprint already edits at step 4 (line 246). The
"different class of bug (license, not memory/fit)" argument is real for the *full*
disclosure work (NOTICE bundling, verbatim §3.1(4)), but the **mislabel string
itself** is a lie-on-screen of the same family the sprint exists to remove, and it is
being touched in the same file this PR opens. At minimum, stop calling an undated
deferral "dated."

---

## ASK-4 — Three non-goals are gated on event triggers, not dates or named sprint slots. §6 wants dates; events can silently never fire.

**Where:** Non-goals section (lines 229–234).

| Non-goal | Owner | Given "trigger" | Problem |
|---|---|---|---|
| New Models tab (line 229) | visionary | "disconf-#1 fires post-Phase-0" | event, no date |
| aeroLLM frontier streaming (line 232) | architect | "`AERO_MOE_SELECT` actually enabled" | env-event, no date (see BLOCK-2) |
| Real singleton hot-free (line 233) | architect + operator | "disconf-#4 fires" | event, no date |
| Nucleus ↔ aeroLLM (line 234) | architect + operator | "aeroLLM ships HTTP bindings" | event, no date |

Contrast the two that **are** compliant and show the doc knows how to do it right:
- Agent-binding editor UI (line 230): "Owner: visionary. **Revisit: 2026-08-10.**"
- Symbolic CoT / knowledge tiering (line 231): "Owner: visionary. **Revisit: 2026-08-10.**"

Those two have real calendar dates. The other four do not. Some of the event-gated
ones are *defensibly* conditional — the Models tab and singleton hot-free genuinely
should only reopen if disconfirming evidence fires, and "reopen with data, not a
guess" (line 229) is sound product discipline. But §6 bullet 1 is categorical for the
env-flag one (BLOCK-2), and even the legitimately-conditional ones should carry a
**review-by date** so that "the trigger never fired" is caught and revisited rather
than becoming the silent void §1 describes. An event with no backstop date is how a
"non-goal" becomes a permanent orphan.

Note on Nucleus specifically: PROMPT §4 (lines 288–294) demanded Nucleus be scoped as
"an explicit, separate, named phase (own sprint or **clearly-flagged follow-up with
an owner**)." It has an owner, so it clears §4's minimum bar — but it has no date/slot,
so it fails §6 bullet 4. Give it a next-sprint slot or a review-by date.

**Required fix:** Add a review-by date to each event-gated non-goal (the event stays
as the *reopen* condition; the date is the *check-whether-it-fired* backstop). Match
the pattern the two compliant rows already set.

---

## ASK-5 — The "serves: <tier>" read-only chip is designated "first thing to cut," with no owner or landing slot for the scope if it is cut. Cutting it silently drops an explicit operator ask.

**Where:** Non-goals (line 230) and implementation order (line 253).

- Line 230: agent-tiering surfaced as a "**read-only chip only** ('serves: fast'),
  **first thing cut** if the wedge overruns."
- Line 253: "...and the read-only 'serves: <tier>' chip (**first to cut**)."

This chip is the *entire* surviving footprint of PROMPT §0/§4's explicit ask that
"agents must consume model tiers too... surface it somewhere the operator can actually
see and use it" (PROMPT §0 line 41, §4 lines 264–271, §5 Phase-2 line 328). The
architecture has already correctly deferred the *editor* (owner: visionary, dated
2026-08-10) — good. But the **read-only surfacing**, the minimum viable version of the
ask, is marked "first to cut" with **no owner and no slot for where it goes if cut**.
If the wedge overruns and it is cut, the operator's §4 ask lands in exactly the
undated void this sprint is trying to escape — and unlike the editor, nothing else in
the doc catches it.

**Required fix:** If the "serves: <tier>" chip is cut, that cut must route to an owner
+ dated slot (naturally: fold it under the same visionary / 2026-08-10 revisit that
owns the editor). State that explicitly so "first to cut" cannot mean "silently
dropped."

---

## INFO-6 — ETA accuracy: is the spec's ±20% NVMe-probe target *dropped* (trimmed) or *deferred* (still owed)? The doc is inconsistent, which risks a phantom follow-up.

**Where:** Tech debt "Added" (line 192), §2.6 resolution (lines 220–221), Performance
(line 180).

- Line 192 frames the coarse ETA as debt measured against "**the spec's ±20%
  NVMe-probe accuracy**" — implying that target still stands and is owed.
- Lines 220–221 resolve §2.6 by **trimming the doc** to derived-ETA reality — implying
  the ±20% NVMe-probe is *dropped*, not owed.
- Line 180 hedges: "The NVMe/throughput ETA probe (**if a rolling probe is added**)
  must be non-blocking" — speculative optional scope.

These three cannot all be true. If the ±20% NVMe-probe accuracy is trimmed out of the
spec (the §2.6 resolution), then line 192 should stop describing the shipped ETA as
debt-against-that-target, and line 180's "if a rolling probe is added" should either
be committed or removed. If it is deferred, it needs an owner + date like everything
else. As written, it is a soft, ambiguous "maybe later" — the seed of a phantom
follow-up. PROMPT §2.6 explicitly said: "Pick one and update the doc to match — don't
leave a third, different, undocumented behavior." Pick one for the *accuracy target*
too, not just the state machine.

**Suggested fix:** State plainly that ±20% NVMe-probe accuracy is **descoped** (the
rolling-median-with-conservative-default is the accepted end state, not a way-station),
and remove the "if a rolling probe is added" hedge — or, if it is genuinely a future
target, give it an owner + date.

---

## What the doc gets RIGHT (so this isn't read as blanket condemnation)

- The `backend_notice` / F8 handling is exemplary: **delete the dead code** (C7, §2.4,
  lines 118–119, 217–218) plus a regression grep asserting **zero occurrences** so it
  cannot silently return. That is the correct anti-pattern-#7 move, and it is the model
  the top-level-`hardware` key (BLOCK-1) should have followed but didn't.
- The six-state load machine is **trimmed to shipped reality and the doc updated to
  match** (C6, §2.6) rather than left as a spec/impl mismatch — exactly what PROMPT §2.6
  asked.
- The disconfirming-evidence tripwires (#1–#5) are genuine stop-conditions, not
  deferrals, and the HARD GATE on §2.2 (line 244, 255) is the right structural defense
  against scope creep.
- Two non-goals (agent-binding editor, symbolic CoT) carry **real calendar dates**
  (2026-08-10) — proof the author knows the compliant form and simply failed to apply
  it uniformly.

---

## Summary of required actions before build

1. **BLOCK-1:** Delete the top-level `hardware` key in §2.1 this sprint. Remove
   "may linger one release" / "prefer deleting." No duplicated unread field ships.
2. **BLOCK-2:** Disambiguate the frontier-streaming "hook" — make it a pure naming
   comment with no env-flag-gated code (and remove it from Tech-debt "Added"), or drop
   it. No env-flag dormant lane without a committed date; §6 bullet 1.
3. **ASK-3:** Give the Gemma license mislabel a real date or bind it to G1 as a single
   slot (delete "or next catalog-touching sprint"); stop calling an undated deferral
   "dated." Consider folding the one-token catalog string fix into step-4 of this
   sprint.
4. **ASK-4:** Add review-by dates to the four event-gated non-goals; the event stays
   as the reopen condition, the date is the did-it-fire backstop.
5. **ASK-5:** Route the "serves: <tier>" chip's possible cut to owner + dated slot, so
   "first to cut" cannot mean silently dropped.
6. **INFO-6:** Resolve the ETA-accuracy ambiguity — descope the ±20% NVMe-probe
   explicitly, or give it owner + date. No third undocumented "maybe later."
