# Review: "Cleaner Experience" cleanup pass

**Date:** 2026-07-23
**Build:** BUILD_LOG.md at `cb169e3`
**Architecture:** ARCHITECTURE.md at `3327dec`
**Scope reviewed:** `3327dec..HEAD` (8 WP commits), focus on WP1/WP2/WP3/WP5 correctness & safety.

## Verdict: WEAK_PASS

No BLOCK findings. The high-risk rewiring (WP5 researcher, WP1 boot gating, WP2 consent,
WP3 tier guards) is correct and fails safe. Two ASK-level items should be filed as
follow-ups; neither is ship-blocking.

---

## Spec adherence

Strong. The three headline failure modes from ARCHITECTURE.md are addressed as designed:
fabricated metrics (`0.15/0.72/24/success=True`) deleted, sleep-loop deleted, egress
consent-gated with goal text removed from URLs, tier surfaces enforced server-side. One
spec deviation (A4 baseline fallback) is noted below.

## Code quality / correctness findings

- **[ASK] A4 "lab-capability baseline" fallback not implemented** — `researcher._design_experiment`
  (researcher.py:1236-1258) maps each hypothesis to an archetype or `"unmeasured"`, but nothing
  guarantees *at least one measurable* experiment when every hypothesis maps to nothing.
  ARCHITECTURE.md A4 requires appending a goal-tagged `model_throughput`/`retrieval_quality`
  baseline in that case. Failure scenario: a goal whose hypotheses contain no throughput/
  prompt/retrieval keywords produces a run of all-`unmeasured` cards with zero numbers — honest,
  but the "fresh lab still gets one measured-or-refused experiment" promise is unmet. Mitigated
  in practice because WP7's default goal ("...measure speed...model...") maps to `model_throughput`.
  File as follow-up; not a correctness bug (never fabricates).

- **[INFO] Index rebuild amplification on real observation stream** — each `tracker.observe`
  now fires on genuine per-run measurements (3–9 per experiment) and every `_save` triggers
  `_rebuild_index()` (experiment_tracker `__init__.py:191-200`). With N experiments this is
  many full LanceDB replaces per research run. Pre-existing pattern, but the real engine
  exercises it harder than the old 4-canned-observations path. Not a correctness issue.

- **[INFO] `tracker.complete` is not wrapped** in the step-4 loop (researcher.py). If it raises
  (disk error), the run aborts with that experiment left `in_progress`. Crash-resume re-runs it
  correctly (idempotent `tracker.start`), so this self-heals; noting for completeness.

### Verified correct (WP5)

- **Run/complete/collect flow is sound.** Step 4 runs *and* completes each experiment
  (`run_experiment` → `maybe_interpret` → `tracker.complete`); step 5 is a pure collector
  (`tracker._load` per id). No path double-runs (completed experiments `continue`) and none is
  left uncompleted on the normal path (halt inside a runner still returns a partial `measured`
  result that gets completed).
- **Crash-resume is correct with the single `resume_p < 0.9` checkpoint.** Collapsing the old
  `<0.7`(run)/`<0.9`(analyze) split into one `<0.9` block that both runs and completes is *more*
  correct: on resume in the 0.7–0.9 window, already-completed experiments are skipped by status
  and only the incomplete ones re-run. `test_resume_skips_completed_experiment` asserts
  `ran == [open_id]`. The 0.9+ window skips step 4 entirely and the collector reloads finished
  records.
- **Late-binding closure is correct.** `ctx.observe = (lambda text, data, _id=exp_id: ...)`
  captures the per-iteration id via the default-arg trick; no loop-variable leak.
- **`run_experiment` never raises into the loop** — outer `try/except` (mini_experiments.py:442-445)
  converts any runner bug into `cannot_run` (never fake data); `maybe_interpret` and `_emit` both
  swallow exceptions.
- **Airgapped-safe by construction** — mini_experiments.py imports only stdlib at module scope;
  no network libs, no `arail.*` top-level imports, so no import cycle and nothing to fetch.
- Tracker signatures all match (`observe(id, text, data)`, `complete(id, results, conclusion, success)`,
  `_load`), and `search_for_agents(query)` / `approved_paths()` calls line up.

### Verified correct (WP1)

- `global _MODEL_WARM` declared at top of `_startup`; when the warm task is gated off,
  `_MODEL_WARM = True` is set inline so the `/api/ready` overlay dismisses instantly — no stuck
  overlay. The nested `_init_knowledge_canvas` correctly re-declares its own `global`.
- `pkb_index.ensure_ready` deferred via `asyncio.create_task(asyncio.to_thread(...))`; early
  searches degrade gracefully (design-acknowledged), no broken state.
- `parser.parse_offline` at boot is heuristic-only (no subprocess); researcher auto-start removed
  (goal staged only). Gated tasks (registry thread, preload, prewarm, hybrid CVE scan) all sit
  behind `autochecks.enabled()` (default off) and are pure fire-and-forget — none leaves the portal
  in a broken state when skipped. `health.py` `interval<=0` one-shot is correct.

### Verified correct (WP2)

- No fail-open path. Both `browser._consent_gate` and `buddy._suggest_internet_correlation` check
  `is_airgapped()` **first**, then `store.is_allowed(url)`; the exception handler returns an
  `awaiting_consent`/`None`-observation (closed), never a fetch. Buddy's URL is now the fixed
  `_HF_PAPERS_URL` with zero goal text; correlation is local. Pending requests are de-duped per
  domain. `consent.py` `_save` chmod 0600.

### Verified correct (WP3)

- `_require_surface(surface)` is the FIRST statement in every guarded handler (terminal, notebook,
  notebooks, marimo, plugins ×2, admin, build, tuning) — before body parse/subprocess. Surface
  names all exist in `_TIER_SURFACES["maximus"]`; no legitimate maximus flow 404s (guard reads the
  same `get_current_tier()` the nav uses). Plugin install adds a server-side `confirm_code_execution`
  flag. Marimo token removed from iframe/pop-out URL (no passphrase in history); iframe still loads
  and a click-to-reveal affordance supplies the token to Marimo's own prompt — functional.
  chmod 0600 added to the three secret writes; non-loopback bind warning emitted.

### Verified correct (WP6)

- `conversations/` excluded from `_iter_pkb_files` (closes the `meta.json` title leak). Classifier
  unified: `pkb_index._source_kind_for_path` delegates to `pkb._source_kind_for_rel` (identical
  prefix map — no label drift between full-rebuild and incremental-upsert paths). No top-level
  import cycle (pkb↔pkb_index cross-import only inside functions). `reset.sh` wipes the
  `ARAIL_CONVERSATIONS_DIR` override (guarded to not double-delete a path under the PKB root).

## Test coverage assessment

New/updated tests cover the load-bearing changes: `test_mini_experiments.py`,
`test_autochecks_boot.py`, `test_buddy_internet_consent.py`, `test_tier_route_guards.py`,
`test_research_resume.py` (rewired to stub `run_experiment` and assert no re-run of completed work).
Resume, consent-closed, and tier-404 behaviors are exercised. Gap: no test asserts the A4
baseline-fallback (because it isn't implemented) and no explicit test that an all-`unmeasured`
run produces zero numeric metrics end-to-end. Recommend adding once A4 is decided.

## Tech debt delta

- **Repaid:** two fabrication code paths deleted; two divergent path classifiers unified; boot
  side-effects moved behind an explicit master switch.
- **Added:** minor — index-rebuild amplification under the real observation stream (INFO above);
  the A4 gap leaves a documented-but-unbuilt promise. Net negative (good).

## Required actions before merge

1. None blocking. Ship with notes.

## Follow-up tickets (WEAK_PASS conditions)

1. Implement or explicitly drop ARCHITECTURE.md A4 "lab-capability baseline" fallback so an
   all-unmeasurable goal still yields one measured-or-refused experiment; add the corresponding test.
2. (Optional) Debounce/batch `tracker._rebuild_index` during a run's observation stream.
