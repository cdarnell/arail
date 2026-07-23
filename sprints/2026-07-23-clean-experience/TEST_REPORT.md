# TEST_REPORT — 2026-07-23-clean-experience

**Verdict: PASS** (with 2 documented pre-existing reds, unrelated to this sprint).

Tests were run with the parent repo's venv against the worktree source
(`PYTHONPATH=<worktree>/src:<qukaizen-dac>`), since the worktree has no venv.
`pytest-randomly` is installed, so suites were run with `-p no:randomly` for a
deterministic signal (the suite has pre-existing order-dependence — see below).

## New tests added by this sprint (all green)

| File | Count | Covers |
|---|---|---|
| `tests/test_autochecks_boot.py` | 5 | ARAIL_AUTOCHECKS default-off + toggle; `MODEL_HEALTH_INTERVAL_SEC=0` one-shot; unknown-health resolves usable; `/api/admin/components` no subprocess by default / `?probe=1` shells out |
| `tests/test_buddy_internet_consent.py` | 4 | airgapped→no network; hybrid+no-consent→one pending request, no fetch, no dup; hybrid+consent→fixed URL (no goal words) + local correlation; no-match→None |
| `tests/test_tier_route_guards.py` | 3 | minimalist 404s on 11 maximus routes; maximus serves them; plugin install requires confirmation |
| `tests/test_mini_experiments.py` | 11 | archetype selection; each archetype measured + cannot_run; unmeasured; success-never-defaults-true; **regression** that `0.15`/`0.72`/`data_points` never reappear; provenance_line |
| `tests/test_pkb.py::test_conversations_excluded_from_index` | 1 | meta.json title-leak closed; transcript never indexed |

## Existing suites verified green (isolated runs)

- Boot: `test_boot_warm` (4), `test_boot_grace`, `test_boot_security_scan`,
  `test_aerollm_preload` — 21 total.
- Egress: `test_egress_guard` / `_httpx` / `_bootstrap`, `test_buddy_*` — pass.
- Research: `test_research_resume` (adapted to the engine surface),
  `test_experiments`, `test_researcher_planning_trace`, `test_researcher_swarm`,
  `test_autoresearch_e2e_fake_aerollm` — pass.
- KB: `test_pkb`, `test_pkb_index`, `test_chat_conversations` — pass.
- Portal/setup: `setup_ladder/` (30), `test_world_recolor` (+ maximus fixture),
  `test_admin_models_html_safety` (+ maximus env), `test_token_compliance`,
  `test_build_tab` (18) — pass in isolation.

## Known reds (NOT introduced by this sprint)

1. `test_opencode_config_lifecycle::...test_start_sets_OPENCODE_CONFIG_DIR_env`
   and `test_opencode_lifecycle::TestLogRotation::test_log_rotation_at_10mb` —
   **fail identically on the untouched parent checkout.** Pre-existing.
2. `test_swarm_goal_surfaces::test_research_page_renders_swarm_review_surface` —
   asserts a "Draft Swarm Plan" button that does not exist in the page;
   **fails on parent too.** Pre-existing (a phantom-button drift the assessment
   flagged).
3. `test_r1_r3_chat_models` — order-dependent under `pytest-randomly`; all 29
   pass with stable ordering. Pre-existing flakiness.

## Test-isolation note

A large mixed run (autochecks + tier + world-recolor + build_tab together)
produced 4 `test_build_tab` failures (`FileNotFoundError: no World bundle at
lab/worlds/photography`). These are **test-ordering pollution** — a sibling
suite mutates world-mount / PKB state — and `test_build_tab` passes 18/18 in
isolation. Orthogonal to this change-set. (Also: the worktree was missing the
git-ignored `lab/worlds/{photography,physics}` runtime bundles the parent has;
restored locally for test parity, not committed.)

## Architect review

`REVIEW.md` — verdict **WEAK_PASS**, no BLOCKs. Two follow-ups:
- **A4 (fixed in this pass):** guarantee ≥1 measurable experiment when every
  hypothesis maps to `unmeasured` — a lab-capability baseline is now appended
  (`model_throughput` if a model is resolvable, else `retrieval_quality`).
- **Index-rebuild amplification (deferred, perf-only):** `tracker.observe` now
  fires per measured observation, each triggering a LanceDB replace. Pre-existing
  pattern; noted for a perf follow-up.

## arail QA gating (per workspace CLAUDE.md: 30% setup / 30% Buddy / 20% security / 10% happy / 10% regression)

- **Setup / quiet boot:** unit-proven — no health thread / LLM subprocess /
  component shell-outs at boot with autochecks off; setup-ladder green; the live
  "first byte < 5s on a no-model box" gate is left for a run on real hardware.
- **Buddy / agents:** egress consent-gated, no goal text in URLs, honest outputs
  — proven.
- **Security:** tier guards + plugin confirm + secret perms — proven by
  `test_tier_route_guards` and perms assertions.
- **Happy path / regression:** research flow, resume, boot, KB suites green.

**Shippable** pending a live smoke on Charlie's machine (boot timing, a real
Autoresearch run producing measured tok/s, and the hybrid Buddy egress.jsonl
check) — the parts that need a booted portal + installed model rather than the
headless test harness.
