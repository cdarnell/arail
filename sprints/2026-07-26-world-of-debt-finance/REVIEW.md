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

---

# Review addendum — post-fix re-review

**Date:** 2026-07-27
**Fix under review:** commit `3d56c9b` ("fix(debt-finance): close the
vetted-institution guardrail tautology (BLOCK-1/2/3)")
**Prior verdict:** BLOCK at `2c7dce1` (BLOCK-1, BLOCK-2, BLOCK-3)

## Verdict: BLOCK

BLOCK-1, BLOCK-2 and BLOCK-3 are genuinely fixed, and the reasoning behind
the BLOCK-1 fix is better than the fix I asked for. But the new guardrail
carries a reproducible residual of the same defect class, and the two
questions the builder correctly refused to decide unilaterally have answers
that require code changes. All remaining work is narrow and fully specified
below; this is a short round trip, not a redesign.

---

## What the fix got right

- **BLOCK-2 — closed.** `_builtin_debt_advisor.py:271` now renders
  `v.institution_type.replace("-", " ")` from the term's own structured
  field. No hardcoded character literal survives in either assembler. The
  "credit counseling agency labelled as a credit union" output is gone.
- **BLOCK-1 — closed, at the right layer.** I asked for either proper-noun
  matching or a distinct vetted-named-institution source; the builder did
  both, and the data-model half is the more important one. Splitting
  `institutions` into *concept terms* (no `institution_type`) and *named
  institutions* (`institution_type` + third-party `verification_source`)
  fixes the category error rather than papering over it, and requiring all
  three conditions in `_vetted_institutions` / `_vetted_institution_names`
  means the concept terms can never re-enter the vetted set by any route.
  `_names_match`'s one-directional containment, and the docstring explaining
  *why* the reverse direction reintroduces the tautology in a different
  shape, is exactly the kind of reasoning I want recorded at the point of
  the check. The verification sources chosen (NCUA charter lookup, NFCC
  member directory) are third-party and distinct from the institutions' own
  marketing, which is what the design required and what the previous bundle
  did not have.
- **BLOCK-3 — closed.** `TestRealSealedBundle` mounts
  `examples/worlds/debt-finance/` itself. I verified independently that the
  adversarial case fails against the old code path and passes against the
  new one. The "PenFed Lending Group does not ride along on PenFed Credit
  Union" near-miss test is the test I would have written and did not think
  to ask for.
- **`_framing_prose` digit check — closed** in both agents; Debt Advisor
  additionally rejects a vetted institution's name. The last live path for a
  model-generated fact into a findings file is shut.
- **Full-suite delta verified by `git stash` re-run.** Correct methodology
  for a repo with pre-existing red. Accepted as stated.

---

## [BLOCK-4] The sentence boundary is not a boundary — unvetted institutions still ride along on adjacent vetted ones

`_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")` splits only *after*
terminal punctuation. Output lines that do not end in `.`/`!`/`?` are
therefore merged with the following line into a single "sentence", and the
check's pairing rule ("some candidate proper noun in this sentence matches
some vetted name") then vets everything in the merged blob.

This is not hypothetical. Debt Advisor's own vetted-institution renderer
(`_builtin_debt_advisor.py:272-274`) emits lines ending in `)` — no terminal
punctuation — so the shipped output already contains merge-prone lines,
directly adjacent to the approved-scouting-finding metadata block. Verified
against the current code:

```
>>> v = frozenset({"penfed credit union"})
>>> check_guardrail(
...   "- **PenFed Credit Union** (credit union, verification source: https://x)\n"
...   "- **Payday Express** is a credit union.", v)
GuardrailResult(ok=True, reason='')          # <-- passes
>>> check_guardrail("- **Payday Express** is a credit union.", v)
GuardrailResult(ok=False, ...)               # <-- blocks, correctly
```

The identical unvetted claim is blocked alone and waved through when it
follows an unpunctuated vetted line. The Payday Express adversarial test
passes only because it is exercised in isolation.

Second instance of the same class, same function: the loop calls
`_INSTITUTIONAL_CHARACTER_RE.search(sentence)` — **one** trigger per
sentence. A single genuine sentence carrying two triggers, one vetted and
one not, is vetted by the first.

**Required fix.** Both are one function:
1. Split on newlines as well as terminal punctuation —
   `re.compile(r"(?<=[.!?])\s+|\n+")`. A list item is a unit of assertion;
   treat it as one.
2. Iterate `finditer`, not `search`, and require *each* trigger occurrence
   in a chunk to be paired.
3. Regression test for each: the two-line merge above, and a single sentence
   naming a vetted and an unvetted institution with a trigger each. Both
   must fail against `3d56c9b`.

I am flagging this rather than waving it because it is the same defect the
last round blocked on — a check whose passing condition is satisfiable
without the property it claims to enforce — and because the reason it
survived is the same reason the first one did: the adversarial tests
construct the input, and the constructed input does not look like the
assembled document. Test the assembled document.

---

## Resolution — flagged question 1: roster shape and the posture of naming real institutions

**Decided, with conditions. The two named institutions stay. The roster
policy is: named institutions exist to give the vetting mechanism something
real to be correct about, and for no other purpose.** They are a
demonstration of the verification standard, not a directory, not a shortlist,
and not a set that should grow because more names would be useful.

Reasoning, so this is not just a ruling:

- The picks themselves are defensible and I sign off on them. Both claims
  are *character* claims only (charter type, insurance status, NFCC
  membership), both are verifiable against a registry maintained by someone
  other than the institution, both registries are the authoritative one for
  the claim being made, and neither statement is comparative, evaluative, or
  a recommendation. PenFed and GreenPath also happen to sit on opposite
  sides of the concept split (a lender and a counseling agency), which
  exercises the `institution_type` renderer meaningfully. If I were picking
  from scratch I would pick these.
- Two is the right number and I do not want a third added without a reason
  that is about the mechanism, not about coverage. The moment the roster
  reads as "here are the good options," the World has started giving
  financial advice through its data rather than its prose, and every
  compliance property in §7 is being defended in the wrong place.

**Two conditions, both required before merge:**

**(a) The roster must not render as a shortlist.** The current heading is
`## Vetted institutions (from this World's sourced terms)`, followed by
exactly two entries: a consolidation lender and a credit counselor, inside a
document about paying down debt. Neutral prose does not survive that layout —
a two-item list under that heading in that context reads as a recommendation
set regardless of what the sentences say, and this is the single
highest-liability line the product emits. Rename to something that describes
the mechanism (`## Institutions whose character claims this World verified`)
and add a code-inserted, non-model line immediately under it stating that the
list is not exhaustive, is not a recommendation, and exists to show what
verification of an institutional-character claim looks like. That line is a
constant in the assembler, not persona text.

**(b) Verification claims must be time-scoped.** A sealed, versioned,
immutable bundle currently asserts "GreenPath is an NFCC member" with no
expiry. NFCC membership and NCUA charters lapse; the bundle cannot notice.
Add a `verified_as_of` date field to each named-institution term, require it
alongside `institution_type` + `verification_source` in both agents' vetted-set
construction (so an institution without one is simply not vetted, and the
mechanism degrades closed), and render it in the output: *verified against
<source> as of <date>*. This converts an eternal unqualified claim into a
dated one, which is the only honest thing a sealed artifact can say about a
third party's current status.

**One thing I am escalating to the operator rather than deciding**, because
it is about what obligation they are willing to carry, not about engineering:

> Naming PenFed and GreenPath in a sealed, versioned bundle in a repo bearing
> your name creates a small, indefinite maintenance obligation: if either
> institution's status changes, the shipped bundle keeps asserting the old
> status until someone reseals it, and condition (b) makes that visible
> ("verified as of 2026-07-27") but does not make it false. Are you willing
> to own a recurring re-verification pass on this roster — realistically
> annual — or would you rather the World ship with *zero* named institutions
> and the vetting mechanism proven only by test fixtures, accepting that
> VISION win condition (1) is then met only through the operator's own
> `balances.json`?

Both answers are respectable. I recommend keeping the two names *with* condition
(b), because an annual re-check of two registry lookups is a cheap obligation
and the alternative leaves a shipped safety mechanism with no live data. But
this is your call, and it is the only part of question 1 that is.

---

## Resolution — flagged question 2: operator-supplied institution names

**Decided. Yes, a distinct code path is required. This is an engineering
question, not a risk-tolerance question, and I am deciding it rather than
escalating it.**

The reason it is not the operator's call: the guardrail's stated purpose
(§4.3, §7.2, §7.5) is to prevent *the agent* from asserting institutional
character it cannot source. When the operator writes `"institution": "Anytown
Credit Union"` into their own `balances.json`, and the analyzer echoes that
string back inside a summary of the operator's own accounts, the product is
not asserting anything about Anytown Credit Union. It is quoting the user to
the user. Blocking that is not the guardrail being strict; it is the
guardrail firing on the wrong subject, because
`_INSTITUTIONAL_CHARACTER_RE` cannot distinguish "the words 'credit union'
appear inside a proper name the user typed" from "the agent claims this
entity is a credit union." Verified against current code:

```
>>> check_guardrail("- **Anytown Credit Union** — Personal Loan, rate 8.99%.",
...                 frozenset({"penfed credit union"}))
GuardrailResult(ok=False, ...)
```

And the consequence is severe, not cosmetic: `_build_output` raises
`_GuardrailBlocked` on the *whole document*, so one such scenario suppresses
the blended APR, every other scenario, and the entire findings file, on every
tick, forever, with an unactionable message. For the most likely input a
real user will ever stage, this World produces nothing. That is a broken
product, not a conservative one.

**Required design — provenance-scoped exemption, not a weakened check:**

1. `check_guardrail(text, vetted_institutions, operator_names=frozenset())`.
   `operator_names` is built in the analyzer from the `institution` fields of
   the parsed `balances.json` — from the operator's own file, nowhere else.
2. Matching for `operator_names` is identical to vetted matching (full-name
   containment in a candidate proper noun in the same chunk). No looser.
3. Debt Advisor passes `frozenset()` for `operator_names`. Its content is
   entirely World content; the exemption must not exist on that path.
4. `_framing_prose` continues to pass `frozenset()` for **both** sets. Model
   prose gets no exemption of any kind — an operator's institution name is
   exempt as a *quotation*, never as license for generated text.
5. The echo must be marked in the rendered output, because an unmarked name
   in a product-generated document is an implicit assertion. Render the
   analyzer's scenario line as e.g.
   `- **Anytown Credit Union** (as you entered it) — ...`, code-inserted,
   never model-inserted. With that marker the document asserts nothing about
   the institution and the exemption is honest on its face.
6. Tests: the operator's own unvetted name passes; the *same* name appearing
   in Debt Advisor's World-content path still blocks; an unvetted name that
   is **not** in `balances.json` still blocks in the analyzer (i.e. the
   exemption is keyed to the operator's file, not to the analyzer module);
   and `_framing_prose` output naming the operator's institution is still
   rejected.

**Related, [ASK] not blocking:** guardrail failure is all-or-nothing and the
operator-facing message is "failed the language-safety check — see logs."
Once (1)-(6) land, a block should be rare and always the operator's to fix,
so the event should name the offending field or line and say what to do.
Please fix it in the same pass if it is cheap; file it if not.

---

## Tech debt delta vs. the prior review

Repaid: all three items I added last round (vetted mechanism had no data;
hardcoded character string; tests coupled to a synthetic fixture).

New, to be recorded in ARCHITECTURE.md §13:
1. The guardrail is now a three-way policy (World-vetted / operator-quoted /
   neither) implemented as set membership plus a regex. It is still a
   heuristic (§13.2's original prediction), and it now has a second
   provenance axis. If a third provenance ever appears — an agent quoting an
   approved scouting finding that names an institution — this function needs
   a real design, not a third frozenset parameter.
2. Named institutions carry an indefinite re-verification obligation
   (condition (b) above), owned by whoever reseals the bundle.

## Required actions before merge

1. Fix **BLOCK-4** — newline-aware chunking, `finditer` over `search`, plus
   the two regression tests that must fail against `3d56c9b`.
2. Implement the **question-2** design, items 1-6 verbatim.
3. Apply **condition (a)** — rename the roster heading, add the
   code-inserted not-a-recommendation / not-exhaustive line.
4. Apply **condition (b)** — `verified_as_of` on both named institutions,
   required in both agents' vetted-set construction (absent ⇒ not vetted),
   rendered in output. Reseal.
5. Answer the escalated operator question above and record the answer in the
   sprint directory. If the answer is "ship with zero named institutions,"
   stop and come back to me — that reopens actions 3 and 4 and changes what
   the real-bundle tests can assert.
6. Address the failure-message **[ASK]** or file it.
7. Re-review after 1-4. QA still should not run: the current suite would
   certify BLOCK-4's merged-line pass as correct.

---

# Re-review addendum 2 (round 3) — fix commit `7cd07f3`

**Date:** 2026-07-27
**Verdict: BLOCK** — one new finding (BLOCK-5), one documented-debt ASK, one unmet housekeeping action.

## What is closed

- **BLOCK-4 — closed.** Newline-aware chunking + `finditer` are both in.
  The adjacent-lines repro from addendum 1 now returns
  `GuardrailResult(ok=False, ...)`, as does the comma-joined two-institution
  sentence. The builder's self-found second-order case (a vetted name
  anywhere in an unsplit chunk vetting an unrelated trigger) is real, was
  correctly diagnosed, and the per-occurrence proximity window closes it.
  Flagging it explicitly rather than silently widening scope was the right
  call and I want it on the record as such.
- **Condition (b), `verified_as_of` — closed and correctly fail-closed.**
  Verified directly: fresh terms yield both institutions; terms with a
  2020 date yield `[]`; terms with the field removed yield `[]`. It gates
  set *membership*, not a log line, in both agents. Rendered in output.
- **Condition (a), roster heading — closed and real.** The heading is
  `## Institutions whose character claims this World verified` and the
  not-exhaustive / not-a-recommendation line is appended unconditionally
  in `_build_output`, code-inserted, above the `if vetted:` branch — it
  renders even when the roster is empty. Not an unused string.
- **Question 2, items 2/3/4/5 — closed.** Matching is identical to vetted
  matching; Debt Advisor passes `frozenset()` explicitly; both agents'
  `_framing_prose` self-checks with empty vetted *and* default-empty
  operator sets, so model prose can never exploit either exemption; the
  `(as you entered it)` marker is code-inserted and conditional.

## BLOCK-5 — the operator-names exemption is scoped to the wrong field and does not fix the failure mode it exists to fix

Required action 2 item 1 specified `operator_names` as built "from the
`institution` fields of the parsed `balances.json`." The implementation
builds it from `debts` only and deliberately excludes `candidate_scenarios`
(`_operator_institution_names`, docstring). But `candidate_scenarios` is the
*only* place the analyzer renders an institution name at all — the "Current
position" section emits counts and a blended APR, no names. So the exemption
can fire only when a scenario's institution coincidentally duplicates one of
the operator's existing debts. That is the rare case. The common case is
untouched:

```
debts     = [{"institution": "Chase", ...}]
scenarios = [{"institution": "Anytown Credit Union", "product": "Consolidation Loan", ...}]
-> operator_names = frozenset({'chase'})
-> _GuardrailBlocked: institutional-character language ('Credit Union') not
   paired with a vetted, specifically-named institution near that claim
```

This is the exact repro from addendum 1, still live: the whole document —
blended APR, every scenario, the entire findings file — is suppressed on
every tick, forever, with "failed the language-safety check — see logs." An
operator staging a credit-union consolidation offer is not an edge case; it
is the modal input to this agent, and consolidation offers come from credit
unions more often than from anything else.

The builder's counter-reasoning ("a candidate scenario's institution is a
claim about who is *offering* a comparison product") is engaged with, and
rejected. The exemption is keyed to **provenance**, not to semantics.
`candidate_scenarios` and `debts` live in the same file, typed by the same
person. The agent is not asserting the offer exists; the operator typed it,
and the analyzer is quoting them back to themselves — which is precisely
what the `(as you entered it)` marker was specified to make honest. The
builder built the marker and then gated it on the set that never reaches it.

**Required fix:** build `operator_names` from the `institution` fields of
both `debts` and `candidate_scenarios` in the parsed `balances.json` —
nothing else, still never scouting findings and never World terms. Keep the
strict matching rule and the marker. Add a regression test asserting the
Chase/Anytown-Credit-Union input above produces a document (not a block),
that the scenario line carries `(as you entered it)`, and that an
institutional-character claim about a name in *neither* list still blocks.

## [ASK-A] Residual proximity leak — heuristic limit, documented debt, not a block

`_PROXIMITY_WINDOW_CHARS = 40` is offset luck, not a property. Verified:

```
"PenFed Credit Union; Acme Lending is a nonprofit."   -> ok=True   (leaks)
"PenFed Credit Union and Acme Lending are nonprofit." -> ok=False  (blocks)
```

Same shape, opposite outcomes, decided by four characters of offset. I am
*not* blocking on this, and the distinction from BLOCK-1/BLOCK-4 matters:
those were tautologies reachable in the actual assembled document. This one
is not. Every remaining line in both assemblers is code-inserted, one
assertion per line, and the only free-text path (`_framing_prose`) is
self-checked against an *empty* vetted set, so it cannot exploit a
proximity match at all. Semicolons, em-dashes and list continuations are
therefore unreachable in practice today. Record it as debt; any future
change that renders two institution names on one line reopens it as a
blocker.

## [ASK-B, carried] Failure message

Required action 6 was not addressed and no ticket was filed. Once BLOCK-5
lands, a guardrail block becomes rare and always the operator's to fix, so
"see logs" is the wrong terminal message. Name the offending field/line
value and say what to change, or file it.

## Housekeeping — required action not done

`ARCHITECTURE.md` was not touched in `7cd07f3`. The two debt items from
addendum 1 (three-way provenance policy needs a real design if a fourth
provenance appears; named institutions carry an indefinite re-verification
obligation) are still unrecorded in §13, and ASK-A above is a third. Record
all three before PASS.

## Required actions before merge

1. Fix **BLOCK-5** — widen `operator_names` to `candidate_scenarios`,
   with the three regression assertions above. Reseal if any bundle file
   changes (it should not).
2. Record ASK-A and the two addendum-1 debt items in `ARCHITECTURE.md` §13.
3. Address or file **ASK-B**.
4. Re-review after (1). QA still should not run: the current build produces
   no output at all for the analyzer's most likely input.

---

# Re-review addendum 3 (round 4) — verdict: BLOCK

**Build:** `eb0070a`
**Reviewed:** the diff and the current source of
`_builtin_consolidation_analyzer.py`, `_builtin_debt_advisor.py`,
`debt_finance_compliance.py` — not the builder's summary.

## 1. BLOCK-5 is genuinely closed

`_operator_institution_names(debts, scenarios)` unions both fields
(`_builtin_consolidation_analyzer.py:295-305`) and the single call site
passes both (`:500`). Verified live:

    debts=[Chase], candidate_scenarios=[Anytown Credit Union]
    -> frozenset({'anytown credit union', 'chase'})

**`_framing_prose` still gets ZERO exemption**, on both agents —
analyzer `:262` `check_guardrail(text, frozenset())`, advisor `:260`
same, plus the advisor's additional vetted-name rejection. Debt Advisor's
body check passes `operator_names=frozenset()` explicitly (`:327`) with
the reason in a comment. That property holds.

One [INFO], not a block: the prose is later re-checked *inside* the body
with `operator_names` in scope (`:314` + `:359`), which is contrary to the
letter of `check_guardrail`'s docstring ("all model-generated/framing prose
get no exemption of any kind"). It is not exploitable, because prose
containing any trigger phrase is already rejected by the zero-exemption
standalone gate and prose is newline-separated from every other line, so it
can neither host a trigger nor donate a proper noun into another chunk's
window. Defense-in-depth only — worth a comment at `:359` noting *why* the
overlap is safe, since the docstring currently reads as if it were violated.

## 2. BLOCK-6 — the provenance policy was applied to only one of the
guardrail's two branches; the other suppresses the modal real input

`check_guardrail` has two branches. The institutional-character branch is
now provenance-aware (vetted / operator-quoted / neither — §13.8). The
evaluative branch is not:

    debt_finance_compliance.py:211
        if _EVALUATIVE_RE.search(text):
            return GuardrailResult(ok=False, ...)

It runs on the **entire assembled body**, before chunking, with no
provenance distinction of any kind. The guardrail exists to stop ARAIL from
*asserting* an evaluative claim. This branch instead polices text ARAIL is
*quoting* — and both agents render operator- and third-party-authored free
text into the body:

- Analyzer `:346-353` renders `r.product`, `r.source`, `r.as_of` verbatim.
  `_EVALUATIVE_RE` includes `best|lowest|guaranteed`, and `\b` treats a
  hyphen as a boundary, so an ordinary pasted citation URL matches.
- Advisor `:313-319` renders `f.get('feed')` and `f.get('path')`, parsed
  out of an approved scouting finding — i.e. externally-authored RSS text.

Verified live, both agents, with non-adversarial inputs:

    Analyzer: source = "https://www.nerdwallet.com/best-balance-transfer-cards"
      -> BLOCKED: evaluative or imperative language detected
    Advisor:  feed   = "Best Balance Transfer Cards - Bankrate"
      -> BLOCKED: evaluative or imperative language detected

This is BLOCK-5's exact defect shape one branch over: the single most
likely thing an operator will paste into `source` — a NerdWallet or
Bankrate "best-balance-transfer-cards" URL — suppresses the entire findings
document, on every tick (the input hash is only saved on success, so it
re-blocks and re-warns forever). The agent asserts nothing evaluative; it
quotes the operator's own citation back to them.

96/96 tests pass because every fixture URL is sanitized
(`example.invalid/rates`, `penfed.org/personal-loans`, `example.gov/...`,
`ncua.gov/...`) — the suite has no realistic marketing URL or feed title
anywhere. Same reason rounds 1-3 passed green while failing the real input.

### Required fix

Do **not** widen the vocabulary exemption globally — that would let the
model's own prose say "best". Make the evaluative branch provenance-aware
the same way the character branch already is. The straightforward shape:

- Check `_EVALUATIVE_RE` against the **agent-authored** portion of the body
  only, and exempt the code-inserted verbatim echo spans (`r.source`,
  `r.product`, `r.as_of`; advisor `feed`/`path`). Passing the assembled
  string and hoping is what created this.
- If a quoted span is exempted, it must still be *marked* as a quote in the
  rendered line, the same way `institution` gets "(as you entered it)" —
  otherwise a "best balance transfer" product name reads as ARAIL's
  characterization. Today `product`/`source`/`as_of` carry no provenance
  marker at all even though `institution` on the same line does.
- Note that `_framing_prose`'s standalone gate must keep checking
  `_EVALUATIVE_RE` with no exemption (it does — the whole-text branch runs
  regardless of the empty name set). Do not break that.

Regression assertions required:

1. Analyzer: scenario with `source` =
   `https://www.nerdwallet.com/best-balance-transfer-cards` -> document is
   written, and the URL appears verbatim.
2. Advisor: approved finding with `feed` = `Best Balance Transfer Cards -
   Bankrate` -> document is written, and the feed name appears verbatim.
3. Analyzer: `_framing_prose` returning `"This is the best option for you"`
   -> falls back to the deterministic sentence (model prose gets no
   evaluative exemption).
4. Advisor: a *code-authored* line containing "best" (inject via a term's
   `institution_type`) -> still blocks.

## 3. ASK-B fix is incomplete, and currently misdirects

The new analyzer message (`:511-522`) interpolates the reason but then
hardcodes an institutional-character explanation and points the operator at
their `institution` fields. For the evaluative branch — which per BLOCK-6
is the branch that will actually fire in practice — that guidance is
wrong: the operator's `institution` fields are fine and the offending text
is in `source` or `product`. The message tells them to look at the one
field that is not the problem.

Branch the message on the reason, or (better, once BLOCK-6 is fixed) have
`GuardrailResult` carry the offending field/span so the message can name it
instead of guessing. The Debt Advisor message (`:447-457`) has the same
shape but is less harmful because pointing at "the World's content" is
correct for both branches there.

## 4. ARCHITECTURE.md §13 record-don't-fix entries — satisfactory, with
one correction owed

§13.8 (three-way provenance), §13.9 (re-verification obligation) and
§13.10 (`_PROXIMITY_WINDOW_CHARS` tripwire) are all present and are written
at the right level of specificity — §13.10 in particular states its
tripwire condition precisely enough to be actionable. That instruction was
followed.

One factual correction is owed in §13.10, which justifies the "genuinely
unreachable" claim with: *"the only free-text path (`_framing_prose`)
self-checks against an empty vetted set."* That is not true. The analyzer's
scenario line (`:346-353`) renders three operator-authored free-text fields
(`product`, `source`, `as_of`) **on the same line as an institution name**,
and the advisor's findings line renders externally-authored `feed`/`path`.
Those are free-text paths with no self-check, and a `product` value such as
`"transfer to PenFed Credit Union"` puts a second institution name on a
line that already has one — the exact tripwire condition §13.10 says is
unreachable. Update the justification. I am not calling this a live BLOCK,
because in the analyzer every name on that line is inside `operator_names`
anyway, but the stated reason for safety is wrong and a future reader will
rely on it.

## Verdict

**BLOCK.** BLOCK-5 is closed and closed correctly; the prose-exemption
property holds; the §13 entries are satisfactory. BLOCK-6 is a new, live,
independently-verified defect on the most probable real input, in the same
defect class, on the guardrail branch the provenance work did not reach.

## Required actions before merge

1. Fix **BLOCK-6** — make the evaluative branch provenance-aware; add the
   four regression assertions above. Add at least one realistic marketing
   URL and one realistic feed title to the fixtures permanently.
2. Fix the ASK-B message so it does not point at `institution` fields for
   an evaluative-branch block.
3. Correct §13.10's "only free-text path" justification.
4. Add the `:359` comment explaining why the prose/body check overlap is
   safe (INFO).
5. Re-review after (1). QA still should not run.

---

# Re-review addendum 4 — round 5

**Date:** 2026-07-27
**Build:** commit `69d5aa9` (BLOCK-6 fix)
**Verdict: BLOCK** (BLOCK-7)

## BLOCK-6 — CLOSED

The masking approach is sound. `quoted_spans` are blanked out of a copy of
`text` before `_EVALUATIVE_RE` runs; the institutional-character branch
explicitly runs on the original unmasked `text`, with a comment saying so.
The longest-first sort is real and correct for the containment case (a
shorter span that is a substring of a longer one no longer corrupts the
longer span's literal before its own `.replace`). BLOCK-1 through BLOCK-5
are **not** reopened: `quoted_spans` cannot smuggle an institutional-
character claim past the other branch, because that branch never sees the
masked string.

## BLOCK-7 — the same defect, in the sibling fields the fix skipped

`quoted_spans` was populated from *some* of the non-agent-authored free-text
fields rendered into the body, not all of them. Two live instances, both
verified by two-sided repro against the built code:

**(a) Consolidation Analyzer — `r.institution`.**
`_build_output` masks `r.product`, `r.source`, `r.as_of` but not
`r.institution`, which is rendered on the same line (`:361`), drawn from the
same operator-typed `candidate_scenarios` entry, and already carries the
strongest provenance marker in the codebase — literally "(as you entered
it)". Repro (empty vetted set, operator-typed scenario):

```
'Best Egg'                 -> BLOCKED: evaluative or imperative language detected
'Best Buy'                 -> BLOCKED
'Lowest Rate Credit Union' -> BLOCKED
'Egg Financial'            -> PASS   (control: same line, no evaluative word)
'LightStream'              -> PASS   (control)
```

Best Egg is a top-tier real US debt-consolidation lender — the single most
likely `candidate_scenarios.institution` this agent will ever see. Best Buy
is one of the most common retail cards in an American debts list. The
findings document is suppressed forever, exactly as in BLOCK-6.

**(b) Debt Advisor — `v.verification_source` (and `v.name`).**
`_build_output` masks `feed`/`path` but not the vetted-institution roster
line (`:300-304`), which renders `v.name`, `v.institution_type`, and
`v.verification_source` — a URL, i.e. precisely the field class BLOCK-6 was
about. Repro:

```
verification_source='https://ncua.gov/lookup'                  -> PASS
verification_source='https://www.nerdwallet.com/best-credit-unions' -> BLOCKED
```

That is the *same nerdwallet URL family from the BLOCK-6 finding*, in the
sibling field. A citation to a "best credit unions" roundup is an entirely
ordinary way to verify a credit union's character claim — and here it is
World-sealed content, so the operator cannot fix it without re-authoring the
bundle.

This is not a hypothetical: ARCHITECTURE.md §13.10's own new correction text
(committed in 69d5aa9) states that the scenario's `institution` "is drawn
from the same `candidate_scenarios` entry that produced the line" — the exact
provenance argument used to justify masking the other three fields. The
reasoning was written down and then not applied to the field it describes.

Test evidence supports the "made my own repro pass" reading: 107/107 pass,
but no test in `tests/test_debt_finance_agents.py` puts an evaluative word in
a scenario `institution`, a `v.name`, or a `verification_source`.

## ASK-C — global `.replace` over-masks

Masking uses `text.replace(span, ...)`, which blanks *every* occurrence of
the span anywhere in the body, not the code-inserted position. A short
operator-supplied value therefore de-fangs the check on unrelated text:

```
as_of='st'  ->  "...this is the best option."  passes the evaluative check
```

Degrades open, not closed. Mitigated for `_framing_prose` (self-checks with
an empty span set first) but not for other body text. Fix by masking at known
insertion offsets, or at minimum refusing spans below a length floor.
Not a BLOCK on its own; must not be shipped undocumented.

## Round-4 secondary items

1. **ASK-B branch message** — [ASK] Branching on `REASON_EVALUATIVE` vs
   `REASON_INSTITUTIONAL_PREFIX` is correct and now names the right branch.
   But the evaluative hint lists only `product`, `source`, `as_of` — omitting
   `institution`, which is where BLOCK-7(a) actually fires. Once BLOCK-7 is
   fixed the residual misdirection shrinks; the hint should still name every
   field that can trip the branch.
2. **§13.10 correction** — [INFO] Factually right this time. It withdraws the
   false "only free-text path" claim, names the actual free-text paths, and
   states a narrower, checkable unreachability argument plus a sharper
   tripwire. Accepted.
3. **`operator_names`-scope comment** — [INFO] Honest, not papered over, and
   its load-bearing claim verifies: `_framing_prose` is appended with a
   trailing `\n` and joined with `\n`, so it is its own chunk under
   `_SENTENCE_SPLIT_RE`, and its standalone self-check (`:264`) passes empty
   name *and* empty span sets. Accepted.

## Required actions before merge

1. Add `r.institution` to the analyzer's `quoted_spans`, and `v.name` /
   `v.institution_type` / `v.verification_source` to the advisor's.
2. Tests: evaluative word in a scenario `institution` ("Best Egg"), in a
   vetted `v.name`, and in a `verification_source` URL — each with a
   matching negative control proving the evaluative branch is not gutted.
3. Document or fix ASK-C (offset-based masking, or a span length floor).
4. Extend the ASK-B evaluative hint to name `institution`.
5. Re-review after (1)-(2). QA still should not run.

---

# Re-review addendum 5 (round 6)

**Date:** 2026-07-27
**Build:** BUILD_LOG.md "Post-review fixes, round 5" at `b7cbda9`
**Prior:** addendum 4 (round 5) at `6a2eb83` — BLOCK-7(a)/(b), ASK-C

## Verdict: WEAK_PASS

BLOCK-7(a), BLOCK-7(b) and ASK-C are closed. One new finding, ASK-D, is a
real defect in the round-5 fix but degrades **closed**, is unreachable with
any realistic `terms.json` value, and does not justify a seventh blocking
round. It is filed below with a recommended structural fix that also closes
the defect family instead of extending it by one more field.

## 1. Independent re-derivation of the interpolated-field list

I re-derived both field lists from the render loops directly, without
consulting BUILD_LOG's tables first, then diffed against them.

**Analyzer `_build_output` (`:307-364`)** — `_framing_prose()`,
`len(debts)`, `apr`, `r.institution`, `marker`, `r.product`, `r.rate`,
`r.fee_pct`, `r.fee_amount`, `r.monthly_savings`, `breakeven_text`
(wrapping `r.breakeven`), `r.source`, `r.as_of`, plus static headings.
The four string-typed operator fields are exactly
`{institution, product, source, as_of}` and all four are now in
`quoted_spans`. `marker` and `breakeven_text` are code-authored literals
containing no `_EVALUATIVE_RE` vocabulary. `debts` entries are never
rendered individually — only `len(debts)` and the computed `apr` — so no
debt-side string reaches the body. **Complete; matches BUILD_LOG.**

**Advisor `_build_output` (`:266-355`)** — `_framing_prose(vetted,
findings)`, `v.name`, `character` (= `v.institution_type.replace("-"," ")`),
`v.verification_source`, `v.verified_as_of`, `f.get('feed')`,
`f.get('checked')`, `f.get('path')`, plus static headings and the
non-exhaustiveness disclaimer. That is the whole set. **Complete; matches
BUILD_LOG.**

I independently checked the two rows BUILD_LOG declined to mask, since
"it's a date string" is exactly the kind of unverified claim that produced
BLOCK-5 through BLOCK-7:

- `v.verified_as_of` — [INFO] Claim verified. `_vetted_institutions`
  (`:167-171`) admits an entry only if `is_verification_fresh(verified_as_of)`
  returns true, which requires a parseable ISO date. A value carrying
  `_EVALUATIVE_RE` vocabulary cannot reach the roster line at all, because
  the entry is dropped before rendering. Not masking it is correct and the
  stated reasoning is sound.
- `f.get('checked')` — [INFO] Claim verified. The only writer is
  `research/agenda_watch.py:156`, `datetime.now(timezone.utc).isoformat()`,
  code-generated. The one residual path is an operator hand-editing an
  approved scout file's `- Checked:` line in their own PKB; that degrades
  closed (false block on their own edit) and is not worth masking.

The framing-prose rows are right and the reasoning is the right way round:
model-generated text must get *less* exemption, not more. Both agents'
standalone self-checks pass an empty span set (`analyzer:262`,
`advisor:261`), so the exemption genuinely cannot leak to model output.

One documentation nit, not a defect: BUILD_LOG describes `f.get('feed')` as
an "RSS feed title". `_approved_findings` parses the `- Feed:` line, which
`agenda_watch` writes as `feed.url`. It is still third-party-authored and
still correctly masked; only the table's description is off.

## 2. Is `_MIN_QUOTED_SPAN_LEN = 5` a safe floor, or does it move the threshold?

The floor is safe, and for a stronger reason than the one BUILD_LOG gives.

BUILD_LOG argues the floor "covers realistic short trigger substrings
plus one character of margin." That argument is weak on its own — it is a
length coincidence, not an invariant, and would break the moment someone
adds a longer trigger word to `_EVALUATIVE_RE`. The floor being 5 does not
by itself prevent a *long* span from blanking a trigger word elsewhere: a
span like `"Best Egg"` (8 chars) is masked globally, and would blank a
`"Best Egg"` occurrence anywhere else in the body too.

What actually makes this safe is that there is no "elsewhere" for it to
defang. The only non-quoted text in either body is (a) static code-authored
headings, audited to contain no trigger vocabulary, and (b) the framing
sentence, which has already passed a zero-exemption `check_guardrail` and
therefore provably contains no `_EVALUATIVE_RE` match before it is ever
concatenated. A global replace can only blank trigger words that live
inside quoted content, which is precisely what the exemption is for. The
floor is a belt-and-braces measure on top of that.

To the specific question asked — a realistic 5+ character institution name
or value that accidentally contains "best"/"lowest" as a substring and
thereby defeats the check for that substring elsewhere: yes, such values
exist ("Best Egg", "Bestow", "LowestRates.ca", a "best-credit-unions" URL),
and yes they are masked globally. But defeating the check "elsewhere"
requires an elsewhere that is both agent-generated and contains the same
literal substring, and the framing-prose pre-check makes that set empty.
Accepted, with one required addition below.

- [ASK-E] The safety argument above depends on an invariant BUILD_LOG never
  states: *the only non-`quoted_spans` text in either body is static
  literals plus a sentence that has already passed a zero-exemption check.*
  That invariant, not the number 5, is what makes global-substring masking
  sound. It is currently undocumented, which means a future change that
  introduces a third source of unquoted text into either body (a
  per-scenario code-authored note, a computed caveat sentence) would
  silently invalidate it with no tripwire. Record it as a comment on
  `_MIN_QUOTED_SPAN_LEN` and in ARCHITECTURE.md §13.10. Follow-up, not
  merge-blocking.

## 3. Was including `v.institution_type` correct scope?

**Correct scope — keep it, do not revert.** The builder was right to
include it and right to flag rather than decide silently. It is rendered on
the same roster line, from the same World-sealed structured record, as
`v.name` and `v.verification_source`; the fact that my live repro only
exercised two of the three fields is a property of my repro, not a
structural distinction. Reverting it would rebuild the exact reasoning that
produced BLOCK-7 — "the review only named these, so only these are in
scope" — which BUILD_LOG's own round-5 post-mortem correctly identifies as
the recurring root cause.

However, the implementation of that row does not work:

- [ASK-D] **`v.institution_type` is masked as its raw value, but rendered
  as its hyphen-replaced value**, so the mask is a no-op for any hyphenated
  value — i.e. for every realistic value, since `terms.json` uses
  `credit-union`, `credit-counseling-agency`. `advisor:300` renders
  `character = v.institution_type.replace("-", " ")` while `advisor:349`
  puts `entry.institution_type` (raw) into `quoted_spans`. Confirmed by
  direct execution: with `institution_type="best-rate-lender"`, rendering
  `"best rate lender"`, passing the raw value as a span still returns
  `ok=False, reason='evaluative or imperative language detected'`; passing
  the rendered value returns `ok=True`. The three tests added this round
  cover `v.name` and `v.verification_source` and do not exercise this path,
  which is why it passed 117/117.

  Severity is ASK, not BLOCK: it fails **closed** (a spurious block, never
  a bypass), and no real `institution_type` value carries `_EVALUATIVE_RE`
  vocabulary, so it is unreachable today. Fix is one line —
  `entry.institution_type.replace("-", " ")` — plus a test at that value.

ASK-D is also the most interesting finding of this round, because it is not
another missed field. The enumeration *did* catch the field. What it missed
is that masking must key on the **rendered string**, not the source field —
a second dimension the field-by-field checklist does not have a column for.

## 4. Is the defect family exhausted? — no, and the approach is the problem

Asked directly: I do not believe a seventh instance is unlikely, and I
think the field-by-field masking pattern is the wrong general fix.

Five rounds have each found the same class, and the countermeasures have
each been one level of thoroughness deeper than the last: match the named
example (round 3), match the sibling field (round 4), enumerate every field
mechanically (round 5). Round 5's enumeration was genuinely better work and
it did catch a field no review had named. It still produced ASK-D, because
the failure moved from *which fields* to *what transform is applied between
the field and the text being searched*. That is the signature of a
countermeasure chasing a defect rather than eliminating it. The next
variant is predictable in shape: a field enumerated correctly, masked
correctly, but rendered through a new transform (truncation, `title()`,
markdown escaping, a `textwrap` wrap that inserts a newline mid-span and
breaks the substring match) — and a newline inserted mid-span would break
masking exactly the way the hyphen does.

The structural root cause is that both agents assemble a flat string and
then try to *reconstruct* provenance from it by substring search. Provenance
is known exactly at assembly time and is being thrown away, then guessed at.
Every fix so far has improved the guess.

**Recommended structural fix (follow-up sprint, not this merge):** have
both `_build_output` functions assemble the body as an ordered list of
`(text, provenance)` segments — `AGENT` for headings, framing prose, and
code-authored connective text; `QUOTED` for every interpolated non-agent
value — and have `check_guardrail` run `_EVALUATIVE_RE` over the
concatenation of the `AGENT` segments only, with `"".join(all segments)`
still used for the institutional-character/chunking pass that legitimately
needs the whole rendered document. This deletes `quoted_spans`,
`_MIN_QUOTED_SPAN_LEN`, the global-replace masking, the raw-vs-rendered
class of bug, and the possibility of a span accidentally matching unrelated
text — all at once, and it makes "did you enumerate every field?" a
non-question, because a field that is not wrapped as a segment is
inescapably `AGENT` and therefore fails closed by construction. It is a
contained change: two render loops and one function, both already fully
covered by the 117 tests, which become the regression harness for it.

I am recommending this as a follow-up rather than a BLOCK because the
current state is safe — every known failure mode in this family now
degrades closed — and because a sixth consecutive blocking round on a
build whose remaining defect is unreachable is not the highest-value next
step. The honest read requested: this build is done as a *guardrail
correctness* matter. It is not done as a *design* matter, and the right
place to finish it is a scoped refactor sprint with a clear goal, not
another review round on this diff.

## Findings summary

- [ASK-D] `v.institution_type` masked raw, rendered hyphen-replaced — mask
  inert for all realistic values. Fails closed. One-line fix + test.
- [ASK-E] The invariant that makes global-substring masking sound is
  undocumented; no tripwire if a third source of unquoted text is added.
- [INFO] BLOCK-7(a) closed — `r.institution` in analyzer `quoted_spans`.
- [INFO] BLOCK-7(b) closed — `v.name` / `v.verification_source` in advisor
  `quoted_spans`; scope extension to `v.institution_type` correct.
- [INFO] ASK-C closed — short-span floor; safety argument holds for a
  better reason than the one given (see §2).
- [INFO] Field enumeration independently re-derived and confirmed complete
  for both `_build_output` functions; both "date string" exclusions
  verified against their actual writers rather than accepted on assertion.
- [INFO] BUILD_LOG describes `f.get('feed')` as an RSS title; it is
  `feed.url`. Cosmetic.

## Tech debt delta

Added, beyond ARCHITECTURE.md's prediction: the `quoted_spans` masking
mechanism itself is now the largest single source of defects in this sprint
(5 of 7 BLOCKs). Record it in ARCHITECTURE.md §13.10 as known debt with the
segment-provenance refactor as its retirement plan.

## Required actions before merge

1. Fix ASK-D: mask `entry.institution_type.replace("-", " ")`, with a test
   using a hyphenated value that renders to evaluative vocabulary.

## Follow-up tickets (do not block merge)

2. ASK-E: document the "no unquoted agent text other than pre-checked
   framing prose" invariant on `_MIN_QUOTED_SPAN_LEN` and in §13.10.
3. Refactor to segment-provenance assembly (§4); retire `quoted_spans`,
   `_MIN_QUOTED_SPAN_LEN`, and global-substring masking.
4. Correct the `f.get('feed')` description in BUILD_LOG's table.
5. QA may run once (1) lands. The remaining items are design debt, not
   correctness gates.
