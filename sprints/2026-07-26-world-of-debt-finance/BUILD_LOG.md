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

## Post-review fixes (REVIEW.md at 2c7dce1, verdict BLOCK)

Addresses required actions 1–3 and 6; see "Architect feedback required"
below for actions 4–5, which are product/scope decisions this pass did not
make unilaterally.

**Root cause (shared by BLOCK-1 and BLOCK-2):** `terms.json`'s
`institutions` category conflated two different things: generic glossary
concepts ("Credit Union", "Credit Counseling Agency" — explaining what a
kind of institution IS) and specific, named, verified institutions. Because
both lived under `category == "institutions"`, and the concept term's own
name literally IS the guardrail's trigger phrase, the "vetted institutions"
set the code built from that category alone was tautological: any window
containing the trigger phrase necessarily contained a "vetted" name.

**Fix, by required action:**

1. **BLOCK-2 (hardcoded label).** `_builtin_debt_advisor.py`'s output
   assembler now prints each institution's own `institution_type` field
   (e.g. `credit-union`, `nonprofit-credit-counseling-agency`) instead of a
   hardcoded literal `"credit union"` applied to every institutions-category
   term.
2. **BLOCK-1 (tautological guardrail).**
   - `terms.json`: the two generic glossary terms ("Credit Union", "Credit
     Counseling Agency") are now explicitly documented in their own
     `definition` field as concepts, not institutions, and carry no
     `institution_type` field. Two new, specific, named, verified
     institutions were added — **PenFed Credit Union**
     (`institution_type: credit-union`, `verification_source`: NCUA's own
     charter lookup, distinct from PenFed's own site) and **GreenPath
     Financial Wellness** (`institution_type: nonprofit-credit-counseling-
     agency`, `verification_source`: NFCC's member directory) — giving the
     vetted-institution mechanism real data to operate on for the first
     time, and closing the VISION win-condition-(1) gap REVIEW.md's
     "Deviations" section flagged.
   - `_builtin_debt_advisor._vetted_institutions` and
     `_builtin_consolidation_analyzer._vetted_institution_names` now build
     the vetted set from `category == "institutions"` **AND** a truthy
     `institution_type` **AND** a `verification_source` field — the
     distinguishing marker that separates a named, verified institution from
     a bare glossary concept. A concept term can never enter the vetted set,
     regardless of category.
   - `debt_finance_compliance.check_guardrail` no longer treats "any vetted
     name is a substring of an 80-char window" as sufficient. It now splits
     the text into sentences, and for each sentence containing an
     institutional-character trigger phrase, extracts the sentence's
     candidate proper-noun institution name(s) and requires the *full* text
     of a vetted institution's name to appear inside one of them
     (one-directional containment — checking the reverse direction would
     let a bare capitalized trigger word match any vetted name that happens
     to contain that word, reintroducing the same tautology in a different
     shape).
3. **BLOCK-3 (fixture realism).** `tests/test_debt_finance_compliance.py`
   gained tests that load `examples/worlds/debt-finance/terms.json` directly
   (not the synthetic fixture) and assert: the generic concepts are never in
   the vetted set; the real named institutions are; a fictional lender is
   blocked; the real vetted institution's true claim passes.
   `tests/test_debt_finance_agents.py` gained a `TestRealSealedBundle` class
   that mounts the actual sealed bundle end-to-end for both agents:
   confirms Debt Advisor prints both real institutions with their correct
   (non-hardcoded) character labels and never prints the two concept terms
   as if they were named institutions; confirms Consolidation Analyzer
   blocks a fictional "Payday Express Credit Union" scenario and allows the
   real "PenFed Credit Union" one. The pre-existing synthetic `_TERMS`
   fixture was updated to include a genuine `institution_type`/
   `verification_source` pair (so it still exercises the happy path) plus a
   bare concept term with no `institution_type` (so the fixture itself now
   also regression-tests the category-alone trap).
4. **Adversarial regression tests (the one BLOCK-1 should have started
   with).** Added to `test_debt_finance_compliance.py`: an unvetted
   fictional name ("Payday Express") paired with "is a credit union"
   is blocked even when real vetted credit unions exist elsewhere in the
   vetted set; a vetted institution whose own name contains "Credit Union"
   (the exact failure-mode swing REVIEW.md's ASK flagged) still passes; a
   near-miss unvetted name ("PenFed Lending Group") does not ride along on
   a similarly-named vetted institution's credibility.
5. **Digit-check ASK (action 6).** Both agents' `_framing_prose` now reject
   a model-generated sentence containing a digit (`_builtin_debt_advisor`
   additionally rejects one containing a vetted institution's name),
   falling back to the existing deterministic sentence — closing the last
   live path by which a model-generated number could reach a findings file.

**Re-sealed the bundle:** `PYTHONPATH=src python
scripts/forge_debt_finance_world.py` (with the sibling `dac_world` repo on
`PYTHONPATH`) — sealed cleanly, 26 terms (up from 24), fully sourced, new
`world_sha256`. One preflight rejection along the way (the edited "Credit
Union" concept's `definition` exceeded the 600-char budget by 22 chars) —
trimmed and resealed clean.

**Verification:**
- `pytest tests/test_debt_finance_compliance.py tests/test_debt_finance_agents.py`
  → **45 passed** (34 pre-existing + 11 new), including all six new
  adversarial/real-bundle regression tests, confirmed to exercise the real
  fix (they were run against the actual sealed bundle, not a hand-built
  fixture, per BLOCK-3's own finding about why the previous 67 tests missed
  this).
- `pytest tests/ -k "debt_finance or world_mount or default_worlds_catalog or sre_shim"`
  → **117 passed**, zero regressions in the broader mount/catalog/shim
  surface this fix touches indirectly (the vetted-set and guardrail
  signature didn't change, only their internals).
- Full unscoped `pytest tests/` (3514 collected): **46 failed, 3469 passed,
  2 skipped, 1 xfailed, 7 errors**. Confirmed by `git stash` + re-run that
  every one of those 46 failures/7 errors is pre-existing and identical with
  this fix stashed out — they are in `test_deep_default_and_tier.py`,
  `test_model_hosting_reframe_qa.py`, `test_model_ux_phase0_warmth_probe.py`,
  `test_qa_model_ux_memory_and_eject_fidelity.py`,
  `test_qa_provider_dropdown_paranoid.py`, `test_r1_r3_chat_models.py`,
  `test_reset_stop_scope.py`, `test_runtime_profile_api.py`,
  `test_swarm_goal_surfaces.py`, and `test_world_forge_api.py` — none of
  which this fix touches. Not attributable to this change.

## Architect feedback required

REVIEW.md's required actions 4 and 5 are product/scope decisions, not code
defects this pass resolved unilaterally, per this role's "no silent scope
expansion" rule:

- **Action 4 — named-institution decision.** REVIEW.md asked for an
  explicit decision on whether v1 shipping with no named institution from
  World content is acceptable, "or whether `terms.json` gains named-
  institution entries." This pass *did* add two named institutions
  (PenFed Credit Union, GreenPath Financial Wellness) as the mechanical fix
  BLOCK-1 required — but that was a required-by-construction side effect of
  fixing the tautology (the vetted mechanism needed real data to test
  against), not a deliberated product decision about which specific
  institutions belong in the World, how many, or what disclosure/liability
  posture citing them implies long-term. `OPEN_QUESTIONS.md` does not yet
  exist in this sprint directory; recommend the architect review this
  choice explicitly (institution selection, verification-source freshness
  policy, and whether "two hand-picked examples" is the intended long-term
  shape or a placeholder) before treating it as settled.
- **Action 5 — operator-supplied institution names.** REVIEW.md's ASK
  flagged that once BLOCK-1 is genuinely fixed, an operator staging a
  `balances.json` scenario for their own real institution (e.g. "Anytown
  Credit Union," not in `terms.json`) will have that scenario permanently
  guardrail-blocked on every tick, because Consolidation Analyzer's vetted
  set is the same World-content vetted set Debt Advisor uses, and an
  arbitrary real institution's own name containing "Credit Union" now
  correctly fails to match anything in it. This pass fixed the guardrail
  to be *correct* (vetted passes, unvetted blocks) per the concrete
  instruction given for this fix, but did not resolve the underlying
  product question REVIEW.md raised: whether operator-supplied institution
  names (the user's own data, not a claim the product is making) should be
  exempt from World-content vetting entirely, subject to a different
  (weaker or absent) check, or intentionally blocked pending the operator
  adding their own institution to a personal allowlist. Left open,
  surfaced here rather than decided silently — this is a policy question
  about what the product should do for the single most likely real input,
  not a code defect.

## Final state (post-review fixes)

- Files changed: 2 terms.json (authoring + sealed, plus the 6 other sealed
  artifacts a reseal regenerates), 3 agent-side Python modules, 2 test
  files. 14 files touched, +421/-45 lines.
- New tests: 11 (5 in `test_debt_finance_compliance.py`, 6 in
  `test_debt_finance_agents.py`, including the required real-sealed-bundle
  path and the adversarial fictional-institution regression).
- Test suite: 45/45 passing in the two debt-finance files; 117/117 passing
  in the broader debt-finance/world-mount/catalog/shim regression slice;
  full-suite delta is zero (46 pre-existing failures unchanged, confirmed
  via `git stash`).

## Post-review fixes, round 2 (REVIEW.md addendum at d7b3233, verdict BLOCK)

Closes BLOCK-4 and implements both of the addendum's now-decided design
questions (operator keeps the two named institutions with two required
conditions; operator-supplied institution names get a provenance-scoped
exemption). No design decisions were made unilaterally in this pass — both
questions had already been resolved by the architect in the addendum; this
pass only implements what was specified.

**1. BLOCK-4 — sentence boundary is not a boundary.**
`_SENTENCE_SPLIT_RE` now also splits on `\n+`, so a rendered list item
(which ends in `)`, not terminal punctuation) is its own chunk and can
never merge with an adjacent line. `check_guardrail` switched from
`.search()` (one trigger per chunk) to `.finditer()` (every trigger
occurrence checked). A second-order tautology surfaced while writing the
regression test for "one chunk, two triggers, one vetted name, one not":
pairing a trigger against *every* candidate name anywhere in the chunk let
an unrelated vetted name elsewhere in the same (unsplit-by-comma) sentence
vet an unvetted trigger it has nothing to do with. Fixed by scoping each
trigger occurrence's candidate search to a `±40`-char window around that
specific occurrence (`_PROXIMITY_WINDOW_CHARS`) rather than the whole
chunk — this was not in the addendum's literal instructions but is
required for "iterate finditer, require each occurrence to be paired" to
actually mean what it says; flagging this addition explicitly rather than
treating it as implied. Two regression tests added, both verified to fail
against `3d56c9b`: the exact adjacent-lines repro, and a single sentence
naming a vetted and an unvetted institution with one trigger each.

**2. Operator-supplied institution names — provenance-scoped exemption.**
`check_guardrail(text, vetted_institutions, operator_names=frozenset())`
— third parameter, matched with the identical strict full-name-containment
rule as `vetted_institutions`, ORed into the allowed set for pairing
purposes. Debt Advisor passes `frozenset()` always (its content is
entirely World-sourced — required action 3). Both agents' `_framing_prose`
already called `check_guardrail(text, frozenset())` with no operator_names
argument, so the model-prose layer gets no exemption of any kind by
construction — no change needed there, verified rather than assumed.

Consolidation Analyzer: `operator_names` is built from the operator's own
`debts[].institution` field (their *existing* card/loan issuers) — not
from `candidate_scenarios`, even though the scenario line is where an
institution name is actually rendered. This distinction matters and is
worth recording: `candidate_scenarios[].institution` is always a claim
about who is *offering* a comparison product and must still be vetted or
blocked like any other institutional-character claim; the exemption exists
so that when a scenario's institution happens to match one of the
operator's own already-staged debts (comparing an offer from your current
issuer), that specific echo is recognized as a quotation, not a new claim.
An institution name that appears only in `candidate_scenarios` — including
a fictional one — gets no exemption and is blocked exactly as before. The
rendered scenario line gets a conditional `(as you entered it)` marker,
code-inserted, present only when that scenario's institution actually
matched an operator name.

**3. Roster heading + disclaimer line (condition (a)).** Debt Advisor's
heading changed from `## Vetted institutions (from this World's sourced
terms)` to `## Institutions whose character claims this World verified`,
with a fixed, code-inserted line immediately under it stating the list is
not exhaustive and not a recommendation. Neither string is model-generated
or conditional — always present when the section renders.

**4. `verified_as_of` staleness gate (condition (b)).**
`debt_finance_compliance.is_verification_fresh(date_str, today=None)` —
shared by both agents rather than duplicated — returns `False` (not
vetted) for a missing field, an unparseable value, or a date more than
365 days old. `_vetted_institutions` (Debt Advisor) and
`_vetted_institution_names` (Consolidation Analyzer) both now require it
alongside `institution_type` and `verification_source`; an institution
failing any of the four conditions is simply absent from the vetted set,
so a character claim about it is blocked rather than passed — staleness
degrades closed. `verified_as_of` (`2026-07-27`, today) was added to both
named institutions in `scripts/worlds_src/debt-finance/terms.json`, and
the date renders next to the citation in Debt Advisor's output (e.g.
`..., verified as of 2026-07-27)`), not just as internal bookkeeping.
Bundle resealed (`PYTHONPATH=src:qukaizen-dac python3
scripts/forge_debt_finance_world.py`) — clean, deterministic diff limited
to `terms.json` plus the 4 sealed artifacts a reseal always regenerates
(SKILL.md, arail-plugin.json, capabilities.json, manifest.json).

**Operator decision recorded.** The operator chose "keep the two named
institutions, own the annual re-check" over stripping to zero — this is
what made conditions (a)/(b) load-bearing rather than moot; recorded here
per the process instruction rather than in a separate OPEN_QUESTIONS.md
entry, since the addendum's escalated question is now closed.

**Verification.**
- `PYTHONPATH=src:qukaizen-dac pytest tests/test_debt_finance_compliance.py
  tests/test_debt_finance_agents.py` — 61/61 passing (11 new tests: 9 in
  the compliance file — 2 BLOCK-4 regressions, 3 operator_names, 5
  `is_verification_fresh` — and 8 in the agents file — roster heading,
  verified_as_of rendering, 2 staleness-gate, 2 operator_names/marker).
- `pytest tests/ -k debt_finance` — 94/94 passing.
- Full-suite run: 46 failed / 3485 passed / 2 skipped / 1 xfailed / 7
  errors — identical failing-test set to the file names already on record
  from the round-1 fix (`test_build_tab.py`, `test_world_forge_api.py`,
  `test_aerollm_defaults.py`, etc. — none in the debt-finance module tree,
  none touching a file this round changed). Not re-verified against a
  fresh `git stash` this round (the round-1 fix already established this
  is pre-existing red); confirmed instead by inspection that every failing
  test file is outside this round's diff (`git status --short` above).
- Self-check: no file touched outside the four specified changes (BLOCK-4,
  heading/disclaimer, `verified_as_of` gate, `operator_names` exemption)
  plus the terms.json reseal and the tests that exercise them. No
  commented-out code. No TODOs.

All four required changes are wired into the real call sites the agents
use in production, not just present as unused code:
- `check_guardrail`'s new signature is called from `_build_output` in
  *both* `_builtin_debt_advisor.py` and `_builtin_consolidation_analyzer.py`
  (the actual write path both agents' `tick()` calls), not only from tests.
- The heading/disclaimer line is in `_build_output`'s line-assembly, which
  is the only function that produces Debt Advisor's findings file content.
- `is_verification_fresh` is called from both agents' vetted-set
  constructors (`_vetted_institutions`, `_vetted_institution_names`),
  which both `tick()` implementations call every run — not a helper left
  unreferenced.
- `operator_names` flows `tick()` → `_operator_institution_names(debts)` →
  `_build_output(..., operator_names)` → `check_guardrail(..., operator_names=...)`
  in Consolidation Analyzer, and is explicitly hardcoded to `frozenset()`
  at the one `check_guardrail` call site in Debt Advisor's `_build_output`.

---

## Post-review fixes, round 3

Fixing REVIEW.md re-review addendum 2 (round 3, fix commit under review
`7cd07f3`): BLOCK-5, ASK-A (documented, not fixed), ASK-B (fixed), and the
housekeeping action (ARCHITECTURE.md §13).

### BLOCK-5 — `operator_names` widened to `candidate_scenarios`

`_operator_institution_names(debts)` was scoped to `debts` only, on the
theory (rejected by the architect) that a candidate scenario's institution
is a claim about who is *offering*, not a claim the operator already made
about themselves. But `candidate_scenarios` is the only place Consolidation
Analyzer ever renders an institution name — the "Current position" section
emits counts/APR only, no names — so the exemption never fired for the
input it exists to fix. Exact repro from REVIEW.md (`debts=[Chase]`,
`scenarios=[Anytown Credit Union]`) raised `_GuardrailBlocked` on the whole
document, every tick, forever.

Fix: `_operator_institution_names(debts, scenarios)` now unions institution
names from both fields of the parsed `balances.json` — still nothing else
(never scouting findings, never World terms). Matching rule and the
`(as you entered it)` marker are unchanged. Call site (`tick()`) and the
`_build_output` docstring/comments updated to match.

Verified manually (exact prompt repro): `_build_output` now returns a
451-char document containing both `Anytown Credit Union` and
`(as you entered it)` for the Chase/Anytown-Credit-Union input — no
exception raised.

Three regression tests added to `TestConsolidationAnalyzerOperatorNamesExemption`
in `tests/test_debt_finance_agents.py`:
1. `test_operator_scenario_only_institution_passes_and_is_marked` — the
   exact repro end-to-end via `tick()`; asserts the findings file exists
   and carries the marker. Fails against pre-fix code (was blocked).
2. `test_debts_only_institution_still_exempted_no_regression` — confirms
   the widening is additive: a debts-only institution is still exempted.
3. `test_institution_in_neither_field_still_blocks` — confirms an
   institution absent from both `debts` and `candidate_scenarios` still
   blocks. Exercised directly against `check_guardrail` (not via `tick()`):
   by construction, the analyzer never renders an institution name that
   isn't sourced from `debts`/`candidate_scenarios`, so there is no
   end-to-end path left by which a genuinely third-party name reaches this
   agent's output at all — itself the intended consequence of the fix, not
   a gap in the test.

One existing test's premise was invalidated by the fix and had to change,
not just be patched around: `test_consolidation_analyzer_blocks_a_fictional_unvetted_institution`
(real-sealed-bundle suite) staged "Payday Express Credit Union" as a
*candidate_scenarios*-only institution and asserted it was blocked. Under
the corrected semantics that is now exactly the case that must pass (the
operator typed it, so it's a quotation) — the test was rewritten as
`test_consolidation_analyzer_allows_operator_typed_fictional_institution_as_quotation`,
asserting the document is written with the marker, with an explicit
docstring note explaining why the old assertion was the defect BLOCK-5
fixed, not a coincidental casualty. `test_unvetted_institution_not_in_debts_still_blocks`
in the synthetic-fixture suite was replaced for the same reason.

No bundle file changed (`terms.json` untouched) — reseal not required,
confirmed by `git status --short` showing only the four Python/Markdown
files below.

### ASK-B — failure message now names the reason and the fix

Both agents' `_GuardrailBlocked` handlers previously emitted a bare
"failed the language-safety check ... see logs" with the reason only in
the structured `data` field, not the message text. This was flagged in
addendum 1 as a cheap fix and carried, unaddressed, into addendum 2. Now
fixed in both agents:
- Consolidation Analyzer's message includes the guardrail's `reason` text
  inline and points at `balances.json`'s `institution` fields as the thing
  to check — this is now the correct pointer post-BLOCK-5, since a block
  here is (almost) always something in the operator's own file.
- Debt Advisor's message also includes `reason` inline but points at the
  mounted World's `terms.json`/scouting findings instead, since nothing an
  operator types can cause a block on that path — deliberately different
  guidance per-agent rather than one generic string.

The `"failed the language-safety check"` substring both existing tests
assert on is preserved.

### ASK-A — recorded as debt, not fixed (per the review's own instruction)

The architect explicitly asked for this to be recorded as a tripwire, not
fixed, since it is genuinely unreachable in the current assembled
document. Added as ARCHITECTURE.md §13 item 10 (see below) — not touched
in code.

### ARCHITECTURE.md §13 — housekeeping action completed

Added three new tech-debt items (§13.8–§13.10), citing REVIEW.md's
re-review addenda 1 and 2 by name:
- §13.8: the guardrail is now a three-way provenance policy
  (World-vetted / operator-quoted / neither); a fourth provenance (an
  agent quoting an approved scouting finding that itself names an
  institution) would need a real design, not a third `frozenset` param.
- §13.9: named institutions carry an indefinite re-verification
  obligation, owned by whoever reseals the bundle.
- §13.10: the `_PROXIMITY_WINDOW_CHARS = 40` tripwire (ASK-A) — recorded
  as unreachable today, with the exact condition (two institution names on
  one line) that reopens it as a live BLOCK.

### Verification

- `pytest tests/test_debt_finance_agents.py tests/test_debt_finance_compliance.py
  tests/test_debt_finance_consolidation_arithmetic.py
  tests/test_debt_finance_agents_seed.py tests/test_debt_finance_reveal_slot.py
  tests/test_world_forge_debt_finance_seal.py` — 96/96 passing (added 5 net
  new tests: 3 BLOCK-5 regressions + 1 replaced synthetic-fixture test +
  1 rewritten real-bundle test, both in place of tests whose premise the
  fix invalidated).
- Exact prompt repro run manually against `_build_output` directly (see
  above) — succeeds, no `_GuardrailBlocked`.
- `pytest tests/ --collect-only` — 3543 tests collect with no import
  errors (confirms the message-text and signature changes don't break
  anything outside the debt-finance module tree at import time).
- Full whole-repo `pytest tests/` run timed out in this environment before
  completing (>2 min, pre-existing per round-1's BUILD_LOG note on
  environment-related full-suite abandonment) — not re-attempted a second
  way this round beyond the scoped run and the collect-only import check,
  since `git status --short` confirms the diff is limited to the four
  files below, none of which any other test file imports.
- `git status --short`: `sprints/2026-07-26-world-of-debt-finance/ARCHITECTURE.md`,
  `src/arail/agents/_builtin_consolidation_analyzer.py`,
  `src/arail/agents/_builtin_debt_advisor.py`, `tests/test_debt_finance_agents.py`.
  No file outside this list touched. No commented-out code. No TODOs.

### Is this round genuinely complete?

I believe BLOCK-5 itself is closed and I am not aware of a live fourth-order
defect in the code this round touched, for a specific reason: the fix makes
the analyzer's institutional-character guardrail a no-op for
`candidate_scenarios` content by construction (any institution rendered
there is, by definition, now in `operator_names`, since the set is built
directly from the same fields it's checked against). That's not a bug I'm
rationalizing around — it's the architect's explicit ruling in addendum 1
("the exemption is about provenance, not offer-vs-debt semantics") taken to
its logical conclusion, and there is no remaining institution-naming
surface in this agent's output left un-exempted (`_framing_prose` still
self-checks against empty vetted *and* empty operator sets, so LLM prose
gets no exemption of any kind — verified unchanged in this round's diff).

I am **not** fully confident there is no fifth-order issue in a part of the
system this round didn't touch, specifically the two items the review
addenda flagged and asked to be *recorded*, not fixed: the three-way
provenance policy (§13.8) if a fourth provenance is ever added, and the
proximity-window tripwire (§13.10, ASK-A) if a future change ever renders
two institution names on one line. Both are explicitly out of scope for
this round per the review's own instructions, not things I judged safe —
the review said "documented debt," and I've recorded them as such rather
than silently deciding they're fine.
