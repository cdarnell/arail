# Review: Model selection UX — unified-list fidelity, disclosed honestly

**Date:** 2026-07-20
**Build:** [BUILD_LOG.md](./BUILD_LOG.md) at `692b460`
**Architecture:** [ARCHITECTURE.md](./ARCHITECTURE.md) at `689ced8`
**Synthesis of three lens drafts:** [correctness](./review-drafts/correctness.md) · [honesty-and-guardrails](./review-drafts/honesty-and-guardrails.md) · [ux-intuitiveness](./review-drafts/ux-intuitiveness.md)

## Verdict: WEAK_PASS

All three lenses returned WEAK_PASS with **zero BLOCK findings**. The build faithfully implements every contract ARCHITECTURE.md claims — verified against the actual diff, not the prose — and closes the six-gap brief plus the load/unload lifecycle lies that the design's own adversarial critiques surfaced. No new lies were introduced; the browse-list honesty is real and reaches the DOM.

WEAK_PASS rather than PASS because there are outstanding ASKs. None blocks merge, but each must ship as a dated follow-up ticket (owner + review-by), per the ARCHITECTURE.md non-goal discipline that blocks any undated follow-up. The single most important non-code item is strategic: the entire Phase-0b honest load-state machine is wired to an endpoint the UI does not call, so the load experience is unchanged — the orchestrator/visionary must weigh this against disconfirming-evidence #1 before declaring the wedge won.

## Spec adherence

Strong. Every failure-mode row in the ARCHITECTURE.md table has a corresponding implementation and test, confirmed by the correctness lens against code:

- **Display fidelity (Phase 0):** hardware snapshot nested + top-level key deleted (F-BLANK/F-DEADFIELD); psutil-fallback lie closed (F-FALLBACKLIE); both `'good'`→`'Unknown'` defaults at chat.html 3296 and 3375 (F-FAKEFIT); both header twins de-oversold (F-HEADER); full oversell sweep incl. `streamed:False` fix and Gemma Apache-2.0→Gemma-Terms correction (F-OVERSELL); `backend_notice` deleted (C7); gallery.py→__init__.py pointer fixed (C8); warmth probed not asserted (F-WARMDOT).
- **Load/unload lifecycle (Phase 0b):** fallback-lie closed; honest per-runtime eject with `_validate_local_model_id_relaxed` guard before the `ollama stop` subprocess (F-EJECTLIE/F-EJECT-OLLAMA-FALSE); idle init (F-INITREADY); cache + inflight locks (F-CACHERACE/F-LOADRACE); identity refusal (F-SWITCH); honest cancel (F-CANCEL); timeout-holds-lock (F-TIMEOUT-ORPHAN); real byte-scaled ETA + corrupt-degrade (F-FAKEETA/F-CORRUPT); re-fit precondition (F-REFIT); friendly daemon-down errors (F-DAEMONDOWN).

Acknowledged drift: the load widget is intentionally left unwired (BUILD_LOG step 12), gating additive load UI behind disconfirming-evidence #1. This is documented and defensible, not silent scope drift — but see UX-1 below for its consequence.

## Code quality findings

- [INFO] The two safety-critical tests are non-vacuous: F-TIMEOUT-ORPHAN proves the no-double-residency invariant via a construction counter (`construct_calls == 2`, the refused middle call never constructs), and F-CANCEL is checked at the AST level. The self-deadlock that the design's own C6.2 introduced was caught and fixed with a bidirectional regression test.
- [ASK] **UX-2 — two fit-chip vocabularies share one slot.** Local rows show a memory-fit axis (Good/Marginal/Requires streaming); deep rows show a load-state axis (Resident/Ready to load) in the same chip position with the same colors but different meaning. Clarity, not correctness.
- [INFO] **UX-4 — "Ready to load" renders in the warning-toned 'streaming' chip color** (fitClass fall-through). One-line fix.
- [INFO] **UX-5 — redundant deep-row phrasing:** chip "Ready to load" + label "load to warm" on the same cold row.

## Security findings

- [INFO] `ollama stop <model>` remains the only subprocess; `model` is validated by `_validate_local_model_id_relaxed` and passed as an argv element (not a shell string) before `subprocess.run`. Confirmed still validated — honesty lens verified the guard order.
- [INFO] No new user-input surface, no auth change, no new dependency. New cache/inflight locks introduce no new I/O. XSS escaping extended to new fields (warm, badge, notes) per C2/F-XSS.
- [INFO] License/attribution (paranoid-checklist item): the false `gemma-4-26b-a4b` "Apache-2.0" label is corrected to "Built with Gemma · Gemma Terms of Use" this sprint. The full disclosure package (NOTICE bundling, `licenses/GEMMA-*`, verbatim §3.1(4) notice) remains a dated architect hand-off (Review-by 2026-08-10) — acceptable because the live false claim dies now and only the compliance-completeness audit is deferred.

## Test coverage assessment

Every ARCHITECTURE.md failure-mode row maps to a named test (T-COLD through T-RESTART, plus the unit/integration/regression tables). The two highest-risk paths (timeout double-residency, cancel honesty) have non-vacuous assertions rather than smoke checks. No coverage gaps were flagged by any lens against the changed lines. The load-widget JS is untested because it is intentionally unwired (not a gap in shipped behavior, but see UX-1 — the tested backend is unreachable from the UI).

## Performance assessment

Not a hot path. The added `compact.hardware` nesting is an O(1) re-key; the `ollama ps` warmth probe is the only added request-path I/O and must stay behind the ≤1s-timeout / last-known-fallback guard specified in the test strategy. No lens flagged a regression. No benchmark was required or run.

## Tech debt delta

Matches the ARCHITECTURE.md prediction (net strongly negative). One latent defect discovered during review that the architect did not anticipate — the inflight-lock-leak (COR-1 below) — is strictly a new risk introduced by the C6.2 concurrency work and must be filed before PASS-grade closure. The honesty lens also surfaced a pre-existing warm-dot inconsistency (HON-1) that sits in this sprint's own eject-honesty domain. Both are filed as dated follow-ups below, satisfying the "no undated follow-up" gate. No other unanticipated debt.

## Required actions before merge

None blocks merge (WEAK_PASS). File the following as dated follow-up tickets — each carries owner + review-by so it does not become the dateless-void this sprint exists to kill. Ranked by severity:

1. **[COR-1 — highest] Inflight-lock leak on synchronous raise.** In `_prepare_chat_model_load`, the span between `_CHAT_MODEL_LOAD_INFLIGHT.acquire()` and `task.add_done_callback(_release_inflight_once)` runs outside any try/finally. A synchronous raise there (e.g. in `_local_memory_snapshot` / `_estimate_model_memory_gb`) leaks the inflight lock permanently, bricking all future chat loads until portal restart — strictly worse than the C6.2 bug it neighbors. Low probability (ASK, not BLOCK). Fix: try/except that releases the inflight lock on early failure. **Owner: builder. Review-by: 2026-08-10.**

2. **[HON-1] Warm-dot cleared before eject success is confirmed.** `chat.html:3401` rail-card eject calls `State.warmModels.delete(m.id)` unconditionally before checking `d.ok`, so a failed Ollama eject flips the warm dot to cold. Self-correcting (next `/api/chat/models` probe re-seeds truth) and pre-existing, but it sits in the eject-honesty domain this sprint owns. Fix: gate the delete on `d.ok`, matching `ejectModel()`. **Owner: builder. Review-by: 2026-08-10.**

3. **[UX-1 — strategic, not a builder defect] The load path bypasses the entire Phase-0b honesty machine.** The rail "load" affordance calls `loadModel()` (chat.html:3490) — a 1-token `/api/chat/stream` ping + 1.8s flash — while the honest `/api/chat/model-load` state machine (re-fit "may swap or fail" message, real ETA, daemon-down banner, identity refusal, idle/loading/ready/error) is on an endpoint nothing in the UI calls. So the load experience is unchanged; disconfirming-evidence #1's own condition ("fidelity ships and the load experience is still opaque") is arguably already visible. Architecturally intended and honestly documented — do not treat the honest-but-unreachable backend as shipped UX. **Owner: visionary/orchestrator (weigh before calling the wedge won). Trigger: disconf-#1 evaluation post-Phase-0. Review-by: 2026-08-10.**

4. **[UX-2] Two fit-chip vocabularies in one slot** (memory-fit axis vs load-state axis; same position, same colors, different meaning). **Owner: builder/visionary. Review-by: 2026-08-10.**

5. **[UX-3] "Requires streaming" verdict is jargon that clashes with this sprint's own header fix.** The sprint purged "streaming" from aeroLLM copy as misleading, yet the local column's worst verdict is still "Requires streaming" for a model Ollama merely swaps/fails on. The plain-English version ("may swap or fail") exists only on the unreachable load path. C3 was left UNCHANGED by design, so this is a lens observation, not drift. **Owner: visionary. Review-by: 2026-08-10.**

6. **[UX-4 — INFO] "Ready to load" renders in the warning-toned 'streaming' chip color** (fitClass fall-through). One-line fix. **Owner: builder. Review-by: 2026-08-10.**

7. **[UX-5 — INFO] Redundant deep-row phrasing** — chip "Ready to load" + label "load to warm" on the same cold row. **Owner: builder. Review-by: 2026-08-10.**
