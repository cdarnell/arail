# ARCHITECTURE — "Cleaner Experience" cleanup pass

> Design spec for this sprint's build phase. Produced 2026-07-23 by a design pass over the
> nine-report assessment (`ASSESSMENT.md`, `reports/`); every anchor below re-verified on
> disk at design time. Owner decisions binding this spec are in `SPRINT.md`. The approved
> execution plan (work-package summary + verification gates) also lives at the session
> plan file; this document is the authoritative deep spec.

**Verified ground truth used throughout:**
- Fabricated metrics confirmed at `src/arail/agents/researcher.py:1325-1331` (hardcoded `0.15 / 0.72 / 24 / success=True`), sleep-loop "experiments" at `:923-965`, LLM-invented metrics prompt at `:1298-1306`.
- Real measurement primitives exist and are reusable: `src/arail/experiments/bench.py:160-247` (`run_bench` — TTFT via 1-token warmup, decode tok/s, JSONL persist), `src/arail/experiments/autoresearch.py` (median-of-N, baseline-vs-variant discipline), `lab/tools/benchmark_models.py` (TPS pattern, but it imports `anthropic` at module top — do **not** import it from the engine; copy the pattern from `bench.py` instead).
- `POST /api/models/health/refresh` already exists (`src/arail/portal/models_api.py:54-63`) — the on-demand probe surface for Part B needs no new endpoint.
- `parse_offline` is heuristic-only, no subprocess (`src/arail/skills/goal_parser/__init__.py:186-193`).
- `_require_workbench` gate pattern at `src/arail/portal/app.py:1918-1928`; Marimo token-in-URL at `app.py:2195` and `:2237-2245`; Buddy HF egress with goal text in URL at `src/arail/agents/_builtin_buddy.py:942-951`.
- `compiled_kb.kind_of` public alias at `src/arail/compiled_kb.py:184-187`; the divergent classifier at `src/arail/pkb.py:411-426`; `meta.json` leak via `_PKB_TEXT_SUFFIXES` at `pkb.py:376` + `_iter_pkb_files` at `:391-404`; `ARAIL_CONVERSATIONS_DIR` hole at `src/arail/chat/conversations.py:43-48` vs `scripts/reset.sh:202`.

**Design-time conflict resolutions:**
1. Synthesis P0 "label simulated research output" is **superseded** by the owner's decision to build a real engine. Labeling survives only for model-narrated *interpretation text*, not metrics.
2. docs-drift wants `build-and-finetune-plan.md` deduped into `maximus.plan.md`; the model-path decision wants an unbuilt-plan banner. Do both: banner the canonical (`maximus.plan.md`, per `ROADMAP.md:21`), reduce `build-and-finetune-plan.md` to a pointer stub with the same banner.
3. Implementation checkpoint (WP1): whether `registry.resolve()` (`src/arail/registry/core.py:355,461`) refuses entries whose health is `unknown`. If it filters on `health.usable`, patch resolve to treat `unknown` as optimistically usable (probe-on-first-call).
4. `LAB_EXP_RUNTIME_SEC` is currently a fake-work duration (`researcher.py:930`); it is repurposed (not removed) as a real time *budget* in Part A, so existing `.env` files keep working.

---

## PART A — Real Mini Experiment Engine (the one new subsystem)

### A1. Principles

- Every number shown to the user is computed by code from a real run on this machine, or it does not exist. The engine can return "cannot run" — it can never return invented metrics.
- Airgapped-safe by construction: the module imports no network libraries; all measurement targets are local (registry-resolved local model, the approved PKB, the local vector index).
- Small: one module + tests, sized for one implementation session. This is a teaching lab, not MLflow.

### A2. Module layout

New file: **`src/arail/research/mini_experiments.py`** (~450-550 lines), plus **`tests/test_mini_experiments.py`**.

- Placed under `arail.research` (the Researcher's home turf) with a module docstring explicitly stating: *"This is the Researcher agent's on-device measurement engine. It is distinct from `arail.experiments` (the /tuning inference-tuning loop) — that loop owns git branches and tuning.yml; this engine owns the Autoresearch page's experiments."* This heads off recreating the two-loop conflation.
- Internal structure (single file, three sections): `schema` (dataclasses `ExperimentSpec`, `MiniResult`), `selector` (`select_archetype()`), `runners` (one function per archetype + shared timing helpers adapted from `experiments/bench.py:160-247` — TTFT warmup call, decode-rate computation, median across runs).
- Public API:
  - `select_experiments(hypotheses, parsed_goal, *, model_state, kb_state) -> list[ExperimentSpec]`
  - `run_experiment(spec, *, router, halt_check, pause_wait) -> MiniResult` (async; `halt_check`/`pause_wait` are callables injected by the Researcher so the module never imports portal/jobs state — no import cycles, trivially testable).
  - `check_model_available() -> tuple[router|None, dict]` — wraps `resolve("fast", tab="research")` (same as `researcher._get_router`, `researcher.py:165-177`) plus one direct `health.probe_entry` call. Probing here is allowed under the no-auto-checks rule because a research run is an explicit user action (Part B makes even the bootstrap start explicit).

### A3. v1 archetypes (three — each genuinely measurable on a laptop, airgapped)

1. **`model_throughput`** — model performance measurement/comparison.
   - N=3 repetitions (median + spread) of a fixed short prompt through the registry-resolved router; per-run: `ttft_ms` (1-token warmup, exactly the `bench.py:199-202` technique), `decode_tok_per_sec`, `total_latency_ms`, `tokens_out` (from `resp.tokens_used`, verified available in the router response at `researcher.py:243`).
   - If ≥2 enabled local entries exist in the registry (e.g. `llama-ai-eng` + `qwen2.5:7b` on maximus), runs as a comparison and reports the delta — this *is* the quantization/size-tradeoff archetype whenever two sizes are installed, so a separate fourth archetype is unnecessary on a fresh lab.
   - Justification: reuses the proven TPS pattern; directly serves the new default goal ("find the best small model for my laptop", WP7); teaches TTFT vs decode-rate.
2. **`prompt_variant`** — prompt-engineering comparison scored by deterministic proxies.
   - Builds 2-3 prompt variants for a goal-derived task (bare / structured-instructions / constrained-format), k=3 samples each; code-computed metrics only: `compliance_rate` (deterministic checker: required sections present, valid JSON, length within bound), `median_latency_ms`, `tokens_out`, `consistency` (mean pairwise Jaccard token overlap across the k samples at temp 0.7).
   - Never asks the model for a score. Teaches that prompts are measurable. Model-dependent → honest `cannot_run` without one.
3. **`retrieval_quality`** — quality of the *approved* KB, no model needed.
   - Probes via `pkb.search(query, approved_only=True)` (`pkb.py:613-663`) using goal keywords + approved-doc titles (`compiled_kb.approved_paths()`, fail-closed). Metrics: `approved_docs_count`, `coverage` (fraction of probes with ≥1 hit), `self_retrieval_top1` (query a doc's own title → is that doc ranked first; works because `hash_embedding` is deterministic/local), `median_score`.
   - With 0 approved docs → `cannot_run: "no approved knowledge — approve documents on the Knowledge (DaC) page first"`. This failure mode is itself the lesson the gate design wants to teach, and it runs with no model at all — so a fresh no-model lab still gets one *honest* measured-or-refused experiment instead of theater.

Rejected for v1: any weight training (belongs to the separate 2026-07-22-distill-now sprint), web-source experiments (egress), dataset-eval archetypes needing downloads (airgap).

### A4. Selection and honesty about unmeasurable hypotheses

`select_archetype(hypothesis)` is a deterministic keyword mapper (throughput/speed/latency/model/token → 1; prompt/phrasing/instruction/format → 2; knowledge/retrieval/source/KB → 3). Two rules:
- A hypothesis that maps to no archetype becomes outcome **`unmeasured`** — recorded as hypothesis-only, zero numeric metrics, never `success=True`. This is the honest replacement for fabrication: not everything is measurable on-device, and the UI says so.
- Every run schedules at least one measurable experiment when possible: if no hypothesis mapped, append one goal-tagged "lab capability baseline" (`model_throughput` if a model is usable, else `retrieval_quality`).

### A5. Metrics schema with provenance

Written through the existing `tracker.complete(exp_id, results, conclusion, success)` (`src/arail/skills/experiment_tracker/__init__.py:70-79` — no schema migration needed; `results` is a free dict):

```python
results = {
  "engine": "mini_experiments/v1",
  "archetype": "model_throughput" | "prompt_variant" | "retrieval_quality",
  "provenance": "measured" | "cannot_run" | "unmeasured",
  "outcome": "supported" | "not_supported" | "inconclusive" | "cannot_run",
  "metrics": { ...archetype-specific, code-computed... },
  "runs": 3,
  "model": "llama-ai-eng", "backend": "ollama_native", "entry_id": "...",
  "environment": {"platform": ..., "machine": ...},
  "started_at": iso8601, "duration_sec": float,
  "cannot_run_reason": None | "no local model available" | "no approved KB documents",
  "interpretation": None | {"text": ..., "provenance": "model-narrated"},
}
```

- `success` passed to `tracker.complete` is computed from a per-archetype criterion (e.g. variant B beat A on compliance; model X ≥20% faster) — **never defaults True** (kills `researcher.py:1321,1330` behavior).
- `interpretation` is the only model-authored content: after measurement, the LLM may write 1-2 sentences *about the measured numbers* (metrics included in its prompt), always labeled `model-narrated` — the same vocabulary discipline as the planning trace's `source: "llm"|"heuristic"` (`researcher.py:1208-1246`). With no model: no interpretation at all — the canned "shows promising patterns" fallback at `:1288-1291` is deleted.

### A6. Data flow (goal → UI), and what changes in `researcher.py`

1. **Plan** (`_plan_research`, `:1103-1206`) — unchanged, keeps the planning trace.
2. **Design** (`_design_experiment`, `:1248-1272`) — replaced: calls `select_experiments()`; `tracker.create` stores the archetype, a truthful methodology string ("Measure decode tok/s over 3 runs of …"), and real metric names instead of `improvement_rate/confidence_score`.
3. **Run** (step 4, `:923-965`) — **sleep loop deleted**. For each experiment, `await run_experiment(...)`; each repetition emits a real observation via `tracker.observe` ("run 2/3: 41.2 tok/s, TTFT 612 ms") — the UI liveness the sleeps used to fake now comes from real work. `LAB_EXP_RUNTIME_SEC` becomes a per-experiment time *cap* (engine trims repetitions to fit). Pause/halt honored between repetitions via injected callables (preserves the good `:946-958` cooperative semantics).
4. **Analyze** (step 5, `_analyze_experiment` `:1293-1331`) — **deleted entirely**, both the LLM-invention prompt and the hardcoded-constants fallback. Analysis is now: derived stats computed in the engine + the optional model-narrated interpretation.
5. **KB write** (`_experiment_markdown` `:1333-1379`, `pkb.write_agent_experiment` `pkb.py:693-706`, `write_agent_experiment_rollup` `:709-755`) — markdown gains a provenance header: `**Provenance:** measured by mini_experiments/v1 on llama-ai-eng (3 runs)` or `**Provenance:** NOT RUN — no local model available`; rollup metric keys switch to the real names and show provenance. Location documented (A7).
6. **Report** (`_generate_report`, `:1381-1445`) — the LLM prompt now includes the measured metrics table and the cannot-run summary (fixing "report never receives observations/metrics"); the heuristic fallback prints the actual numbers; the false line "All experiments completed with data collection and analysis" (`:1419-1420`) is deleted; footer gains `Provenance: N measured · M unmeasured · K could-not-run`.
7. **UI** (`src/arail/portal/templates/research.html`) — experiment cards render the `metrics` dict generically plus a provenance badge (reuse the existing LLM/heuristic badge CSS from the planning trace, `:919-920` region); a run-level banner when the router is None: *"No local model — model-dependent experiments were skipped (cannot run). Install one: `ollama pull llama3.2:1b`, then re-run setup or press Retry."* Plus a KB-empty variant for the retrieval archetype pointing at the Knowledge page. Status endpoint (`app.py:3594-3668` region) passes the provenance summary through.

Resume semantics (`:680-718`, `run_state.json`) are untouched — completed experiments reload from the tracker exactly as today.

### A7. Old simulated path & documentation

- **Delete, don't demo-label.** The owner rejected label-only; keeping an "illustrative" mode would preserve the fabrication code path and the identical-constants bug class. Git history is the archive.
- New doc section (rides in WP4's docs work): "Where experiment results land" — raw records `lab/data/experiments/<id>.json` (per `config.py:82`; note: *outside* the PKB, so `reset pkb` does not wipe them — stated explicitly), KB candidates `lab/pkb/agents/experiments/*.md` + `_rollup.md` (raw until human-promoted via the compiled-KB gate), report `lab/pkb/agents/research/<date>_<goal>_report.md`.

### A8. Tests

New `tests/test_mini_experiments.py` with a `FakeRouter` (deterministic text, controllable latency): metrics are computed from actual timing/text; no-model → `cannot_run` with zero numeric metrics; retrieval over a temp PKB + approved manifest; markdown contains the provenance line; a regression assertion that the strings `0.15`/`0.72`/`data_points": 24` no longer appear in researcher output. Update `tests/test_experiments.py`, `tests/test_research_resume.py` (resume path unchanged, fixtures gain provenance fields). `tests/test_autoresearch_e2e_fake_aerollm.py` (tuning loop) untouched.

---

## PART B — No-auto-checks boot

**Master switch:** new env **`ARAIL_AUTOCHECKS`** (default **off** — quiet is the default per owner; `ARAIL_AUTOCHECKS=1` restores today's background loops for power users). One helper module `src/arail/autochecks.py` (`enabled() -> bool`), importable by both portal and registry without cycles. Individual legacy vars (`ARAIL_TIER0_BOOT_WARM`, `ARAIL_AEROLLM_PRELOAD`, …) remain honored as per-feature overrides *within* the master gate.

Per offender (all in `app.py:747-1059` unless noted):

1. **Bootstrap `parser.parse` (`app.py:888`)** → replace with `parser.parse_offline(goal_text)` unconditionally at boot (verified heuristic-only, `goal_parser/__init__.py:186-193`). No deferred LLM re-parse task — the heuristic parse is sufficient for a bootstrap goal, and it removes the 60 s unreachable window entirely rather than moving it.
2. **Registry health thread (`app.py:770` → `core.py:431-438` → `health.py:254-269`)** → when `not autochecks.enabled()`: skip both the thread *and* the initial `run_preflight`. Entries stay `status="unknown"` with `detail="not checked — run ./arailctl doctor or press Check"`. Degradation: "MODEL TIER DOWN" is only emitted from `run_preflight(announce=True)` (`health.py:236-244`), so it simply never fires at boot; the Models pill renders a grey "not checked" state with a Check affordance wired to the **existing** `POST /api/models/health/refresh` (`models_api.py:54-63`, `announce=False` — the loud alarm becomes a quiet pill state). Also honor `MODEL_HEALTH_INTERVAL_SEC=0` as loop-off even when autochecks is on. **Checkpoint:** verify `resolve()` (`core.py:355,461`) treats `unknown` health as usable-optimistic (probe on first call); patch if it filters on `health.usable`.
3. **`/api/admin/components` (`app.py:4754-4853`)** → drop the `version_cmd` shell-outs from the default path; resolve Python packages via `importlib.metadata` (the helper `_pkg_version` already exists inside this handler, `:4761-4767`); shell-only components (ollama/npm/docker/git) return `version: null, "not checked"` unless called with `?probe=1` from a new explicit "Check versions" button in `admin.html`. Page load = zero subprocesses.
4. **`/api/admin/check-updates` auto-fire** → delete the on-load calls in `dashboard.html:1131/1146`; the endpoint and its `/stream` variant remain button-only (the button path is already never boot-grace-gated, `app.py:4863-4866` comment). Airgap gate stays.
5. **`pkb_index.ensure_ready` (`app.py:990-995`)** → wrap in `asyncio.create_task(asyncio.to_thread(...))` so a first-boot LanceDB rebuild can't block first byte (searches degrade gracefully meanwhile; upserts are already debounced). **Knowledge-canvas Neo4j init (`app.py:800-824`)** → move the `await _knowledge_canvas_store.init()` into a create_task; add `ARAIL_SKIP_CANVAS=1` skip flag.
6. **Researcher auto-start from bootstrap (`app.py:904-909`)** → stop calling `researcher.start(parsed)`. Set the goal, emit *"Goal loaded — open Autoresearch and press Approve & Run to start."* The staged goal shows on the dashboard; starting is an explicit click. Keep `_reconcile_interrupted_research` auto-resume (`app.py:871`) — resuming a run the user already started is user-invoked. Update `docs/MACOS.md:52` which documents the old auto-start.
7. **Warm/preload/prewarm/dream/inbox defaults** → `_warm_primary_router` completion call (`app.py:5982-6029`), `aerollm_preload_loop` (`:779`), `_prewarm_claude_cache_task` (`:850`), and the hybrid boot security scan (`:1033-1053`) all go behind `autochecks.enabled()` (each issues model completions or subprocess scans = probes/warmers). When the warm task is skipped, set `_MODEL_WARM = True` inline so the `/api/ready` overlay (`:1083`) dismisses instantly. **Dream daemon (`LAB_DREAMS`, `:1018`) and inbox watcher (`LAB_INBOX_WATCH`, `:844`) keep their current defaults** — they are product features (nightly reflection; 10 s file poll), not package/model probes, and don't touch the boot path; they're listed in the quiet-boot recipe for users who want total silence. Minor: `start-portal.sh:6` keeps `--reload` only under a dev flag.
8. **`setup.sh` model pulls** → default `ARAIL_SKIP_MODEL_DOWNLOAD=1` when non-interactive (`! -t 0`) or when ollama is unreachable; lower `_arail_timeout 900` → `180` on pulls (`setup.sh:845,885,950,969,992`) with a fail-fast message ("run later: `ollama pull llama3.2:1b`"). Setup never appears to hang 15 minutes.
9. **The explicit checkup surface** → extend `arailctl doctor` (`arailctl:365-374`): keep the venv/import checks, add `python -m arail.doctor` (new small module `src/arail/doctor.py`) that runs — explicitly invoked, so probing is fine — registry `run_preflight` + tier table, component versions (importlib.metadata + `ollama --version`), PKB index readiness/staleness, egress mode + guard-installed confirmation, and `--updates` (hybrid only) for the remote check. Document `ARAIL_AUTOCHECKS` + a "quiet boot" recipe in `.env.example:228-257`.

**KEPT at boot (cheap and load-bearing — explicitly unchanged):** `egress.install_guard()` first (`app.py:752-757`), starter-pack/skill/loadout/research-file seeding (`:924-984`, idempotent file writes), conversation orphan sweep (`:786-798`, already threaded), shipped-World seal check (`:829-842`, local hashing, async), world-mount announce, interrupted-research reconciliation.

---

## PART C — Ordered execution sequence (8 work packages)

### WP1 — Quiet boot (Part B) — *owner pain #1*
- **Items:** B1-B9 above.
- **Files:** `src/arail/portal/app.py` (startup, components, check-updates), `src/arail/registry/{core,health}.py`, new `src/arail/autochecks.py` + `src/arail/doctor.py`, `arailctl`, `scripts/setup.sh`, `scripts/start-portal.sh`, `src/arail/portal/templates/{dashboard,admin,_nav}.html`, `.env.example`.
- **Risk:** the `resolve()`-with-unknown-health checkpoint (above); the UI overlay must dismiss when warm is skipped (`_MODEL_WARM` inline flip); Models-pill JS must handle `unknown`.
- **Tests:** update `tests/test_boot_warm.py`, `test_boot_grace.py`, `test_boot_security_scan.py`, `test_aerollm_preload.py`; new tests: no registry thread / no `parser.parse` subprocess when `ARAIL_AUTOCHECKS` unset; `/api/admin/components` spawns no subprocess by default.
- **Verify:** with no model installed, `time ./arailctl start` → first byte < 5 s; activity log contains no "MODEL TIER DOWN" after 5 min idle; `./arailctl doctor` prints the full tier/components table.

### WP2 — Egress honesty (Buddy / Browser / curator messaging) — *owner pain #2*
- **Items:** gate `_suggest_internet_correlation` behind `ConsentStore.is_allowed("huggingface.co")` (create a pending request on first attempt instead of fetching); **remove goal text from the URL** — fetch the un-parameterized recent-papers list and do the goal correlation locally (`_builtin_buddy.py:910-978`). Add consent checks to `browser.py` `browse_url`/`chat` (`:96-101, :220-225`) — `is_allowed(netloc)` else create request and return an "awaiting consent" result; fix the `:5` docstring either way. Reword the Researcher's "N sources auto-approved / awaiting approval" (`researcher.py:900-919`) to state that approval records permission and nothing is fetched (full `fetch_approved` wiring stays out of scope). `chmod 0600` consent files (`consent.py:152-153`).
- **Files:** `src/arail/agents/{_builtin_buddy.py,browser.py,consent.py,researcher.py}`.
- **Risk:** none to airgapped mode (all changes are hybrid-branch only); egress guard untouched.
- **Tests:** extend `tests/test_buddy_suggesters.py`, `test_egress_guard.py`; new: hybrid + unconsented → no HF request, a pending consent entry appears.
- **Verify:** in hybrid, run a Buddy suggest cycle: `grep huggingface.co lab/data/egress.jsonl` shows no hit without a matching allowlist entry, and no URL ever contains goal words.

### WP3 — Security quick wins (gates, secrets, hand-off card)
- **Items:** server-side tier guards (the `_require_workbench` 404 pattern, `app.py:1918-1928`) on `/plugins` + `POST /api/plugins/install` (`:2277, :4032-4042`), `/notebook` + `/api/notebook/start` (`:1830, :1852`), `/marimo` + `/api/marimo/start` (`:2227, :2249`), `/notebooks` (`:2143`), `/terminal` (`:1822`), `/tuning` (`:11053`), `/build` (`:9763`), `/admin` (`:4126`) — routes/URLs unchanged, guard only. Server-side confirm flag + UI warning on plugin install ("clones and pip-installs arbitrary code as you"). `chmod 0600` on `_write_env_kv` / `_patch_lab_conf_password` / `_write_code_server_password` (`app.py:1246-1314`). Remove `?access_token=<ARAIL_PASSWORD>` from the Marimo iframe src and `url_external` (`app.py:2195, 2237-2245`) — match opencode's no-creds-in-URL pattern; replace with a click-to-reveal token affordance (risk note: Marimo will prompt once for the token). Hand-off warning card in `welcome.html` (near `:188-194`) + dashboard: "the dashboard has no login — anyone at this browser can run code, flip egress, and read tokens." Loud banner when `BIND_ADDR` is non-loopback (signal exists at `app.py:9289`).
- **Risk:** tier guards may break maximus users whose `LAB_TIER` is unset/misdetected — guard reads `arail.tier.get_current_tier()`, same source as nav, so parity holds. Full dashboard auth explicitly **deferred** (owner).
- **Tests:** new `tests/test_tier_route_guards.py` (minimalist client → 404 on all nine routes); perms assertions on the three writes.
- **Verify:** `LAB_TIER=minimalist curl -s -o /dev/null -w '%{http_code}' :8080/plugins` → 404; `stat -f '%Lp' .env lab.conf` → 600; `grep -r "access_token=" src/arail/portal/templates/ src/arail/portal/app.py` → no ARAIL_PASSWORD embedding.

### WP4 — Truth-in-UI: the five model surfaces (owner decision 1)
- **Items:** "What can I build here?" explainer panel on `/build` distinguishing persona-wrap vs `build_ai_eng.sh` distillation vs nucleus-dependent `/build` vs `/tuning` (`build.html`, copy near `:90`); actionable nucleus-down state replacing the red dot + silent 502 (`build.html:95-98`, `build_api.py:163-169` error message: "Model building requires the Nucleus pipeline (separate install) — see docs"); "where your model lands" doc mapping the five artifact locations (Ollama store / `lab/models/` / `build/` / `models/graduated/` / nucleus configs tree — new `docs/models-on-disk.md`, folding in A7's experiment-artifact map); `/tuning` disambiguation banner (`tuning.html`, "tunes inference throughput, not weights"); unbuilt-plan banner on `docs/maximus.plan.md` + reduce `docs/build-and-finetune-plan.md` to a banner'd pointer stub; reference `scripts/build_ai_eng.sh` from the docs with its placeholder caveats; relabel the 1210-byte `models/graduated/.../adapters.safetensors` stub (`.placeholder` + reconcile `superskill-spec.yaml`); `__TODO_DEEP_MODEL__` → "configure your deep model" affordance or hidden toggle (`app.py:7032`).
- **Risk:** none functional — copy/docs/templates plus one error message. The actual bake→seal→compact path stays in the distill-now sprint (owner).
- **Verify:** fresh clone, open `/build` with no nucleus: explainer + actionable message, no bare 502; `grep -l "unbuilt" docs/maximus.plan.md docs/build-and-finetune-plan.md`.

### WP5 — Mini experiment engine (Part A) + research-surface truth
- **Items:** all of Part A; plus (same files, so bundled): decouple the two loops on `research.html` — scope the "Every experiment is a git branch" tagline (`:11-15`) and the Experiment Branches panel (`:238-263`) to `/tuning` provenance ("from the /tuning loop") or hide when empty; fix the dead learn-link by adding a `## The research loop` section (anchor `#the-research-loop`) to `docs/agents-explained.md` describing the *new* measured loop (`research.html:271-272`); swarm-lane honesty tooltip ("views of a single Researcher run", `researcher.py:565-680`); fix the "70B+ model" string (`researcher.py:269`) to read the resolved deep entry name.
- **Files:** new `src/arail/research/mini_experiments.py`, `src/arail/agents/researcher.py`, `src/arail/portal/templates/research.html` (+ `research.css`), `src/arail/pkb.py:709-755`, `docs/agents-explained.md`, new `tests/test_mini_experiments.py`.
- **Risk:** the largest package — land after WP1 so runs start explicitly; keep the tracker schema additive so `test_research_resume.py` passes; do not touch `experiments/autoresearch.py`.
- **Verify:** with a model: set goal "find the best small model for my laptop" → run → experiment cards show tok/s numbers that change between runs (not constants), `lab/pkb/agents/experiments/*.md` contains `Provenance: measured`; with Ollama stopped: run completes with visible "cannot run: no local model" outcomes and **zero** numeric metrics — `grep -r "improvement_rate.*0.15" lab/` empty.

### WP6 — KB / DaC button-up
- **Items:** exclude `conversations/` from `_iter_pkb_files` (`pkb.py:391-404`) closing the `meta.json` title leak; wipe-contract — `reset.sh` `reset_pkb()` (`:202`) also wipes the `ARAIL_CONVERSATIONS_DIR` override path (read from env/.env) + document the override in `docs/PRIVACY.md`; unify the path-to-kind classifiers — `pkb._source_kind_for_rel` (`:411-426`) and `pkb_index`'s copy delegate to `compiled_kb.kind_of` (`compiled_kb.py:184-187`); Tier-2 fact-store **ROADMAP/unbuilt** banners on `docs/conversation-memory.md`, `docs/agents.md:143-160`, `docs/adr/0002-*`; rename the nav "DaC" label to "Knowledge" with a small subtitle (`_nav.html:50` — label only, `/dac` route stable); one-line disambiguating headers on the three overlapping DaC approval panels (`dac.html:45-74`).
- **Risk:** classifier unification changes stored labels (`agent_buddy_dream` → `agent_dream`) — existing LanceDB rows keep old labels until reindex; ship a `kb reindex` note or accept-both filtering during transition.
- **Tests:** extend `tests/test_pkb.py`, `test_pkb_index.py`, `test_chat_conversations.py` (meta.json never indexed); new reset-override test if feasible in shell CI.
- **Verify:** create a conversation titled "SECRET-XYZ", reindex, `curl /api/pkb/search?q=SECRET-XYZ` → no hit; `ARAIL_CONVERSATIONS_DIR=/tmp/cx ./arailctl reset pkb` leaves nothing in `/tmp/cx`.

### WP7 — Onboarding & first-run truth
- **Items:** replace the default `ai`-intent goal (`setup.sh:1897-1919`) with "Find the best small model for my laptop — measure speed and responsiveness of what's installed" (directly runnable by WP5's throughput archetype — the first Enter-press now produces *measured* results); one name for the first action — "Set Research Goal" (matches the real button, `research.html:278`) — fixing `setup.sh:2262` ("Run Research"), `app.py:914-921` tip, `docs/missions.md:16,32`, `CLAUDE.md:262`; run the World/mode wizard steps for CLI-onboarded users (redirect to `/welcome?step=world` on first dashboard load when no World mounted, once, dismissible — `app.py:1319`, `welcome.html`); repoint the dashboard runbook banner (`dashboard.html:385`) at `INSTALL.md` (or refresh `the-lab.md:74-119`); reconcile the model footprint — skip the ~5 GB Qwen3-8B snapshot on minimalist (`setup.sh:1744-1751`) or correct `README.md:91` + banner; update `TROUBLESHOOTING.md:159-167` to the real default model; hide the Agents "Activity" stub tab (`agents.html:30,413-414`); intent-aware starter packs (`app.py:920-935` + `pkb_seed`, skip AI primers for non-`ai` intents); `examples/peanut_farmer/README.md` fork+rename walkthrough; INSTALL.md network-mode step; soften passphrase framing + note about explicit research start (replaces the old "starts on its own" note).
- **Risk:** default-goal change interacts with `bootstrap_goal.json` written by setup (`setup.sh:1837`) — keep field shape identical.
- **Verify:** fresh minimalist setup on Apple Silicon downloads ≤ ~1 GB; first dashboard load with no World redirects to the World picker; `grep -rn "Run Research" scripts/ docs/ CLAUDE.md` → empty.

### WP8 — Docs drift & pruning
- **Items:** CLAUDE.md refresh (commit count/date `:149`, surfaces list `:100-121` gains Worlds/DaC/Build, symlink table `:129-130` → both `arail` and `qkz` are symlinks to `arailctl`, stale recent-work paragraph); Docs-tier corrections (`README.md:242/:68`, `CLAUDE.md:120-121`, `INSTALL.md:87` → Docs is every-tier per `app.py:124`); `.env.example:42-44` default-model copy → `llama-ai-eng` (Llama-3.2-1B); legacy `min/med/max` sweep (`AGENTS.md:19`, `BLUEPRINTS.md:67-70`, `REPOSITORY_LAYOUT.md:58`, `.env.example:131`, `setup.sh:1107-1113`); `ROADMAP.md:54` theme names → the four real `LAB_UI_THEME` ids; delete orphaned `teacher.html` + `/api/teacher/*` (`app.py:11444-11534`); drop `/api/pkm/*` aliases (`app.py:10995-11019`, grace window elapsed); refresh the stale `sprints/2026-07-07-portal-design-v2` ledger; reconcile the INDEX.md sprint claims (`docs_registry.py:67` vs `app.py:2318`); one canonical clone URL (`AGENTS.md:122` vs README).
- **Risk:** `/api/pkm/*` removal — grep templates/JS for callers first; `teacher.html` deletion — `write_teacher_qa` in `pkb.py:796-827` stays (it has a caller) but its `/api/teacher/*` wiring goes.
- **Verify:** `grep -rn "min / med / max\|(max)\b" docs/ README.md CLAUDE.md AGENTS.md` → empty; full `pytest tests/` green; `curl /api/pkm/search` → 404.

**Sequencing note:** WP2 and WP3 are independent of each other after WP1 and can interleave; WP5 must follow WP1 (explicit start) and precedes WP7 (default goal targets the new archetype); WP6 and WP4 can slot anywhere after WP3; WP8 last so it documents the end state.
