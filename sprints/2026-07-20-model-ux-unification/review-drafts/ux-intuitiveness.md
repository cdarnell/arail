# Review: Model selection UX — unified-list fidelity (lens: ux-intuitiveness)

**Date:** 2026-07-20
**Build:** BUILD_LOG.md at `692b460`
**Architecture:** ARCHITECTURE.md at `938ff9d`
**Lens:** ux-intuitiveness — read as the frustrated end user seeing this screen for the first time.

## Verdict: WEAK_PASS

The browse-time list is genuinely more honest and less confusing than before —
that half of the wedge lands and reaches the DOM. But the second half of the
lens question — *does loading a model make the memory situation understandable?*
— is not delivered to the user: the honest load-state machine Phase 0b built is
on an endpoint the UI never calls. No new lies were shipped, so this is not a
BLOCK; but the load-time opacity is the single most important thing for the
orchestrator/visionary to weigh before calling the wedge won.

## What genuinely improved (the frustrated user IS less confused browsing)

- The green `good` chip on a 26B is gone; a missing verdict now renders
  `Unknown`, not fake green (both sites, 3322 + active-mini 3422).
- The `Local · GPU (≤ 8B)` header lie is gone; `Local · SSD (streamed)` →
  `Local · aeroLLM` with accurate "kept resident" copy.
- Free memory is now actually visible in three places: the telemetry chip
  (`tele-vram`, populated at 3853), the picker header (`… GB free`, 2192), and
  per-model `est. vram` in the picker option meta (2291). A user CAN line up
  "this model is ~13.4 GB" against "7.1 GB free."
- Warmth reflects real residency (`ollama ps` / `_tier1_resident()`), seeded on
  every fetch — not client-side guesswork.
- aeroLLM vs AirLLM copy is now backend-accurate; deep rows correctly render no
  eject-button lie.

## Findings

### [ASK] The load button bypasses every Phase 0b honesty message — loading a model is still opaque
The rail/active "load" affordance calls `loadModel()` (chat.html:3490), which
fires a 1-token `/api/chat/stream` ping and shows a `flashStatus` line that
self-clears after 1.8s (3128). The entire honest load lifecycle Phase 0b built —
`/api/chat/model-load` → `_prepare_chat_model_load` with the re-fit message
("~14 GB needed, ~8 GB free — may swap or fail"), the real byte-derived ETA, the
daemon-down friendly banner, the model-identity refusal, the idle/loading/ready/
error states — is on an endpoint **nothing in the UI calls**. BUILD_LOG step 12
documents this openly: the `loader-strip` markup has zero JS wiring.

Consequence for the lens: a user clicking "load" on a `Requires streaming` 26B
gets a fleeting "loading…"→"loaded"/"load failed" flash, no memory warning, no
ETA, no guardrail — the exact opacity this sprint set out to kill, fixed at
*browse* time but not at *load* time. This is architecturally intended (the load
widget is gated behind disconfirming-evidence #1, and Phase 0b is honestly framed
as backend-only foundation), so it is **not a builder defect** — but it means
disconf-#1's own trip condition ("fidelity ships and the load experience is still
opaque") is arguably already observable. Route to visionary/orchestrator to weigh
before declaring the wedge won; do not let the honest-but-unreachable backend be
mistaken for a shipped user-facing improvement.

### [ASK] Two fit-chip vocabularies share one slot, on two different axes
Local rows render a **memory-fit** verdict (Good / Marginal / Requires streaming
/ Unknown). Deep rows render a **load-state** (Resident / Ready to load / Not
installed / Streaming). Same chip position, same color mapping, different
semantic meaning — a green "Good" (fits) and a green "Resident" (loaded) sit in
the same column looking identical. The code comment (2077) acknowledges the axes
differ. For a user scanning to decide in <10s, the chip no longer means one
consistent thing. Consider a visual or label distinction between "will it fit"
and "is it loaded."

### [ASK] "Requires streaming" verdict is jargon and now clashes with the sprint's own header fix
The sprint deliberately purged "streamed/streaming" from aeroLLM copy because
aeroLLM keeps models resident. Yet the local-GPU column's worst verdict is still
the literal word **"Requires streaming"** for a model that Ollama will simply
swap on or fail to load — nothing streams a local Ollama model. The plain-English
version already exists on the (unreachable) load path: "may swap or fail." The
browse chip should borrow that plain language rather than a term the rest of the
sprint treats as misleading. (C3's `_fit_verdict_label` was explicitly left
UNCHANGED, so this is a lens observation, not spec drift — but it is exactly the
kind of jargon that keeps the frustrated user frustrated.)

### [INFO] "Ready to load" renders in the warning-toned "streaming" chip color
`fitClass()` (2077) matches good/marg/resident/not-install and falls everything
else through to `'streaming'`. A cold-but-installed, fits-fine aeroLLM row shows
verdict "Ready to load" → no match → 'streaming' color. A ready model wearing the
warning color is subtly off. One-line fix: `if (v.startsWith('ready')) return 'good';`

### [INFO] Redundant deep-row phrasing
A cold aeroLLM row shows chip "Ready to load" *and* warm-label
"installed (aeroLLM) · load to warm" at once — two phrasings of the same state in
one row. Not wrong, just noisy.

## Spec adherence (for this lens)
Implementation matches the architecture's scope exactly, including the deliberate
decision NOT to wire a load widget (Leash / disconf-#1). The findings above are
lens observations about whether the *shipped* surface achieves user-facing
intuitiveness, not builder drift. Phase 0 (display fidelity) reaches the DOM;
Phase 0b (load lifecycle) is honest backend that does not yet reach the user.

## Required actions before merge
None are BLOCK. Recommended:
1. Record in the sprint ledger that load-time understandability is NOT delivered
   this sprint (honest backend, unreachable UI) so it is not mistaken for shipped
   UX — and let the orchestrator decide whether disconf-#1 has already tripped.
2. (cheap, this sprint) Fix the "Ready to load" chip color (one line).
3. (follow-up) Reconcile the "Requires streaming" browse verdict with the
   sprint's own anti-"streaming" copy stance — prefer the "may swap or fail"
   plain language — and consider distinguishing the fit vs load-state chip axes.
