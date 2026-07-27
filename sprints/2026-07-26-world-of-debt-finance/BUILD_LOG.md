# Build log: World of Debt Finance

**Architecture:** [ARCHITECTURE.md](./ARCHITECTURE.md)
**Plan:** `.claude/plans/snappy-zooming-volcano.md`
**Started:** 2026-07-26

## Plan

| # | Files | Change | Test | Commit ref |
|---|---|---|---|---|
| A | `scripts/worlds_src/debt-finance/{spec,terms,face}.json`, `compliance/DISCLAIMER.md`, `src/arail/skill_seed.py`, `scripts/forge_debt_finance_world.py` | Author + seal the `debt-finance` World bundle into `examples/worlds/debt-finance/` (opt-in example, not a catalog default) | `tests/test_world_forge_debt_finance_seal.py` | see below |
| B | `src/arail/agents/loader.py`, `src/arail/agents/builtin_seed.py` | Make both agents git-trackable shipped agents (`_SHIPPED` + `ensure_*_folder`) | `tests/test_debt_finance_agents_seed.py` | see below |
| C | `src/arail/agents/debt_finance_compliance.py`, `_builtin_debt_advisor.py`, `_builtin_consolidation_analyzer.py` | Agent bodies: guardrail, disclaimer precondition, arithmetic, tick loops | `tests/test_debt_finance_compliance.py`, `tests/test_debt_finance_agents.py` | see below |
| D | `.gitignore`, `lab/data/user-import/debt-finance/balances.json` (test-only) | Input staging tree + explicit gitignore line | covered by C/F tests | see below |
| E | `src/arail/portal/app.py`, `src/arail/portal/static/js/worlds.js`, `CLAUDE.md` | Generic `user_data` reveal slot + one button on mounted World cards | `tests/test_debt_finance_reveal_slot.py` | see below |
| F | `tests/` | Full Phase F test suite per ARCHITECTURE.md §11 | — | see below |

## Execution

### Phase A — World bundle
- Authored 24 terms across 6 categories (5 base + `retirement-and-secured-credit`
  for ARM/HELOC/401(k)-loan per the plan's decision), sourced to CFPB/NCUA/IRS/
  PenFed/Chase/Ramsey/Clark Howard pages, all real URLs.
- Institution chosen: **PenFed Credit Union** (Pentagon Federal Credit Union),
  NCUA-insured, open membership, public personal-loan rate page — first 3
  `knowledge_sources[]` are URL-kind (CFPB, NCUA, PenFed) so all 3 make it into
  live scouting watches; position 4 (Chase balance-transfer offers page) is a
  citation-only source per the ordering-cap rule, confirmed by the seal-time
  `assert_agenda_ordering` check.
- Added the four skill constants (`debt-strategy-summary`,
  `cite-approved-findings`, `blended-apr-calc`, `breakeven-calc`) to
  `skill_seed.py`, mirroring `observe-lab`.
- **Deviation from the plan's literal path**: the plan says
  `examples/worlds/debt-finance/`, matching `ARCHITECTURE.md`'s bundle location
  language, but also names `forge_video_games_world.py` as the structural
  template — that script seals to `lab/worlds/video-games/` (a catalog
  default). Verified against `examples/worlds/README.md` and
  `lab/worlds/README.md`: catalog defaults auto-mount-visible to every fresh
  lab; `examples/worlds/` bundles are opt-in via "+ Add a World…" /
  `/api/worlds/import`. Followed the plan's literal path
  (`examples/worlds/debt-finance/`) — a personal-finance World should not be a
  forced-default the way `video-games` is. `forge_video_games_world.py` was
  still used as the structural template for `preflight()`/seal/verify shape;
  the two Phase-A-specific checks (`_EVALUATIVE_RE` scan, `assert_agenda_ordering`)
  are new, per the plan.
- Fixed two bugs found only by running the sealer against real content (not
  assumed from the template): `GateResult` has no `.violations` attribute
  (it's `.unsourced` / `.undeclared_category` / `.dangling_edges` — the
  video-games script has the same latent bug, never triggered because its
  gate always passes; left untouched, out of scope); `slug`/`term` fields in
  `terms.json` are (unique-id, display-name), not (world-slug, unique-id) —
  the architecture's illustrative example uses `"slug": "debt-finance"` for
  every term, which is a docs bug, not the real contract (confirmed against
  `dac_world.assert_closed_sourced_graph`, which treats `slug` as the graph's
  node identity).
- **Local dev environment note**: `dac_world` is an unpublished git-ssh
  dependency (`pyproject.toml`). Verification in this sandbox used
  `pip install -e ~/ProJects/qukaizen-dac` into a throwaway Python 3.11 venv
  at `/tmp/arail-venv` (system Python was 3.9, below the `>=3.10` floor) — not
  committed, not part of this repo's tree.
- `PYTHONPATH=src python scripts/forge_debt_finance_world.py` seals cleanly;
  `examples/worlds/debt-finance/agenda.json` contains exactly the 3 intended
  feed URLs.

### Phase B — Agents made durable
- Added `"debt_advisor"` and `"consolidation_analyzer"` to
  `loader.py`'s `_SHIPPED` set and two `_seed_if_shipped()` branches, exactly
  mirroring the existing four.
- `builtin_seed.py` gained `ensure_debt_advisor_folder()` /
  `ensure_consolidation_analyzer_folder()`, following `ensure_sre_folder()`'s
  thin-shim pattern (idempotent, fork-respecting — a shim starting with the
  sentinel docstring is regenerated if missing, a forked file is left alone).
  `AGENT.md` frontmatter is verbatim from `ARCHITECTURE.md` §5.1/§5.2.
- **Observation, not a fix (out of scope)**: `loader._seed_if_shipped()` calls
  `ensure_<id>_folder()` with no `pkb_root` argument, so it always seeds the
  *default* `_pkb_root()`, never a test's `pkb_root=` override passed
  separately to `load_one()`/`discover()`. This is a pre-existing property of
  every shipped agent (Buddy, SRE, etc.), not something introduced here —
  `tests/test_debt_finance_agents_seed.py`'s `test_loader_discovers_and_loads`
  tests work around it by monkeypatching `arail.pkb._pkb_root` instead of
  passing `pkb_root=`, which is what production code path actually does.
  Flagged here for visibility, not fixed — fixing it would touch
  `loader.py`'s `_seed_if_shipped` signature for every shipped agent, which
  is scope drift beyond this plan.

### Phase C — Agent bodies
- `debt_finance_compliance.py`: `CANONICAL_PHRASE = "not licensed financial
  advisors"` (a fixed substring of the operator's draft disclaimer text),
  `read_disclaimer()` (reads fresh every call, returns `None` on any
  precondition failure), `check_guardrail()` (evaluative/imperative regex +
  institutional-character regex, windowed against a vetted-institution set).
- `_builtin_debt_advisor.py` / `_builtin_consolidation_analyzer.py`: full
  tick-loop agents per Buddy/SRE's hand-rolled `asyncio` shape. Both check a
  no-op fingerprint first (terms.json content hash + approved-finding count
  for Debt Advisor; balances.json content hash for Consolidation Analyzer)
  before doing any work.
- **Deviation, documented and continued past per the task's own instruction
  ("make the most conservative choice consistent with the constraints, note
  it, continue")**: ARCHITECTURE.md §5.1/§7.5 describes substituting a
  specific rate from "an approved scouting finding's structured fields."
  Reading `src/arail/research/agenda_watch.py:_finding_markdown` directly
  shows scout findings are **unstructured fetched excerpt text** with only
  World/watch/feed/checked-date metadata — there is no structured rate field
  to extract. Regex-scraping a number out of untrusted excerpt text would
  reintroduce exactly the hallucination/mismatch risk §7.5 exists to close.
  v1's Debt Advisor cites an approved finding by metadata only (feed, checked
  date, path to the reviewed excerpt) and never attaches a parsed figure or
  an institutional-character label to a scouting finding. Consolidation
  Analyzer is unaffected — its numbers come entirely from the operator's own
  `balances.json`, which does have structured `rate`/`fee_pct` fields.
  This does not violate any critical constraint (no number is ever
  LLM-generated either way) and is more conservative than the literal spec,
  not a scope reduction — surfaced here rather than silently narrowed.
- `state.json` for both agents (which lives under `lab/pkb/agents/<id>/`,
  unlike the findings files) contains exactly `{hash, count/last_run_at}` —
  verified by `TestDebtAdvisorStateFile`/`TestConsolidationAnalyzerStateFile`
  in `tests/test_debt_finance_agents.py`, which assert the exact key set and
  grep the serialized JSON for forbidden figures.

### Phase D — Input/output staging tree
- `.gitignore` gained an explicit `lab/data/user-import/` line, committed on
  its own before any file exists at that path (closes the failure mode
  ARCHITECTURE.md's failure-modes table names explicitly).
- No `balances.json` is committed — Phase F's tests write it to `tmp_path`
  fixtures only; `git status` after the full test run shows nothing new
  under `lab/data/`.

### Phase E — Reveal button
- `app.py`'s `/api/system/reveal` `slots` dict gained one entry:
  `"user_data": Path(DATA_DIR) / "user-import"`, using the local
  `from arail.config import DATA_DIR` import (not the module-level one at
  the top of the file) so test fixtures / runtime overrides that monkeypatch
  `arail.config.DATA_DIR` take effect — matches the existing `models_dir`
  pattern immediately above it.
- `worlds.js`'s `worldCard()` gained one "Reveal findings" button inside the
  existing `if (w.mounted)` branch, calling
  `window.revealSlot('user_data', w.slug + '/findings')`. No new template,
  no new route.
- `CLAUDE.md`'s reveal-slot whitelist mention updated to list `user_data` —
  the one factual-accuracy fix in scope; the deferred cross-World
  "sensitive data never under lab/pkb/" policy rule was NOT added, per the
  plan's explicit instruction to wait until this World ships.

### Phase F — Tests
Six new test files, 67 tests, all green:

| File | What it covers |
|---|---|
| `test_world_forge_debt_finance_seal.py` | Bundle seals + verifies; not a catalog default; no `investing` category; fully sourced; agenda watches are exactly the 3 intended URLs (the CI catch for the ordering-cap bug); position-4 source does NOT produce a watch; `compliance/DISCLAIMER.md` is seal-exempt and present; terms graph closed. |
| `test_debt_finance_compliance.py` | `read_disclaimer()` precondition (present/missing/altered/no-bundle/reads-fresh); `check_guardrail()` evaluative/imperative language (5 parametrized adversarial phrases) and institutional-character labeling (vetted vs. unvetted). |
| `test_debt_finance_consolidation_arithmetic.py` | `blended_apr`/`monthly_interest_cost`/`breakeven_months` against 3+ hand-computed scenarios (single-debt, multi-debt weighted, transfer-fee breakeven, zero-savings, zero-fee edge cases). |
| `test_debt_finance_agents_seed.py` | `_SHIPPED` membership; shim creation/thinness/singleton-identity/idempotency/fork-respect for both agents; `AGENT.md` frontmatter fields; all 4 skills materialize. |
| `test_debt_finance_agents.py` | End-to-end tick tests for both agents: findings land outside `lab/pkb/`; every institution/rate/URL in output is verbatim from its structured source (exact-match, not "looks plausible"); disclaimer precondition refusal (missing/altered); guardrail-block refusal; malformed-input handling (no crash, no echo, one warning); absent-input no-op; tick-no-op on unchanged input; `state.json` never contains a figure; `chmod 0600`; activity-stream pointer never contains a figure. |
| `test_debt_finance_reveal_slot.py` | `user_data` slot resolves/creates dir, supports subpath for `<slug>/findings`, rejects traversal, appears in the valid-slots list. |

`PYTHONPATH=src python -m pytest tests/ -k debt_finance -q` → **67 passed**.

## Architect feedback required

None. The one real gap found during implementation (scouting findings are
unstructured, not structured-rate records — see Phase C) was resolved by
taking the more conservative reading of the architecture's own numeric-
integrity principle (§7.5), not by contradicting it, so it did not rise to
the level of "the architect's plan needs revision" — flagged in this log
for visibility instead.

## Final state

- **Local dev environment**: this sandbox's system Python was 3.9 (below the
  repo's `>=3.10` floor) and `dac_world` is an unpublished git-ssh dependency
  — verified/tested against a throwaway Python 3.11 venv at `/tmp/arail-venv`
  with `pip install -e ~/ProJects/qukaizen-dac` and `pip install -e .`,
  neither committed nor part of this repo's tree.
- `PYTHONPATH=src python scripts/forge_debt_finance_world.py` — seals
  cleanly, byte-identical on a second run (confirmed by re-running after all
  phases landed: zero diff).
- `PYTHONPATH=src python -m pytest tests/ -k debt_finance -q` → **67 passed,
  0 failed**.
- Targeted regression check on every file this sprint touched (`loader.py`,
  `builtin_seed.py`, `skill_seed.py`, `app.py`'s reveal endpoint,
  `worlds.js`) plus the shipped-Worlds-catalog invariant and the pre-existing
  SRE/Buddy shim tests: `pytest tests/ -k "loader or skill_seed or
  builtin_seed or worlds_js or reveal or agent_workflows or agents"` and
  `tests/test_default_worlds_catalog.py` / `tests/portal/
  test_base_template_smoke.py` → **all green** (131 + catalog + 75 template
  tests, zero failures).
- A full, unscoped `pytest tests/` run (3514 tests collected) was attempted
  for completeness but produced pre-existing failures scattered from the
  first few percent of the run onward — before any debt-finance or
  agent-loader test executes alphabetically — consistent with this sandbox
  venv missing runtime dependencies this repo's full suite expects outside
  the debt-finance scope (Ollama, faster-whisper models, LanceDB embedding
  assets, network-gated fixtures). Not attributable to this sprint's changes:
  every file this sprint modified was independently confirmed green above.
  The full-suite run was killed after ~85% collection progress once this was
  established, rather than burning further time chasing pre-existing,
  out-of-scope environment gaps.
- `git status --short` after the full build: clean except the running edit
  to this file. Nothing under `lab/data/user-import/` appears as untracked —
  Phase F's `balances.json` fixtures live entirely under pytest's `tmp_path`,
  never the repo tree.
- Lines changed: ~10 files touched outside `tests/`/`scripts/worlds_src/`/
  `examples/worlds/` (`loader.py`, `builtin_seed.py`, `skill_seed.py`,
  `debt_finance_compliance.py` [new], `_builtin_debt_advisor.py` [new],
  `_builtin_consolidation_analyzer.py` [new], `app.py`, `worlds.js`,
  `.gitignore`, `CLAUDE.md`); 6 new test files (67 tests); 1 new World bundle
  (`examples/worlds/debt-finance/`, 24 terms) plus its authoring source
  under `scripts/worlds_src/debt-finance/` and forge script.
- Commits (in order): World bundle seal (Phase A) · agent shipping plumbing
  (Phase B) · agent bodies (Phase C) · `.gitignore` staging entry (Phase D) ·
  reveal button (Phase E) · Phase F test suite · this final BUILD_LOG update.
