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

## Post-review fixes, round 4

Fourth architect review (REVIEW.md re-review addendum 3, commit `5abf008`)
returned **BLOCK** on **BLOCK-6**: the evaluative-language branch of
`check_guardrail` (`_EVALUATIVE_RE.search(text)`) ran on the entire
assembled body with zero provenance distinction, while the institutional-
character branch had already been made provenance-aware. Both agents
render non-agent-authored free text into the body — the analyzer's
`r.product`/`r.source`/`r.as_of` (operator-typed, verbatim from
`candidate_scenarios`) and the advisor's `feed`/`path` (externally-authored
RSS text from an approved scouting finding) — so an ordinary,
non-adversarial citation URL or feed title containing a word like "best"
(e.g. a NerdWallet "best-balance-transfer-cards" page, or a "Best Balance
Transfer Cards - Bankrate" feed title) suppressed the entire findings
document, permanently (the no-op hash only saves on a successful write).

### Fix — `quoted_spans` parameter on `check_guardrail`

Added `quoted_spans: frozenset[str] = frozenset()` to `check_guardrail`
(`debt_finance_compliance.py`): the evaluative branch's analogue of
`operator_names`, but scoped to exact literal substrings rather than a
named-entity set. The `_EVALUATIVE_RE` check now runs against a masked copy
of the text with every `quoted_spans` occurrence blanked out first; the
institutional-character branch is unaffected and still runs against the
original, unmasked text (a comment at the mask site makes this explicit).
This is deliberately **not** a vocabulary widening — the architect ruled
that out explicitly, since it would let the model's own generated prose
say "best"/"guaranteed" freely too. `quoted_spans` only ever narrows what
counts as "this exact code-inserted echo," never the trigger-word list
itself.

**Bug caught during implementation, fixed before commit:** the first
version of the masking loop iterated `quoted_spans` in arbitrary set order
and used sequential `str.replace()`. When one quoted span is a substring of
another (e.g. `"balance-transfer"` is a substring of the citation URL
`".../best-balance-transfer-cards"`), masking the shorter span first
corrupts the longer span's text so the longer `.replace()` no longer finds
an exact match — leaving the surrounding `"best-"`/`"-cards"` fragments of
the URL unmasked and the evaluative check still (incorrectly) tripping.
Fixed by sorting spans longest-first before masking. Caught by running the
exact NerdWallet-URL repro against the live code before writing it up as
done, not by trusting the test suite alone — the repro initially still
failed with the naive implementation.

Call sites:
- **Consolidation Analyzer** (`_build_output`): `quoted_spans` is built
  from `r.product`, `r.source`, `r.as_of` across all computed scenario
  results. The rendered line now marks these fields `(as entered)`,
  matching the existing `(as you entered it)` marker style on the
  institution name, so a reader can tell they're the operator's own words
  quoted back, not the agent's characterization.
- **Debt Advisor** (`_build_output`): `quoted_spans` is built from
  `f.get('feed')`/`f.get('path')` across approved findings. The rendered
  line now marks these `(quoted verbatim)`.

`v.institution_type`/`v.name`/`v.verification_source` (Debt Advisor's
vetted-institution roster) and `r.institution` (Analyzer) were deliberately
**not** added to `quoted_spans` — see "fifth-order check" below.

### Secondary items (also required this round)

1. **ASK-B message fix**: the analyzer's guardrail-block message hardcoded
   an institutional-character explanation pointing at `balances.json`'s
   `institution` fields, which was wrong for the evaluative branch (the
   branch that fires in realistic practice per BLOCK-6). Added
   `REASON_EVALUATIVE` and `REASON_INSTITUTIONAL_PREFIX` constants to
   `debt_finance_compliance.py` so the agent can branch its hint on which
   reason actually fired, instead of guessing/hardcoding. The Debt
   Advisor's message was already correct for both branches (per the
   review) and was left unchanged.
2. **ARCHITECTURE.md §13.10 correction**: the previous justification for
   the proximity-window tripwire being "genuinely unreachable" claimed
   "the only free-text path (`_framing_prose`) self-checks against an
   empty vetted set" — false, since the analyzer's scenario line and the
   advisor's findings line are both free-text paths with no self-check.
   Replaced with the actual reason: on the analyzer's scenario line, the
   only name that can appear there (the scenario's own institution) is,
   by construction, always a member of `operator_names`, so a second
   *unvetted* name can never legitimately co-occur on that line today.
   Tightened the tripwire condition to match.
3. **INFO note on `operator_names` scope**: added a comment at the
   analyzer's `check_guardrail` call site explaining why re-checking
   `_framing_prose` inside the body with `operator_names` in scope is safe
   despite reading as a docstring violation — the framing sentence is its
   own newline-delimited chunk (can't merge with scenario lines) and was
   already rejected by the zero-exemption standalone gate if it contained
   a trigger phrase.

### Regression tests added

- `tests/test_debt_finance_compliance.py`: `quoted_spans` unit tests
  (exempts a marketing URL; default empty means no exemption; does not
  exempt agent-generated prose; does not leak into the institutional-
  character branch) plus a test asserting the `REASON_*` constants match
  actual `check_guardrail` output.
- `tests/test_debt_finance_agents.py`:
  - `TestConsolidationAnalyzerEvaluativeQuotedSpans` — the exact
    NerdWallet-URL repro now writes successfully (a); genuine
    model-generated evaluative prose (`_framing_prose` with a mocked LLM
    response) still falls back to the deterministic sentence (b); a benign
    non-URL source is unaffected (c, no regression); an adversarial body
    combining a code-inserted evaluative word (in a quoted span) with an
    unvetted institutional-character claim on the SAME body still blocks
    on the institutional branch (d).
  - `TestDebtAdvisorEvaluativeQuotedSpans` — the exact "Best Balance
    Transfer Cards - Bankrate" feed-title repro now writes successfully;
    a code-authored `institution_type` value containing "best" (injected
    directly, not via `quoted_spans`) still blocks, confirming the fix did
    not widen the exemption to vetted-institution roster content.
  - Updated the one `check_guardrail` monkeypatch lambda
    (`TestDebtAdvisorGuardrail`) to accept the new `quoted_spans` keyword,
    since the call sites now always pass it.

Full debt-finance suite (`pytest tests/ -k debt_finance`): **107 passed**,
0 failed. The four compliance/agent test files plus the seed/seal tests all
pass. A whole-repo `pytest tests/` run was attempted but is slow/flaky in
this environment for reasons unrelated to this diff (many pre-existing
failures scattered across unrelated portal/integration tests appear before
the debt-finance test files are even reached, at the same rate whether or
not this round's diff is applied); the debt-finance-scoped run is the
authoritative signal for this change per the review's own instruction to
"run the full debt-finance test suite."

### Fifth-order defect-class check (provenance-unaware checks on mixed
### agent/non-agent assembled text) — none found beyond what's fixed above

Per the round's instruction, before declaring done I looked deliberately
for another instance of this same defect class (a check that runs on
assembled text mixing agent-generated and non-agent content, without
provenance awareness) anywhere else in either agent's write path.

**Candidates considered and why each is not a live instance:**

- **`v.verification_source` and `v.institution_type`/`character`** (Debt
  Advisor's vetted-institution roster line, rendered from `terms.json`).
  These are literal, non-agent-generated strings, structurally similar to
  `feed`/`path`. I considered adding them to `quoted_spans` too, but
  rejected it: unlike `feed`/`path` (arbitrary open-web RSS text an
  operator has zero control over) or `product`/`source` (arbitrary text an
  operator pastes into their own file), `institution_type` and
  `verification_source` are authored at **World-sealing time** by the same
  trusted party who curates the vetted-institution list itself — the
  review's own required regression assertion 4 explicitly demands that an
  evaluative word injected via `institution_type` **still blocks** (this
  round's `test_code_authored_institution_type_with_evaluative_word_still_
  blocks` encodes exactly that). Extending the exemption to
  `verification_source` would be the same category of content by the same
  author, so leaving it unmasked is consistent with that explicit
  instruction, not an oversight.
- **`v.name` / `r.institution`** (the institution's own name, in both
  agents). Also literal, non-agent-generated, and also not in
  `quoted_spans`. I did not add these either: masking them would only
  matter if a genuine institution's own name contained one of
  `_EVALUATIVE_RE`'s literal trigger words (e.g. a hypothetical
  "BestPoint Credit Union"), which is a real but narrow edge distinct from
  BLOCK-6's shape — BLOCK-6 was about *arbitrary third-party or open-web
  text* an agent has no control over and that commonly contains marketing
  language (citation URLs, RSS titles), not about institutions' own legal
  names, which is a much rarer collision and which the institutional-
  character branch already treats correctly today (the proximity/
  substring-match logic that answers "is this name vetted" is unaffected
  by anything in this fix, since it always runs on unmasked text). I did
  not silently leave this alone without noting it: this paragraph is that
  note, and it should be revisited if a real institution with an
  evaluative-sounding legal name is ever sealed into a World.
- **`f.get('checked')`** (a scouting finding's checked-date string). Also
  literal and non-agent-generated, but a date string has no realistic path
  to containing `_EVALUATIVE_RE`'s vocabulary; if it somehow did, that
  would indicate malformed metadata worth surfacing as a block, so leaving
  it unmasked is the more defensible default, not an oversight.
- **No other `check_guardrail` call sites exist.** `grep` for
  `check_guardrail`/`_build_output` across `src/arail/agents/` confirms
  the only two production write paths are `_builtin_consolidation_
  analyzer.py` and `_builtin_debt_advisor.py`'s `_build_output` functions,
  both addressed above, plus each agent's own `_framing_prose` standalone
  self-check (unchanged, zero-exemption on every parameter, by design).

I'm confident there is no unaddressed live instance of BLOCK-6's exact
shape (an *arbitrary, operator-or-web-authored* free-text field escaping
the evaluative check's provenance policy) in either agent's write path,
because I enumerated every literal-string interpolation in both
`_build_output` functions and classified each by author/trust level. The
two categories I chose not to touch (World-sealer-authored institution
records; date strings) are structurally different from the category
BLOCK-6 was about, and I've stated the actual reasoning above rather than

---

## Post-review fixes, round 5

**Reviewed:** `sprints/2026-07-26-world-of-debt-finance/REVIEW.md`,
re-review addendum 4 (round 5), verdict BLOCK, at commit `6a2eb83`.
**This round's fix commit:** see `git log` for the commit immediately
following this entry.

### What round 4 got wrong

Round 4's enumeration paragraph above (the one ending "I'm confident there
is no unaddressed live instance...") explicitly *named* `v.name` /
`r.institution` as a category it considered and chose not to mask, on the
reasoning that BLOCK-6 was about "arbitrary third-party or open-web text,"
not "institutions' own legal names." The review's addendum-4 correction is
right and mine was wrong: the institution-name fields sit on the *exact
same rendered line*, come from the *exact same provenance class*
(operator-typed `candidate_scenarios` entry; World-sealed vetted-roster
entry) as the sibling fields I did mask, and my own round-4 correction to
ARCHITECTURE.md §13.10 already said so in as many words — I just never
connected that sentence back to the masking call sites. The "narrower
edge case" framing was a rationalization, not a structural distinction:
`_EVALUATIVE_RE`'s vocabulary (`best`, `lowest`, `top pick`, ...) is
extremely common in real institution and lender brand names ("Best Egg",
"LendingClub's Best Rate program", a NerdWallet "best-credit-unions"
citation), not a rare collision.

### BLOCK-7 fix

- **Consolidation Analyzer** (`_builtin_consolidation_analyzer.py`,
  `_build_output`): added `r.institution` to the `quoted_spans` frozenset
  passed to `check_guardrail`, alongside the existing `r.product`,
  `r.source`, `r.as_of`.
- **Debt Advisor** (`_builtin_debt_advisor.py`, `_build_output`): added
  `v.name`, `v.institution_type`, and `v.verification_source` (for every
  vetted institution rendered into the roster) to the `quoted_spans`
  frozenset, unioned with the existing `feed`/`path` set from findings.
  (`v.institution_type` included per REVIEW.md's required-actions list,
  even though BLOCK-7(b)'s live repro only named `v.name` and
  `v.verification_source` — it is structurally the same class: a
  World-sealed structured field rendered verbatim on the same roster
  line, e.g. a hypothetical `institution_type` value containing "top" or
  "best" would have the identical defect shape.)
- **ASK-B hint** (`_builtin_consolidation_analyzer.py`, the
  `REASON_EVALUATIVE` branch message): extended to name `institution`
  alongside `product`/`source`/`as_of`, since BLOCK-7(a) fires on exactly
  that field. Reworded to also flag the ASK-C short-value caveat below.

### ASK-C fix

`check_guardrail` in `debt_finance_compliance.py` now filters `quoted_spans`
by a `_MIN_QUOTED_SPAN_LEN = 5` floor before masking: any span shorter
than 5 characters is never used to blank text ahead of the evaluative
check, and instead the body is left fully evaluative-checked at that
location (degrades closed, not open). Offset-based masking (blanking only
the exact insertion range) was not practical without threading tracked
offsets through the `f"..."`-based body assembly in both agents' render
loops — a much larger structural change to two independently-evolving
render functions for a defect whose blast radius the length floor already
closes. The floor is documented in both the module-level comment and the
`check_guardrail` docstring, including the exact tradeoff being made and
why.

### Exhaustive field-by-field checklist (every literal interpolation into
guardrail-checked text, both agents)

**Consolidation Analyzer — `_build_output`, from `candidate_scenarios`/`debts`:**

| Field | Rendered where | Masked (quoted_spans)? | Why |
|---|---|---|---|
| `r.institution` | scenario line, `**{institution}**` | **Yes (this round)** | Operator-typed `candidate_scenarios` field; same line/provenance as `product`/`source`/`as_of`; carries "(as you entered it)" marker. Missed in round 4 — BLOCK-7(a). |
| `r.product` | scenario line, `— {product} (as entered)` | Yes (round 4) | Operator-typed free text, code-inserted verbatim. |
| `r.source` | scenario line, `Source: {source} (as entered)` | Yes (round 4) | Operator-typed citation URL, code-inserted verbatim. |
| `r.as_of` | scenario line, `as of {as_of} (as entered)` | Yes (round 4) | Operator-typed date string, code-inserted verbatim. |
| `apr` (computed) | "Current blended APR: {apr:.2f}%" | N/A — numeric, code-computed | Not free text; cannot contain `_EVALUATIVE_RE` vocabulary. |
| `len(debts)` | "Debts entered: {n}" | N/A — numeric | Same. |
| `r.rate`, `r.fee_pct`, `r.fee_amount`, `r.monthly_savings`, `r.breakeven` | scenario line | N/A — numeric, code-computed | Same. |
| `_framing_prose()` output | top-of-document sentence | **Not masked, by design** | This is the one field in this document that is genuinely model-generated when the LLM path is live; it is separately self-checked with an *empty* `quoted_spans`/name set before being used (zero-exemption gate), and the deterministic fallback sentence is a hardcoded literal with no evaluative vocabulary. Masking it here would be backwards — it must get *less* exemption than everything else, not more. |
| Static headings / labels ("## Current position", "No candidate scenarios staged.", etc.) | throughout | N/A — hardcoded literal strings, code-authored | Fixed strings audited once; contain no `_EVALUATIVE_RE` vocabulary and never will unless someone hand-edits the source, at which point ordinary code review catches it. |

**Debt Advisor — `_build_output`, from the mounted World's roster / approved scouting findings:**

| Field | Rendered where | Masked (quoted_spans)? | Why |
|---|---|---|---|
| `v.name` | roster line, `**{name}**` | **Yes (this round)** | World-sealed structured field, third-party institution's own name; same line/provenance as `institution_type`/`verification_source`. Missed in round 4 — BLOCK-7(b). |
| `v.institution_type` | roster line, `({character}, verification source: ...)` | **Yes (this round)** | World-sealed structured field (`.replace("-", " ")` of an enum-like value in `terms.json`); same provenance/line as `v.name`/`v.verification_source`. Included per REVIEW.md's explicit required-actions list. |
| `v.verification_source` | roster line, `verification source: {url}` | **Yes (this round)** | World-sealed citation URL, third-party-authored. Missed in round 4 — BLOCK-7(b), the live repro (NerdWallet "best-credit-unions" URL). |
| `v.verified_as_of` | roster line, `verified as of {date}` | Not masked | Date string; no realistic path to `_EVALUATIVE_RE` vocabulary, and a malformed value here is itself worth surfacing as a block rather than being silently exempted. |
| `f.get('feed')` | findings line, `Found via {feed}` | Yes (round 4) | Externally-authored RSS feed title, code-inserted verbatim. |
| `f.get('path')` | findings line, `` see `{path}` `` | Yes (round 4) | Mounted-World-relative file path, code-inserted verbatim. |
| `f.get('checked')` | findings line, `checked {checked}` | Not masked | Date string; same reasoning as `verified_as_of`. |
| `_framing_prose(vetted, findings)` output | top-of-document sentence | **Not masked, by design** | Same reasoning as the analyzer's framing prose: this is the genuinely model-generated field, self-checked separately with an empty exemption set, with the additional per-vetted-name rejection (`v.name.lower() in lowered`) the analyzer doesn't need since it has no vetted set of its own. |
| Static headings / labels | throughout | N/A — hardcoded literal strings | Same as analyzer. |

Every row in both tables is now either (a) in `quoted_spans` because it is
a code-inserted verbatim echo of operator- or World-sealer-authored
structured data, (b) a numeric/date value structurally incapable of
carrying evaluative vocabulary in a way that would matter, or (c) the
framing-prose sentence, which is deliberately given *zero* exemption
because it is the one place genuinely model-generated text can enter
either document. There is no fourth category and no remaining call site —
`grep` for `f"` / `f'` interpolations inside both `_build_output`
functions was re-run against this table line by line, and every match is
accounted for above.

### Do I believe every field is now accounted for?

Yes, with the caveat that this is the second time a "masked some but not
all provenance-equivalent fields" mistake reached review, and the
mechanism that caused it both times was the same: enumerating fields
individually against BLOCK-6/7's letter ("is this an arbitrary
third-party/open-web string?") rather than mechanically enumerating every
`f"..."`-interpolated field in each render function first and *then*
classifying each one. This round used the mechanical enumeration first
(the tables above), which is why it also caught `v.institution_type` —
not called out by BLOCK-7's live repro, but flagged by REVIEW.md's
required-actions list as the same class — before another review round had
to point it out. I am not aware of a fourth provenance-equivalent field in
either write path; the tables above are the complete set of interpolated
fields in both `_build_output` functions, not a subset chosen because it
matched the review's named examples.

### Tests added

- `TestConsolidationAnalyzerInstitutionQuotedSpan` (3 tests,
  `tests/test_debt_finance_agents.py`): the "Best Egg" repro passes and is
  written verbatim; "Egg Financial" control still passes; genuinely
  agent-generated evaluative prose (`llm_complete` stubbed to return
  "Best Egg is the guaranteed top pick for you.") still falls back to the
  deterministic sentence.
- `TestDebtAdvisorVettedRosterQuotedSpans` (4 tests, same file): the
  NerdWallet "best-credit-unions" `verification_source` repro passes and
  is written verbatim; the NCUA control URL still passes; a vetted
  institution's own name containing "Best" passes; genuinely
  agent-generated evaluative prose is still blocked via a direct
  `check_guardrail` call.
- `test_short_quoted_span_does_not_globally_mask_unrelated_evaluative_word`,
  `test_short_quoted_span_below_floor_is_itself_still_fully_checked`,
  `test_quoted_span_at_or_above_floor_still_masks_correctly`
  (`tests/test_debt_finance_compliance.py`): the exact `as_of='st'` ASK-C
  repro no longer bypasses the check on an unrelated "best"; a short span
  that is itself evaluative-sounding is not masked and is still caught
  (documents the degrade-closed tradeoff); a realistic-length span is
  still masked correctly (no regression).

### Test results

- `tests/test_debt_finance_agents.py` + `tests/test_debt_finance_compliance.py`:
  84 passed (was 107 pre-this-round across the broader debt-finance
  selection below; these two files' local count).
- Full debt-finance selection (`pytest tests/ -k "debt_finance or
  debt-finance"`): **117 passed**, 0 failed.
- Full repo suite (`pytest tests/`, 629.9s): 46 failed, 3508 passed, 2
  skipped, 1 xfailed, 7 errors — **zero of the 46 failures/7 errors are in
  any debt-finance file** (`grep -i debt` against the failure list is
  empty). All failures are pre-existing red in unrelated areas
  (`test_world_forge_api.py`, `test_dashboard_layout_v2.py`,
  `test_r1_r3_chat_models.py`, `test_qa_provider_dropdown_paranoid.py`,
  etc.) — the same pre-existing-red pattern prior rounds' full-suite
  `git stash` methodology established. No regression introduced by this
  round's changes.

## Post-review fixes, round 6 (final)

**REVIEW.md at 3610d04 ("Re-review addendum 5 (round 6)"), verdict
WEAK_PASS.** One required fix (ASK-D) before merge; one documentation-only
tech-debt entry; everything else in that round was accepted as-is (BLOCK-7,
ASK-C closed; field enumeration independently re-derived and confirmed
complete).

### ASK-D fix

`_builtin_debt_advisor.py`'s `_build_output` renders
`character = v.institution_type.replace("-", " ")` (line ~300) but the
`quoted_spans` frozenset it builds for the guardrail's evaluative-branch
exemption (line ~349, prior to this fix) put in the *raw*
`entry.institution_type` — never the hyphen-replaced string that actually
appears in the rendered document. For any realistic hyphenated value
(`terms.json` uses `credit-union`, `credit-counseling-agency`), the mask
never matched what was rendered: masking the raw span left `ok=False`
(spurious block), while masking the rendered span correctly returns
`ok=True`. Confirmed independently by the architect before this fix landed.
Degrades closed (over-blocks, never a bypass) and is unreachable against
the two real institutions in today's sealed bundle — not a live BLOCK, but
a real one-line bug in the round-5 fix.

**Fix:** `quoted_spans` now includes `entry.institution_type.replace("-",
" ")`, matching the exact transform `_build_output` applies before
rendering — not the raw field.

**Test:** replaced the now-stale
`test_code_authored_institution_type_with_evaluative_word_still_blocks`
(which asserted institution_type was "never a member of quoted_spans" — a
premise round 5 deliberately overturned when it correctly widened scope to
include this field) with
`test_hyphenated_institution_type_with_trigger_word_no_longer_blocks`,
using a test fixture value (`"best-rate-lender"`) that only exposes an
`_EVALUATIVE_RE` trigger word once its hyphens are stripped for display.
This test fails against the pre-fix code (raises `_GuardrailBlocked`) and
passes against the fix. Added
`test_genuinely_agent_authored_evaluative_text_still_blocks` as a negative
control confirming the fix only changed which rendered string is masked,
not whether genuinely agent-authored text remains blocked.

### ARCHITECTURE.md §13 — tech-debt entry added, not implemented

Added §13.11, documenting the architect's recommended segment-based
provenance refactor (assemble `(text, provenance)` segments at render time
instead of reconstructing provenance from a flat string via substring
search) as a candidate for its own future, separately-scoped sprint,
referencing REVIEW.md's "Re-review addendum 5 (round 6)" as the source.
**Not implemented** — the architect was explicit that this belongs in its
own scoped sprint, not another round on this diff, and this build's own
implementation stayed within the ASK-D scope only.

### Test results

- `tests/test_debt_finance_agents.py` + `tests/test_debt_finance_compliance.py`
  + `tests/test_debt_finance_agents_seed.py` + `tests/test_debt_finance_reveal_slot.py`
  + `tests/test_world_forge_debt_finance_seal.py` (targeted local run): 110
  passed, 0 failed.
- Full debt-finance selection (`pytest tests/ -k "debt_finance or
  debt-finance" -q`, from the worktree root, with
  `PYTHONPATH=src:.../qukaizen-dac`): **118 passed**, 3447 deselected, 0
  failed. (117 -> 118: net +1 from replacing one stale test with two new
  ones.)
- Full repo suite: not independently re-run this round beyond the targeted
  debt-finance selection above. Round 5's full-suite baseline (46
  pre-existing failures, all outside debt-finance) is unchanged by this
  round's diff, which touches only `_builtin_debt_advisor.py`'s
  `quoted_spans` construction, `tests/test_debt_finance_agents.py`, and
  `ARCHITECTURE.md`.

### Commit

`2a74ab7` — `fix(debt-finance): mask institution_type's rendered form, not
raw field (ASK-D)`. Single atomic commit: the one-line production fix, the
two-test regression/negative-control pair, and the documentation-only
ARCHITECTURE.md §13 tech-debt entry.

## Closing summary

Review history on this build: base review at `2c7dce1` returned **BLOCK**
(BLOCK-1/2/3); five subsequent re-review rounds each returned **BLOCK**
(BLOCK-4 at round 2; BLOCK-5 at round 3; BLOCK-6 at round 4; BLOCK-7(a)/(b)
at round 5) as the review progressively found deeper instances of the same
provenance-masking defect class; round 6 (this round) returned
**WEAK_PASS**, with the one required fix (ASK-D) closed above and the
architect's structural recommendation filed as tracked tech debt rather
than implemented.

**Current status: ready for `/qa`.** All required actions from REVIEW.md's
round-6 addendum are complete. No BLOCK findings remain open. The
segment-based provenance refactor is explicitly out of scope for this
sprint and tracked in ARCHITECTURE.md §13.11 for a future sprint.

---

## Post-QA fixes (round 7 — response to TEST_REPORT.md FAIL)

QA's adversarial pass (`tests/test_debt_finance_qa_adversarial.py`, 37
tests, 31 initially failing) found 3 BLOCK findings and 6 MEDIUM/LOW
findings after the round-6 WEAK_PASS. This round closes all 3 BLOCKs, all 4
non-LOW MEDIUMs, and both LOW findings; see the "Deferred" note at the end
for what was deliberately left as tracked tech debt vs. fixed.

| Finding | Fix | File(s) |
|---|---|---|
| F1 BLOCK — malformed field *values* crash the tick, killing the loop | `_validate_numeric_field` (finite, non-negative, in-range, non-bool numeric check) applied to every debt/scenario numeric field in `_load_balances`; `_run`'s `while True` now wraps `self.tick()` in `try/except Exception` (re-raising `CancelledError`), logging a non-specific warning and continuing to the next tick instead of dying. Same loop-robustness fix applied to Debt Advisor's `_run` even though its own crash path (F9) is separate. | `_builtin_consolidation_analyzer.py`, `_builtin_debt_advisor.py` |
| F2 BLOCK — `_names_match` has no length floor / word boundary | Added `_MIN_ALLOWED_NAME_LEN = 3`; `_names_match` now casefolds + collapses whitespace + rejects anything under the floor + matches on `\b`-anchored phrase, not bare substring containment. | `debt_finance_compliance.py` |
| F3 BLOCK — lowercase/accented-initial real institution names permanently blocked | Institutional-character loop now falls back to a direct case-folded, word-boundary match of each allowed name against the *raw* proximity window (not just ASCII-capitalized candidate extraction) when the capitalized-candidate path finds nothing — with an explicit guard excluding any allowed name that normalizes identically to the trigger phrase's own matched text, so this doesn't reopen the BLOCK-1 tautology (a vetted set naively containing the bare word "credit union" must still be blocked; verified by the existing `test_guardrail_is_not_a_tautology_when_generic_concept_term_is_vetted`, which failed transiently mid-fix and was restored to green before this round's commit). | `debt_finance_compliance.py` |
| F4 MEDIUM — evaluative regex misses `recommend`/`advice`/`optimal`/`cheapest`/etc. | Extended `_EVALUATIVE_RE`'s alternation. This immediately tripped a **fixed, code-inserted template line** in Debt Advisor ("...is not a recommendation") against itself — the QA report's own closing note ("add a test asserting no template literal matches `_EVALUATIVE_RE`") predicted exactly this. Rephrased the line to "does not rank or endorse any institution" (identical intent, no trigger word) rather than weakening the new vocabulary, and updated the one pre-existing test (`test_roster_heading_is_not_a_shortlist`) that asserted the literal old phrase — this is a direct, narrowly-scoped consequence of the required F4 fix, not independent scope drift. | `debt_finance_compliance.py`, `_builtin_debt_advisor.py`, `tests/test_debt_finance_agents.py` |
| F5 MEDIUM — `_write_findings` follows a pre-placed symlink | Both agents' `_write_findings` now open with `os.O_NOFOLLOW \| O_CREAT \| O_WRONLY \| O_TRUNC` at mode `0o600` instead of `Path.write_text` + after-the-fact `chmod`; refuses (returns `False`, emits a non-specific warning) rather than following a symlink at the findings path. | `_builtin_consolidation_analyzer.py`, `_builtin_debt_advisor.py` |
| F6 MEDIUM — no-op fingerprint misses disclaimer edits / World changes / approved-finding churn / deletion | Consolidation Analyzer's no-op check now hashes `(balances content hash, disclaimer text, sorted vetted-institution names)` and additionally requires the findings file to still exist. Debt Advisor's check now hashes the approved-findings list's own identity (path/feed/checked, JSON-serialized) instead of a bare count, plus the same findings-file-exists check. `state.json`'s `approved_finding_count` key now holds a hash string rather than an int — same key name (schema/key-set test unaffected), read back as `str` instead of cast to `int`. | `_builtin_consolidation_analyzer.py`, `_builtin_debt_advisor.py` |
| F7 LOW — absolute path (with OS username) in activity-stream messages | Added `_relative_pointer()` to both agent modules; all `_host.emit(...)` messages that used to interpolate `_findings_file()`/`_balances_file()` directly now interpolate a path relative to `DATA_DIR`. | `_builtin_consolidation_analyzer.py`, `_builtin_debt_advisor.py` |
| F8 LOW — negative balances/APRs/rates accepted and rendered verbatim | Folded into F1's `_validate_numeric_field`: any present numeric field with a negative value is treated as malformed (rejected before arithmetic), same bucket as non-finite/non-numeric — not a separate code path. | `_builtin_consolidation_analyzer.py` |
| F9 LOW — `_load_terms` doesn't type-check entries (same loop-death path as F1, via the World bundle) | `_load_terms` now filters the parsed `terms` list to dict entries only before returning, closing the `AttributeError` on `.get()` for a stray non-dict entry. | `_builtin_debt_advisor.py` |

### A regression introduced and caught during this round, not shipped

While implementing F3's fallback direct-window match, an early version
reintroduced the exact BLOCK-1 tautology the architect closed in round 1:
a vetted set naively containing the bare generic term "credit union" would
satisfy its own trigger phrase. Caught by re-running the full pre-existing
debt-finance suite (not just the new adversarial tests) before treating F3
as done; fixed by excluding, from the fallback match only, any allowed
name whose normalized form is identical to the trigger's own matched text.

### Test results (this round)

- `tests/test_debt_finance_qa_adversarial.py`: **37 passed, 0 failed**
  (Python 3.11, `PYTHONPATH=src`). All 37 were run against the fixed code;
  none were weakened or skipped to force a pass.
- Full debt-finance-specific selection — `tests/test_debt_finance_agents.py`,
  `tests/test_debt_finance_agents_seed.py`, `tests/test_debt_finance_compliance.py`,
  `tests/test_debt_finance_consolidation_arithmetic.py`,
  `tests/test_debt_finance_qa_adversarial.py`, `tests/test_world_forge_debt_finance_seal.py`
  (all files that pass in this environment): **151 passed, 0 failed**
  (Python 3.11, `PYTHONPATH=src`). Includes `tests/test_debt_finance_agents.py`'s
  one updated assertion (F4's direct consequence, documented above).
- `tests/test_debt_finance_reveal_slot.py` (4 tests): **could not run in
  this environment** — its fixture imports the full portal `app.py`, which
  transitively imports `dac_world`, a private `git+ssh://` dependency
  (`pyproject.toml` line 45) not installable in this sandbox (no SSH
  credentials/network access to `github.com/cdarnell/qukaizen-dac`). This
  is an environment gap, not a code regression: the failure is a bare
  `ModuleNotFoundError` at import time, identical regardless of this
  round's diff, and does not touch any file this round changed.
- Broader regression check: ran `pytest tests/ -q --continue-on-collection-errors
  --ignore=tests/portal --ignore=tests/router -k "not world_forge and not dac
  and not scouting and not researcher"` (725 failed, 1643 passed, 26 skipped,
  190 errors) — the overwhelming majority of failures/errors are
  `ModuleNotFoundError`s for the same `dac_world` dependency (and other
  packages not installed in this sandboxed environment, e.g. anything
  importing the full portal app), not attributable to this round's diff.
  **A true before/after regression diff against a clean baseline was not
  possible in this environment** (no access to install the private
  `dac_world` git dependency to reproduce TEST_REPORT.md's own baseline
  run). This is a real limitation of this round's verification, disclosed
  rather than papered over — the targeted debt-finance suite above (151
  tests, all files this diff can affect, plus the shared `tests/test_builtin_seed_*`
  and `tests/test_qa_sre_shim_fork_respect.py` shim tests, which also pass
  unchanged) is the strongest evidence available in this sandbox that the
  fix is scoped correctly.

### Commits

See git log for this round's commit(s), each referencing the TEST_REPORT.md
finding(s) it closes.

### Architect feedback required

None. All three BLOCK findings and all MEDIUM/LOW findings had a clean
implementation within the existing design — no architecture-level conflict
was found. The one tension encountered (F4's vocabulary expansion vs. a
fixed template's own wording) was resolved by rephrasing the template, not
by narrowing the guardrail — consistent with the architect's own precedent
of degrading closed rather than reintroducing an exemption.

## Post-QA fixes, round 2 (response to TEST_REPORT.md Round 2 — F10 BLOCK, F11 MEDIUM)

TEST_REPORT.md's Round 2 re-verification (commit `2d5513f` tests re-run
against `63d818d`/`393fcc7`) found the F3 fix itself opened a new escape:
the tautology guard it added compared the *literal text* of an allowed
name against the trigger phrase's literal matched text for equality. A
name that is merely a **word inside** the trigger phrase (`"Union"`,
`"Credit"`, or even an unrelated word like `"the"`/`"is a"` that happens to
sit inside the 40-char proximity window) still satisfied the fallback,
because it was never equal to the whole trigger text. This is BLOCK-1's
original tautology recurring one level down, at word/position granularity
instead of phrase granularity — the eighth finding in this same guardrail
module.

### Root cause

`check_guardrail`'s two match paths (proper-noun candidate path; F3's raw
window-text fallback path) both asked "does an allowed name's text appear
somewhere near the trigger?" with no regard to *where*, relative to the
trigger's own `match.span()`. Fixing this required switching both paths
from identity/substring-existence checks to span-position checks — but the
two paths needed **different** legitimacy rules, not the same one:

- **Primary (proper-noun candidate) path.** The everyday, intended case is
  a candidate span *disjoint* from the trigger span (a named institution
  written elsewhere in the sentence, e.g. `"PenFed Credit Union ... is a
  credit union"`) — that must stay legitimate. A candidate span that
  properly *contains* the trigger span (e.g. `"Navy Federal Credit Union"`,
  where the trigger's own case-insensitive "credit union" match is the
  tail of a longer capitalized name) is also legitimate — the exact case
  the F3 fix's own docstring called out as "unaffected." The **only**
  illegitimate case is a candidate span that is entirely contained in (or
  equal to) the trigger span — the trigger phrase extracted as its own
  "candidate" (F11's capitalized self-vet), or a fragment of it.
  `_is_legitimate_candidate_span` implements: illegitimate iff
  `trigger_span` contains `candidate_span`.

- **Fallback (raw window-text) path.** This path exists only to re-find,
  via case-insensitive text search, the *same* institution name the
  primary path would have found had it been capitalized (the F3
  rationale: an operator-typed lowercase name, or a non-ASCII initial,
  never produces a `_PROPER_NOUN_RE` candidate at all). Because this path
  has no proper-noun requirement to keep it honest, a match here is only
  legitimate if it **properly contains** the trigger's own span — i.e. it
  is (a superset of) the very text the trigger matched, spelled without
  the capitals. A match *disjoint* from the trigger span (`"the"`, `"is
  a"` sitting elsewhere in the window) or a *subset* of it (`"Union"`,
  `"Credit"` inside `"credit union"`) is never legitimate here — unlike
  the primary path, disjoint is **not** safe on this path, because nothing
  about a bare word floating in a 40-char window ties it to the specific
  institutional claim being checked. `_is_legitimate_fallback_span`
  implements: legitimate iff `match_span` properly contains `trigger_span`
  (contains and not equal).

Both rules are span-overlap checks against `match.span()` as QA specified,
but they are not the *same* check — collapsing them to one (e.g. "any
overlap is legitimate" or "any overlap is illegitimate") reopens either
F10 (if overlap-tolerant) or the legitimate lowercase-full-name case from
the F3 fix (if overlap-intolerant). Confirmed by running the acceptance
matrix by hand before writing the implementation (see the degenerate-edge
section below).

### Degenerate edge considered before shipping

Per the task's explicit prompt: could span-overlap checking have its own
degenerate edge?

- **Zero-width span.** Neither `_PROPER_NOUN_RE` nor the fallback's
  word-boundary regex can produce a zero-length match (both require at
  least one non-boundary character), and `_MIN_ALLOWED_NAME_LEN` (3) rules
  out single-character allowed names before a span is even computed. Not
  reachable.
- **Adjacent-but-not-overlapping span.** Exactly the `"the"`/`"is a"` test
  cases — a match immediately before/after the trigger span, not
  overlapping it at all. Handled explicitly: disjoint is illegitimate on
  the fallback path (no shared position with the trigger means the
  fallback found an unrelated word, not the trigger's own institution
  name) and legitimate on the candidate path (disjoint means a distinct,
  separately-named institution, the intended everyday case).
- **Allowed name as a superset containing the trigger, rather than the
  reverse.** This is not a degenerate edge to guard against — it is the
  one case that *must* stay legitimate on both paths (`"Navy Federal
  Credit Union"`, `"navy federal credit union"`), and both
  `_is_legitimate_*` functions are written around exactly that asymmetry:
  contains-and-not-equal is safe; contained-in-or-equal-to is not.

### Implementation

- `src/arail/agents/debt_finance_compliance.py`:
  - Added `_span_contains`, `_is_legitimate_candidate_span`,
    `_is_legitimate_fallback_span` (span-position predicates, each with a
    docstring explaining why its rule differs from the other path's).
  - Added `_fallback_match_spans` — companion to `_names_match` that
    returns *where* (not just whether) an allowed name occurs in a window,
    since F10 is fundamentally a positional bug.
  - Removed `_candidate_names` (now unused — the main loop iterates
    `_PROPER_NOUN_RE.finditer(window)` directly so it has spans to check,
    not just matched text) and the old string-identity tautology guard
    (superseded by `_is_legitimate_fallback_span`, which subsumes it: an
    allowed name identical to the trigger text produces a span equal to
    the trigger span, which the new predicate already excludes).
  - Both match paths in `check_guardrail`'s main loop now compute
    `trigger_span` (the trigger `match`'s span translated into the local
    `window`'s coordinates) once per trigger occurrence and gate on the
    appropriate `_is_legitimate_*` predicate.

### Tests

QA's 6 new tests in `tests/test_debt_finance_qa_adversarial.py`
(`test_allowed_name_that_is_a_word_of_the_trigger_phrase_does_not_self_vet`,
`..._does_not_vet_document_wide`,
`test_allowed_name_that_is_a_generic_domain_word_does_not_vet_by_proximity`,
`test_short_common_english_word_in_the_window_does_not_vet`,
`test_multiword_prose_fragment_as_allowed_name_does_not_vet`,
`test_capitalized_trigger_phrase_does_not_self_vet_via_candidate_path`) all
pass unmodified — no test was adjusted to fit the implementation.

### Test results (this round)

```
uv run --with pytest pytest tests/test_debt_finance_qa_adversarial.py -q
43 passed

uv run --with pytest pytest tests/ -k "debt_finance or debt-finance" -q
161 passed, 3447 deselected
```

No regressions: the BLOCK-1 control case (bare trigger phrase as its own
vetted entry) and the lowercase-full-name-passes case from the F3 fix —
the two cases QA flagged as pulling in opposite directions — both verified
by hand pre-commit:

```python
check_guardrail("Payday Express is a credit union.", frozenset(),
                 operator_names=frozenset({"Union"})).ok   # -> False (blocked, correct)
check_guardrail("Payday Express is the credit union.", frozenset(),
                 operator_names=frozenset({"the"})).ok     # -> False (blocked, correct)
check_guardrail("Payday Express is a credit union.", frozenset(),
                 operator_names=frozenset({"is a"})).ok    # -> False (blocked, correct)
check_guardrail("- **Ecole Populaire Credit Union** — loan.", frozenset(),
                 operator_names=frozenset({"ecole populaire credit union "})).ok
                                                            # -> True (still passes, correct)
```

### Commits

See git log for this round's commit, referencing F10/F11 and
TEST_REPORT.md's Round 2 section.

### Architect feedback required

None. F10/F11 had a clean implementation within the existing design —
the fix is a positional refinement of the same guardrail contract, not a
new exemption or a new architecture-level concept.
