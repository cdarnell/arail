# Review: World of Debt Finance

**Date:** 2026-07-27
**Build:** [BUILD_LOG.md](./BUILD_LOG.md) at 6001ad7 (7 commits, 05dfa93..6001ad7)
**Architecture:** [ARCHITECTURE.md](./ARCHITECTURE.md) at 05dfa93
**Plan:** `.claude/plans/snappy-zooming-volcano.md`

## Verdict: BLOCK

The BLOCK-severity privacy constraint (§0.1 — no user figure under `lab/pkb/`)
is genuinely and structurally satisfied, including the `state.json` leak path
the plan flagged. That was the hardest thing to get right and it is right.

But the *other* two-layer safety property this design leaned on — §4.3/§7.2's
"an unvetted institution can never be paired with institutional-character
language, enforced in code, not just persona" — is **not** actually enforced
against the World this sprint ships, and one code path actively violates it.
Both defects are invisible to the test suite because the agent tests run
against a synthetic `terms.json` fixture that does not resemble the sealed
bundle. "67 passed" is accurate and does not mean what it appears to mean.

---

## Spec adherence

Read against ARCHITECTURE.md §§0–13 and the plan's phases A–F.

Honored:
- **§0.1 / §6.2 — the BLOCK.** Traced both agents' every write. The only
  path under `lab/pkb/` either agent touches is
  `lab/pkb/agents/<id>/state.json`, written by `_save_state()` in both
  files. Debt Advisor writes exactly `{terms_hash, approved_finding_count,
  last_run_at}`; Consolidation Analyzer writes exactly `{input_hash,
  last_run_at}`. Both are literal dict constructions — there is no path by
  which a balance, APR, or institution name reaches them, verified by
  reading the constructors, not the comments above them. Findings go to
  `lab/data/user-import/debt-finance/findings/<id>.md` via `_findings_file()`
  in both modules, `chmod 0600`, outside the `_iter_pkb_files` walk. No write
  to `decisions.md` or `agents/recommendations/` anywhere.
- **§7.1 — disclaimer precondition.** `read_disclaimer()` re-reads
  `compliance/DISCLAIMER.md` from the mounted bundle on every call (no
  caching, no module-level constant) and returns `None` if the file is
  missing *or* if `CANONICAL_PHRASE = "not licensed financial advisors"` is
  absent from it. Both agents' `tick()` treat `None` as a hard return before
  any `_build_output`/`_write_findings` call. This is real, not claimed.
  The shipped DISCLAIMER.md contains the phrase and the CROA/state-licensing
  paragraph §7.4 required.
- **§6.1 — parse-failure behavior.** All three branches implemented as
  specified: absent → silent no-op; valid → tick; malformed → one
  non-specific warn event with the path only, no content echo, no crash.
- **§1 / §12 — scope.** Confirmed by `git diff --name-only 9c51502..HEAD`:
  zero changes to `scouting.py`, `agenda_watch.py`, any template, or
  `_TIER_SURFACES`. Portal delta is exactly one `slots` dict entry
  (`user_data`, correctly using the local `from arail.config import DATA_DIR`
  import per the plan's §4 correction) and one button inside `worldCard()`'s
  existing `if (w.mounted)` branch. No `investing` category in `spec.json`.
- **Plan §Load-bearing correction 1 — git tracking.** Traced the fresh-clone
  import path: `loader._SHIPPED` now contains both ids →
  `_seed_if_shipped()` has both branches → `builtin_seed.
  ensure_debt_advisor_folder()` / `ensure_consolidation_analyzer_folder()`
  write a thin PKB shim (`from arail.agents._builtin_debt_advisor import
  debt_advisor`) plus `AGENT.md`, idempotent and fork-respecting via the
  sentinel-docstring check, mirroring `ensure_sre_folder()`. The canonical
  bodies live in `src/arail/agents/`, which is git-tracked. A fresh clone
  gets both agents. Correct.

Drifted (see findings):
- **§7.2's institutional-character check does not function against the
  sealed World** (BLOCK-1).
- **§7.5's "no institution label the code didn't source" is violated by
  Debt Advisor's own output assembly** (BLOCK-2).
- **§11's agent-quality tier does not test the shipped bundle** (BLOCK-3).

---

## Security findings

### [BLOCK-1] The §7.2 institutional-character guardrail is inert against this World's own `terms.json`

`check_guardrail()` (`debt_finance_compliance.py:106-119`) finds each
occurrence of `credit union|nonprofit|member-owned`, takes an ±80-char
window, and allows it through if `any(name in window for name in
vetted_institutions)`.

`vetted_institutions` is built from institutions-category terms
(`_vetted_institution_names`, `_vetted_institutions`). The shipped
`examples/worlds/debt-finance/terms.json` declares exactly two:

```
credit-union             | term: "Credit Union"
credit-counseling-agency | term: "Credit Counseling Agency"
```

So the vetted set contains the literal string `"credit union"`. Any window
containing the phrase that triggered the check necessarily contains a vetted
"name". The condition is a tautology: **`check_guardrail` can never block on
institutional character while this World is mounted.** An arbitrary unvetted
lender — "Payday Express is a credit union" — passes.

This is the entire code half of §4.3's "two-layered, not persona-only"
enforcement, and it is the mitigation cell for the failure-modes row
"A scouting finding mislabels an unverified lender as 'credit union'". The
row is currently unmitigated in code. Persona-only enforcement is what the
design review already rejected.

The bug is a category error in the design's own framing as much as the
build's: the institutions category in `terms.json` holds *concept* terms
("what a credit union is"), not *named institutions*. The vetted-names
mechanism assumed the latter. Fix requires either (a) matching only against
proper-noun institution names — none currently exist in the bundle — or
(b) a distinct field/category for vetted named institutions. Either way the
current check must not ship claiming to enforce something it cannot.

### [BLOCK-2] Debt Advisor hard-codes the label "credit union" onto every institutions-category term

`_builtin_debt_advisor.py:240-243`:

```python
lines.append(
    f"- **{v.name}** (credit union, verification source: "
    f"{v.verification_source})"
)
```

`v.name` is any term whose `category == "institutions"`. Against the shipped
bundle this emits, verbatim, into the findings file:

```
- **Credit Counseling Agency** (credit union, verification source: https://www.consumerfinance.gov/...)
```

A credit counseling agency is not a credit union. This is a
code-inserted institutional-character mislabel — the precise thing §7.5
promised could not happen because "numbers and institution names are
inserted by code from structured fields." The label `credit union` here is
not from a structured field; it is a hardcoded string literal the assembler
assumes applies to the whole category. And BLOCK-1 guarantees the guardrail
waves it through.

Fix: emit the term's own `category`/`short` text, or nothing, rather than a
hardcoded character claim.

### [ASK] LLM framing prose is not checked for digits before it is persisted

`_framing_prose()` in both agents calls `_host.llm_complete(...)`, and the
returned string is spliced into `lines[1]` and written to the findings file.
The only filter applied is `check_guardrail(text, frozenset())`, which
matches evaluative vocabulary and institutional-character phrases — it has no
numeric check. The prompt asks the model not to emit a number or institution
name; nothing enforces it. §7.5's guarantee is "any number... in a findings
file is inserted by code," and this is a live path where a model-emitted
number reaches a findings file. Low likelihood, cheap fix: reject the model
sentence if it contains `\d` or any candidate institution substring, and
fall back to the deterministic sentence (that fallback already exists and is
already exercised — the tests stub `llm_complete` to return `""`, which is
why this path has zero real coverage).

### [INFO] `state.json` home-directory fallback

`_state_file()` in both agents falls back to `Path.home() / ".debt_advisor"`
when `get_pkb_root()` returns `None`. Contents are hash/timestamp only, so no
privacy exposure — but CLAUDE.md's "never a home dir" convention argues for
a repo-relative fallback or a no-op. Worth a follow-up, not a blocker.

### [INFO] Airgapped default and consent path

Confirmed neither agent makes an outbound call: the only host seam that could
is `llm_complete`, which routes to local `deep_policy`. `scouting.py` and
`agenda_watch.py` are untouched, so the `is_airgapped()` short-circuit and
`auto_approved = False` hard-set are structurally intact.

---

## Code quality findings

- **[BLOCK-3] The agent-quality tests do not test the shipped World.**
  `tests/test_debt_finance_agents.py:28-38` defines a synthetic `_TERMS`
  whose institutions entry is `"PenFed Credit Union"` — a term that does
  **not exist** in `examples/worlds/debt-finance/terms.json` (PenFed appears
  there only as a `source` URL). Every "verbatim from its structured source"
  and guardrail assertion runs against this fixture. Consequently:
  `test_institution_and_source_are_verbatim_from_terms` passes on a name the
  product will never print; the hardcoded `(credit union, ...)` label is
  *correct* for the fixture and wrong for reality; and the guardrail's
  tautology is masked because the fixture's vetted name is a proper noun.
  This is the mechanism by which both BLOCKs reached "all green."
  At least one end-to-end test must load `examples/worlds/debt-finance/`
  itself.
- **[ASK] The guardrail-block test is tautological.**
  `TestDebtAdvisorGuardrail` monkeypatches `check_guardrail` to always return
  `ok=False` and then asserts nothing was written. That tests the `try/except
  _GuardrailBlocked` wiring, which is worth testing — but it is *not* a test
  that the guardrail catches anything, and ARCHITECTURE.md §11 explicitly
  asked for "deliberately construct an input designed to trip the §7.2
  guardrail." No such test exists for the agent path. (The unit tests in
  `test_debt_finance_compliance.py` do exercise real phrases against
  `check_guardrail` directly, with a hand-built vetted set — which again
  avoids the real-bundle tautology.)
- **[ASK] Once BLOCK-1 is fixed, the natural operator input becomes a
  silent permanent block.** Consolidation Analyzer renders
  `**{institution}** — {product}` from `balances.json`. If the operator
  stages "Anytown Credit Union" — the single most likely value — a correctly
  functioning institutional-character check blocks the write on every tick,
  forever, with only "failed the language-safety check — see logs." Today
  BLOCK-1 hides this. The fix for BLOCK-1 must account for operator-supplied
  institution names in their own staged scenarios (they are the operator's
  own data, not an unverified claim the product is making) or this World
  produces no analyzer output at all for most users.
- **[INFO]** `_framing_prose(vetted, findings)` in Debt Advisor takes two
  arguments it never uses.
- **[INFO]** Arithmetic (`blended_apr`, `monthly_interest_cost`,
  `breakeven_months`) is clean, pure, correctly edge-cased (zero balance →
  `None`; non-positive savings → `None`; non-positive fee → `0`), and
  genuinely unit-tested against hand-computed values. No complexity or
  duplication concerns anywhere in the three new modules.

---

## The two documented deviations

**1. Sealing to `examples/worlds/debt-finance/` rather than the template
script's `lab/worlds/`.** Correct call, and correctly reasoned. The plan's
literal path said `examples/`; `forge_video_games_world.py` was named only as
a structural template. A personal-finance World auto-appearing in every fresh
lab's catalog would be a product mistake. No new gap — the only consequence
is that mounting goes through "+ Add a World…" / `/api/worlds/import`, which
the plan already anticipated (§Load-bearing correction 5).

**2. Debt Advisor cites approved scouting findings by metadata only.**
Correct call, and the strongest judgment in the build. `agenda_watch.
_finding_markdown` genuinely produces unstructured excerpt text with no rate
field; regex-scraping a number out of it would have manufactured exactly the
"real citation, wrong number" risk §7.5 exists to close. Citing feed/checked-
date/path is strictly more conservative than the spec and attaches no
institutional-character label. No new gap.

The cost, which BUILD_LOG.md does not name: combined with the fact that
`terms.json`'s institutions category holds concepts rather than named
institutions, **no code path in this build ever emits a named institution
from World content.** VISION win condition (1) — "at least one concrete,
sourced, named-institution statement" — is met only through the operator's
own `balances.json` scenario names, i.e. only by the operator telling the
product something it already knew. That is a product-level gap worth an
explicit decision, not a silent one.

---

## Test coverage assessment

67 tests across 6 files; they run and the count is honest. Distribution
roughly matches §11's weighting. Genuinely strong areas: arithmetic
(hand-computed, multiple edge cases), disclaimer precondition
(present/missing/altered/no-bundle/reads-fresh — the altered case really does
strip the canonical phrase and assert refusal), `state.json` content (asserts
the exact key set *and* greps the serialized blob for forbidden figures —
this is a real security assertion, not a file-exists check), `chmod 0600`,
malformed-input no-echo (plants `secret-balance-99999` in the bad JSON and
asserts it is absent from the warning), reveal-slot traversal rejection, and
the seal test's agenda-ordering assertion (position-4 source really is
asserted *not* to produce a watch — the CI catch the design asked for).

The gap is not breadth, it is fixture realism: the two agent-behavior files
never touch `examples/worlds/debt-finance/`, so no test observes what this
product actually prints. Add a real-bundle end-to-end test and BLOCK-1 and
BLOCK-2 both fail immediately.

Not exercised at all: the `llm_complete`-returns-real-text path (always
stubbed to `""`), the `asyncio` `_run()` loops (only `tick()` is called), and
the §11 regression item "existing Worlds still mount and scout" (BUILD_LOG
reports a targeted `-k` run; a full-suite run was abandoned for
environment reasons — acceptable given the zero-diff to `scouting.py`/
`agenda_watch.py`, but it is an assertion by argument, not by test).

---

## Tech debt delta

vs. ARCHITECTURE.md §13's prediction: items 1 (two hand-rolled tick loops),
2 (guardrail is a heuristic), 3, 5, 6, 7 all landed as forecast. §13.7 is
partially repaid — the `user_data` reveal slot was built, generically, so
"open the file yourself" is no longer the only story.

New debt not anticipated by §13, to be added there:
1. The vetted-institution mechanism has no data to operate on: `terms.json`'s
   `institutions` category holds concepts, not named institutions. §7.2 and
   §4.3 both assume named institutions exist there.
2. Debt Advisor's output assembler contains a hardcoded institutional-
   character string.
3. Agent tests are coupled to a synthetic World fixture that diverges from
   the shipped bundle.

---

## Required actions before merge

1. **Fix BLOCK-2:** remove the hardcoded `(credit union, ...)` label from
   `_builtin_debt_advisor.py:240`. Emit only what the term's own structured
   fields say.
2. **Fix BLOCK-1:** make the institutional-character check able to refuse
   something while `debt-finance` is mounted. Either introduce a distinct
   vetted-named-institution source (and populate it, which also addresses
   the VISION win-condition-(1) gap), or match only proper-noun institution
   names and exclude the concept terms. Do not ship a check whose passing
   condition is structurally always true.
3. **Fix BLOCK-3:** add at least one end-to-end test per agent that mounts
   `examples/worlds/debt-finance/` itself and asserts on the resulting
   findings text. It must fail today against items 1 and 2.
4. **Decide, explicitly, on the ASK in "Deviations":** whether v1 shipping
   with no named institution from World content is acceptable, or whether
   `terms.json` gains named-institution entries (PenFed already has the
   verification source). Record the decision in OPEN_QUESTIONS.md either way.
5. **Resolve the ASK on operator-supplied institution names** before or
   alongside action 2, so the fix doesn't convert a defanged check into a
   permanently-blocking one for the common case.
6. Address the digit-check ASK on `_framing_prose` (cheap; closes the last
   live path by which a model-generated number reaches a findings file).
7. Re-review after 1–3. QA should not run until then — the current suite
   would certify the mislabel as correct.
