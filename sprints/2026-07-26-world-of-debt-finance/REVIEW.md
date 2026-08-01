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

---

## Re-review addendum 6 — segment-based provenance refactor (round 7)

**Date:** 2026-07-27
**Commits reviewed:** 689383a, 3bed0e0, ccc2b61, d105fed, fe3d344
**Verdict: WEAK_PASS**

I proposed this refactor in addendum 5. It was implemented substantially as
intended, and it does structurally close half the defect family. It does not
structurally close the other half — but nothing in the remaining half is
reachable through either agent's templates today, so there is no live BLOCK.

### What is now genuinely structural (closed, not patched)

The **evaluative/imperative check** is sound as a general primitive. It
concatenates only AGENT segments and does zero positional reasoning — no
offsets, no masking, no windows, no name sets. BLOCK-6/BLOCK-7 (a benign
WORLD URL containing "best") and the vetted-roster marketed-name variant are
not "fixed"; they are no longer expressible. The joining of AGENT segments
with a space also correctly prevents two adjacent AGENT segments fusing into
a word neither contains. This half of §13.11 is closed.

### What is NOT structural — the neighbour rule is a proximity window in
### segment units

`check_guardrail` legitimizes an institutional-character trigger if the
trigger's own segment *or either immediate neighbour* is non-AGENT. That is
a ±1 window. It has replaced `_PROXIMITY_WINDOW_CHARS` with a window
measured in segments rather than characters — it has not removed the
positional inference. BUILD_LOG's claim that there is "no proximity window
... anywhere in this path any more" is inaccurate as written.

Adjacency does not establish that the vouching segment is a *name*.
Verified empirically against the new API:

    [world("2026-01-15"), agent(" — Acme Bank is a nonprofit credit union.")]  -> ok=True
    [world("https://ncua.gov/x"), agent(" Globex is a member-owned credit union.")] -> ok=True

A verified-as-of **date** and a citation **URL** each vouch for a character
claim about an entirely different, unvetted, agent-invented name. This is
the same shape as every prior finding in the family: a positional proxy
standing in for a referential question.

### The reported `[operator("navy federal"), agent(" is a nonprofit.")]` case

Confirmed `ok=True`. **Not reachable today.** I traced every AGENT segment
that can sit adjacent to a WORLD/OPERATOR segment in both `_build_output`s:
all are hardcoded literals in this repo containing no trigger word. The only
non-hardcoded AGENT text in either agent is `_framing_prose`, and in both
agents it is always its own `lines` entry, and lines are joined with
`Segment.agent("\n")` separators — so a model-generated segment's immediate
neighbours are *always* AGENT joiners and it can never acquire a non-AGENT
voucher. That property is what makes the design safe today.

It is held by inspection of two files. Nothing asserts it: no test, no
runtime check, no comment at the construction sites. It is one plausible
future edit away — `agent(" — a member-owned option")` placed next to
`operator(r.institution)` — from becoming a live escape with no test failing.

Separately, and independent of reachability: **OPERATOR provenance is being
treated as vouching for a character claim, and it does not.** WORLD
provenance has real character semantics (`_vetted_institutions` requires
`institution_type` + `verification_source` + a fresh `verified_as_of`).
OPERATOR provenance means only "the human typed this string into
balances.json" — it vouches that a name is not hallucinated, not that the
institution *is* a nonprofit. The module docstring conflates the two. So the
reported case is not merely a residual gap like §13.10's tripwire; it is a
semantic conflation in the primitive itself.

### WORLD/OPERATOR evaluative exemption — a real trust-boundary trade

Exempting these segments entirely is defensible for OPERATOR (all four
rendered fields carry an explicit "(as you entered it)"/"(as entered)"
marker). It is a genuine coverage trade for WORLD, because a World bundle is
third-party-authorable and mountable. Verified:

    [agent("- **"), world("SomeBank"), agent("** ("),
     world("best guaranteed nonprofit"), agent(")")]  -> ok=True

A World's `institution_type` renders as the character label with **no**
"as the World states it" marker, unlike every operator field. The docstring
frames WORLD exemption as unconditionally safe ("never the agent's own words
by construction") and is silent on the fact that a reader cannot distinguish
World voice from agent voice on the rendered line. I accept the trade —
mounting a World is an explicit trust act — but it must be stated, not
implied.

### Prior findings' behavioral guarantees — one is not preserved

BLOCK-2 (mislabeling), staleness degrade-closed, F10/F11 (moot by
construction), F1's loop backstop: all preserved. **F9 is not preserved in
the Consolidation Analyzer.** `_vetted_institution_names` still iterates
`terms or []` calling `t.get(...)` without the `isinstance(t, dict)` filter
that 393fcc7 added to the Debt Advisor via `_load_terms`. Verified: a
`terms.json` with a stray string entry raises `AttributeError` out of that
function, called unguarded from `tick()`. F1's backstop catches it, so it is
not loop death — it is a silent permanent stall (every tick logs "skipped
this cycle" and no findings are ever written again). Pre-existing, but
ccc2b61 rewired this function's role and left the asymmetry.

### Stale operator guidance

The analyzer's `REASON_EVALUATIVE` hint still tells the operator to inspect
`institution`/`product`/`source`/`as_of` "for wording that reads as
evaluative", and still warns about short values matching substrings. Those
fields are now OPERATOR segments and are never evaluative-checked; the
substring-fusion concern is deleted machinery. That branch is in fact now
effectively unreachable in the analyzer. The hint points the operator at
exactly the fields that cannot cause it.

### Findings

- [ASK] Institutional check's ±1 neighbour rule is a proximity window, not a
  referential link; a WORLD date/URL vouches for an unrelated AGENT name.
- [ASK] OPERATOR provenance conflated with character vetting in the docstring
  and in the neighbour rule.
- [ASK] The invariant that makes both of the above unreachable ("no
  trigger-bearing or model-generated AGENT segment is ever adjacent to a
  non-AGENT segment") is unasserted and untested.
- [ASK] WORLD evaluative exemption is an unstated trust-boundary trade;
  `institution_type` renders unmarked while operator fields are marked.
- [ASK] F9's non-dict-terms hardening never applied to
  `_vetted_institution_names`; silent permanent stall.
- [INFO] BUILD_LOG's "no proximity window anywhere in this path any more" is
  inaccurate.

### Required actions before merge

1. Add a test asserting the template invariant directly: for both agents'
   `_build_output` segment lists, every AGENT segment adjacent to a non-AGENT
   segment is a hardcoded literal free of `_INSTITUTIONAL_CHARACTER_RE`
   matches. This is what makes today's safety a checked property rather than
   a reviewed one.
2. Correct BUILD_LOG's "no proximity window" claim and the module docstring's
   WORLD/OPERATOR conflation; state plainly that OPERATOR vouches for name
   authenticity, not institutional character.
3. Apply the F9 `isinstance(t, dict)` filter to `_vetted_institution_names`.
4. Fix the analyzer's stale `REASON_EVALUATIVE` operator hint.
5. Keep ARCHITECTURE.md §13.11 **OPEN** as tech debt, narrowed: the
   evaluative half is closed; the institutional half remains a positional
   heuristic, now with a documented, verified escape (date/URL voucher) and a
   documented semantic conflation (OPERATOR-as-character-voucher). Do not
   mark §13.11 closed.

---

## Re-review addendum 7 (round 8, 2026-07-27) — `is_name` provenance tag

**Reviewed:** e775da9 (core fix), 871f772 (F9 parity), 6c26893 (stale hint),
523c6e2 (docs, §13.11 CLOSED).

### Verdict: WEAK_PASS — ship. This is terminal; do not schedule a round 9.

### 1. Is `is_name` tagged correctly and completely?

Yes. Full enumeration of every non-AGENT `Segment` construction site in the
codebase (`grep -rn --include="*.py" "Segment\." src scripts`; there are no
others outside the two agents and the compliance module):

**Debt Advisor `_build_output`** — 7 non-AGENT sites:

| Site | Field | `is_name` | Correct? |
|---|---|---|---|
| L349 | `v.name` | **True** | yes — the institution's own name |
| L351 | `character` (`v.institution_type`) | False | yes — a character label, not a name |
| L353 | `v.verification_source` | False | yes — URL |
| L355 | `v.verified_as_of` | False | yes — date |
| L380 | `f["feed"]` | False | yes — an RSS source title, not an institution being characterized |
| L382 | `f["checked"]` | False | yes — date |
| L384 | `f["path"]` | False | yes — a bundle-relative path |

**Consolidation Analyzer `_build_output`** — 4 non-AGENT sites:

| Site | Field | `is_name` | Correct? |
|---|---|---|---|
| L385 | `r.institution` | **True** | yes |
| L387 | `r.product` | False | yes — product name |
| L394 | `r.source` | False | yes — URL |
| L396 | `r.as_of` | False | yes — date |

No fourth candidate exists. The analyzer's "Current position" block renders
only `len(debts)` and a computed blended APR — the `institution` field on
`balances.json`'s `debts` entries is never rendered at all, so there is no
untagged name hiding there. The builder found both sites; the enumeration is
complete.

### 2. Could a segment be mistagged at too coarse a granularity?

No. Both `is_name=True` sites wrap a bare field access (`v.name`,
`r.institution`) with no concatenation, no formatting, and no surrounding
literal. The name segment's `text` is exactly the name and nothing else, so
the tag cannot be laundered onto adjacent prose. This is the property that
makes the fix hold, and it holds.

### 3. Does this close the entire defect family? — Partly. Verified live.

The reported defect is genuinely closed. Both round-7 repros now block, as
does the OPERATOR-provenance variant:

```
[world("2026-01-15"),        agent(" - Acme Bank is a nonprofit credit union.")]  -> ok=False
[world("https://ncua.gov/x"), agent(" Globex is a member-owned credit union.")]   -> ok=False
[operator("Personal Loan"),   agent(" Payday Express is a credit union.")]        -> ok=False
```

But the builder's structural claim — repeated verbatim in ARCHITECTURE.md as
"There is no adjacency math... no positional reasoning of any kind left in the
institutional-character branch" — is **not accurate**, and I verified it:

```
# Case 1 still trusts a non-AGENT trigger segment with NO name pairing at all:
[agent("Payday Express is a "),   world("credit union")]        -> ok=True
[agent("Payday Express offers a "), operator("credit union loan")] -> ok=True

# Case 2 still uses immediate-neighbour ADJACENCY to decide WHICH name a
# trigger is about — a real vetted name vouches for a claim about a
# different, agent-invented one in the same or an adjacent AGENT span:
[world("PenFed",is_name=True), agent(" and Payday Express is a credit union, unlike "), world("Navy Federal",is_name=True)] -> ok=True
[agent("Payday Express is a credit union "), world("PenFed",is_name=True), agent(" Globex is a credit union")]              -> ok=True
```

So the coarse-property-for-fine-question shape **is** still present: the check
treats "an AGENT segment" as the atomic unit for the question "which name is
this claim about." What `is_name` correctly eliminated is the strictly weaker
error "any non-AGENT text counts as a name." That is a real and complete
closure of the *reported* defect, not of all positional inference.

Neither residual is reachable today, and I checked why rather than assuming:
the only model-generated AGENT text in either agent is `_framing_prose`, which
occupies its own line, is neighboured on both sides by `agent("\n")`, is itself
run through `check_guardrail`, and in the Debt Advisor is additionally rejected
if it contains any vetted institution's name. Every AGENT segment adjacent to a
non-AGENT one is a hardcoded literal. Fail-closed holds.

### 4. Ruling on §13.11: **CLOSED is accepted.**

I am overriding my own addendum-6 instruction. The reason I said "narrow, keep
open" was that every prior fix had closed one inference method and left the
next one available. `is_name` is categorically different: it replaces an
inference with a fact asserted at the one call site that knows it, defaulting
closed for anyone who forgets. The builder's reasoning about *why* to close is
right even though its supporting claim about *what* was removed is overstated.
Reopening a defect whose reported shape is structurally unreachable would be
process theatre.

The residuals in §3 above are **not** §13.11. They belong to §13.10 (a single
AGENT segment spanning two disjoint institution mentions), which remains open
and separately tracked, and which must now explicitly own both verified shapes
— the case-1 no-name-pairing path and the name-vouches-across-an-AGENT-span
path. That is a documentation move, not a reopening.

### Findings

- [INFO] `is_name` tagging is complete and correctly granular (§1, §2).
- [INFO] F9 `isinstance` parity, the stale `REASON_EVALUATIVE` hint, and the
  OPERATOR-vs-WORLD docstring clarification (addendum-6 actions 2, 3, 4) are
  all correctly addressed.
- [ASK] ARCHITECTURE.md §13.11's closure paragraph asserts "no positional
  reasoning of any kind left" and "no adjacency math." Both are false as
  verified above. An overstated safety claim in the architecture record is the
  precise mechanism by which the next reviewer stops looking. Correct the
  sentence to what is actually true: *the check no longer infers whether a
  neighbour is a name; it still uses segment adjacency to associate a claim
  with a name, which is why §13.10 stays open.*
- [ASK] The new template-invariant test
  (`test_template_invariant_no_agent_segment_adjacent_to_non_agent_carries_a_trigger_or_is_dynamic`)
  **hand-copies** both `_build_output` templates into the test body rather than
  calling them. It calls `_da._vetted_institutions` and `_ca._compute_scenarios`
  but reconstructs the segment list with its own `S.agent(...)` literals. It
  therefore cannot fail on the exact drift it was written to catch: a future
  edit adding a trigger-bearing AGENT segment next to a non-AGENT one in the
  real `_build_output` leaves this test green. Addendum-6 action 1 asked for
  the invariant to become "a checked property rather than a reviewed one";
  as delivered it is still a reviewed one, now with a green test next to it.
  Make it call the real `_build_output` with `_host.llm_complete` monkeypatched
  and the guardrail's segment list captured.

Neither ASK is a correctness defect in shipped code — the `is_name` check is
the load-bearing control and it fails closed independent of both. They ship as
follow-ups.

### Required actions (follow-up tickets, not merge blockers)

1. Correct the two overstated sentences in ARCHITECTURE.md §13.11's closure
   paragraph; move the two verified residual shapes into §13.10's scope.
2. Rewrite the template-invariant test to exercise the real `_build_output`
   for both agents instead of a hand-copied replica.

---

# Re-review addendum 8 (round 9, 2026-07-31) — post-launch capability upgrade (Workstreams A/B/C)

**Build:** `d1b9db8` (education/content), `106d7bb` (generic scouting), `d7bb412` (tracking + proposed scenarios)
**Architecture:** ARCHITECTURE.md §6.6 (new), §6.1 (`alert_breakeven_months`)

## Verdict: BLOCK

Three BLOCKs. All three are in `106d7bb`/`d7bb412`. Workstream A (`d1b9db8`)
is clean.

The three defects are the same three defect classes this sprint has been
closing for eight rounds, now reintroduced on new surface: a provenance
escape (BLOCK-8), an unbounded-input escape whose code comment asserts a
safety property it does not have (BLOCK-9), and a malformed-input path that
violates the F1 "never crashes the tick" contract it claims to extend
(BLOCK-10). Plus one silent-total-failure bug in `_visible_text` (BLOCK-11,
grouped below as a correctness BLOCK).

---

## BLOCK-8 — `Segment.world(...)` on live-fetched web text is a new trust
decision, and the docstring says it isn't

`_build_proposed_scenarios` (`_builtin_debt_advisor.py`) tags each candidate
value `Segment.world(v)`. Its docstring says this is:

> "the identical treatment a scouting finding's `feed`/`path` already gets
> … this isn't a new trust decision, it's the same one already made for feed
> titles."

That is false, and the falseness is exactly the load-bearing part.

The precedent's own comment at `_builtin_debt_advisor.py:448` states the
justification: *"scouting feed/path is a `Segment.world(...)` — World-sealed
content."* And it is:

- `feed` is the World's own `agenda.json`-declared URL — sealed, and it
  passes `scripts/forge_debt_finance_world.py`'s preflight evaluative-language
  scan before sealing.
- `path` is code-generated by `agenda_watch._write_finding`.
- `checked` is a code-generated ISO timestamp.

A candidate value is none of these. It is a substring of **live third-party
HTTP response text**, fetched at tick time, selected by a regex from a
**seal-exempt** sidecar. It has never been through the preflight scan,
because it did not exist at seal time.

`debt_finance_compliance.py`'s own module docstring pre-writes this finding:

> "This trade is accepted because a World's own authoring-time content … is
> expected to pass the preflight evaluative-language scan in
> `scripts/forge_debt_finance_world.py` before it is ever sealed … If that
> preflight check is ever removed, weakened, or **bypassed**, this runtime
> exemption stops being backed by anything and this section must be
> revisited."

This bypasses it. WORLD segments are never evaluative-checked at all, and
WORLD text renders with **no** "as the World states it" marker — the reader
cannot tell WORLD voice from AGENT voice. So arbitrary evaluative text from a
watched page now renders into an operator-facing document that is otherwise
in the agent's voice, exempt by construction.

The build's own test proves the escape and then asserts it as intended
behavior:

```python
adversarial = _FINDING_WITH_CANDIDATES.replace(
    "`7.99% APR`, `9.99% APR`", "`the best rate today`")
```

"the best rate today" reaches `proposed_scenarios.md` unchecked. Note this
needs no hostile World at all: the *shipped* `generic_percent_rate` pattern
(`\b\d{1,2}\.\d{1,2}%\b`) matches on any rate page, and the surrounding
matched text is chosen by whoever controls the page, not by us. This is
strictly more likely to capture evaluative-sounding text than a literal feed
URL is — a URL has a fixed shape; a regex over prose does not.

**Required:** candidate values are third-party live content and must be
tagged as such. Either (a) add a third trust tier (`Provenance.UNTRUSTED` /
`Segment.untrusted(...)`) that **is** evaluative-checked and fails closed, or
(b) keep them out of any agent-authored document and leave them only in the
scout finding itself (which is already fenced, inert, and read as
third-party). What must not stand is the current state: live web text
wearing the WORLD provenance tag whose entire justification is seal-time
scanning. At minimum, correct the docstring — an overstated safety claim in a
provenance comment is the mechanism by which the next reviewer stops looking
(same finding shape as addendum-7's ASK on §13.11).

## BLOCK-9 — ReDoS is not mitigated, and the comment claims it is

`_load_scout_patterns` bounds pattern *length* (200), *count* (20), and
*match count* (10), and comments:

> "a short regex-length cap plus the existing `_MAX_FETCH_BYTES` cap on the
> text being matched keeps a hostile or careless pattern's blast radius small
> without needing a full regex-safety analyzer."

Measured on this checkout: the 6-character pattern `(a+)+$` against a
**40-character** input did not terminate within 120 seconds (the test process
was killed). `_MAX_FETCH_BYTES` is 512 KB — five orders of magnitude more
input. The `max_matches` cap does not help either: the break is inside the
`finditer` loop, and a catastrophic pattern hangs *before yielding its first
match*.

Neither cap bounds anything that matters. A single careless pattern in any
mounted World's sidecar hangs the agenda-watch tick indefinitely, in-process.

Aggravating: `scout-patterns.json` is **seal-exempt**. The `DISCLAIMER.md`
precedent it cites is a document a human reads; this is machine input that
compiles to executable matching whose output flows into a trusted-provenance
channel (BLOCK-8). Seal-exempt here means "not integrity-protected," so
neither the World author's intent nor `world_sha256` constrains what runs.

**Required:** one of —
1. a hard wall-clock bound on the whole `_extract_candidates` call (run it in
   a worker with a timeout; `signal.alarm` is main-thread-only and won't do
   here), or
2. a conservative structural rejector at load time (refuse any pattern with a
   quantifier applied to a group that itself contains a quantifier, refuse
   nested unbounded repetition, refuse backreferences), or
3. `regex` module with its `timeout=` argument, if a new dependency is
   acceptable.

And either way, delete the sentence claiming the current caps suffice.

## BLOCK-10 — `_load_history_lines` does not honor the F1 contract it invokes

Its docstring: *"Corrupt individual lines are dropped, never raised — the
same F1 'malformed input never crashes the tick' contract."* It validates
only that a line is **JSON-parseable**, not that it decodes to an object.
Verified on this checkout:

```
history.jsonl line: 5
_load_history_lines -> ['5', '{...}']       # '5' kept as "valid"
_latest_entries_by_key -> AttributeError: 'int' object has no attribute 'get'
```

`5`, `"x"`, `null`, `[]` are all valid JSON and all survive the filter. The
caller's blanket `except Exception: pass` means the tick doesn't crash — but
that is the wrong kind of survival: **history appending and threshold
alerting are then silently and permanently dead**, because `_append_history`
and `_safe_write_0600` are downstream of the raise in the same `try`. The
file never gets rewritten, so the poison line never ages out. One stray byte
— from an interrupted write, a shared-machine neighbour, or a partially
flushed line — permanently disables the feature with no warning anywhere.

**Required:** filter on `isinstance(json.loads(line), dict)` in
`_load_history_lines`, and log (don't `pass` silently) in the caller's
handler so a permanently-failing history path is visible.

## BLOCK-11 — `_visible_text` drops the entire page when `</head>` is omitted

`</head>` is optional in HTML5 and routinely omitted. `_TextExtractor`
increments `_skip_depth` on `<head>` and only decrements on an explicit
`</head>`, so with no closing tag the skip never ends. Verified:

```
_visible_text("<html><head><title>T</title><body>REAL RATE 7.99%</body></html>")
-> ''
```

The entire body is discarded. Consequences: the feed's text hash becomes the
hash of the empty string and is stable forever, so **the watch never fires
again** — the deal-finding feature this whole workstream exists to deliver
silently stops working on a spec-legal page. Worse, it fails toward silence,
the one failure mode a scouting system cannot self-report.

**Required:** close the `head` skip on `<body>` (and on any non-head-content
start tag), or track "in head" as a boolean that any body-level tag clears,
rather than a depth counter that only an explicit end tag decrements. Add the
`<head>`-unclosed case to `tests/test_agenda_watch.py`.

---

## Findings — verified correct (no action)

- [INFO] **`alert_breakeven_months` is genuinely wired through**, not
  validated-and-ignored. `_validate_numeric_field(data, "alert_breakeven_months")`
  runs in `_load_balances` and closes the same classes as every other numeric
  field (bool-is-int, NaN/Infinity, negative, `_MAX_REASONABLE_VALUE`), and
  the runtime `isinstance(..., (int, float)) and not isinstance(..., bool)`
  re-check is a redundant belt, not a divergent rule. The malformed case
  surfaces as "could not read", tested.
- [INFO] **`_safe_write_0600` refactor is behaviorally identical** in both
  modules. The only change is that `path` and `content` become parameters;
  `O_NOFOLLOW`, `O_TRUNC`, the mkdir, the chmod, and the False-on-symlink
  return are byte-for-byte preserved. `_write_findings`'s
  `text.rstrip() + "\n\n---\n\n" + disclaimer` moved to the caller unchanged.
- [INFO] **Retained-finding pruning never touches approved findings** under
  any ordering. `approved` is computed first, `unreviewed` is the complement,
  and only `unreviewed[:overflow]` is unlinked. An approval that lands between
  ticks moves a file out of the prune set; a de-approval moves it in and it is
  then correctly prunable. Approved findings correctly do not count against
  the cap.
- [INFO] **`threshold_crossings` is correct on the stated edge cases.** First
  tick (`prev_by_key == {}`) → `prev` is None → `prev_crossed` False →
  crossing fires once, correctly. `breakeven is None` (never breaks even) is
  excluded on both sides rather than compared. A scenario that disappears
  keeps its last history entry, so a same-keyed reappearance below threshold
  correctly does not re-alert. The alert is genuinely pointer-only — no rate,
  fee, or institution name — matching §6's convention.
- [INFO] **PKB isolation holds.** `history.jsonl` and `proposed_scenarios.md`
  are both under `lab/data/user-import/debt-finance/`, both 0600, both with
  explicit never-under-pkb tests. `agenda_watch`'s new text snapshots go to
  `DATA_DIR/agenda-watch/`, not the PKB.
- [INFO] **Workstream A holds Navy Federal to the identical standard** as
  PenFed/GreenPath: `institution_type: credit-union`, `verification_source:
  https://mapping.ncua.gov/ResearchCreditUnion`, `verified_as_of: 2026-07-31`.
  Same regulator, same shape. No term in the new corpus introduces evaluative
  or comparative language, and the `related[]` graph change is topology only.
- [INFO] **Zero domain-specific code in `agenda_watch.py`** — the
  generic-scouting standing rule is honored. All finance specificity lives in
  the World's sidecar. The driver-version-shaped test is the right proof.

## Findings — ASK

- [ASK] **`verified_as_of` on PenFed and GreenPath was bumped to 2026-07-31**
  in `d1b9db8`, whose commit message describes verifying *new* sources.
  `verified_as_of` is a load-bearing freshness input (`is_verification_fresh`)
  and a WORLD-provenance rendered field. If the two pre-existing entries were
  re-verified against NCUA/NFCC in this pass, say so in the record; if the
  date moved as a side effect of a bulk edit, it must move back. A silently
  refreshed freshness date is a small lie in the exact field designed to
  prevent one.
- [ASK] **Snapshot/finding filename collision.** `_snapshot_path` and
  `_write_finding`'s `stem` both use `_slugish(url)[:48]`. Two watched URLs on
  the same node sharing a 48-char slug prefix (common for
  `.../rates/personal-loan` vs `.../rates/personal-loan-2`) share one snapshot
  file, producing a diff of one page against another page's text. Pre-existing
  for findings; new and more consequential for snapshots. Include a short hash
  of the full URL in the stem.
- [ASK] **State-format migration is unhandled.** `entry["sha256"]` now hashes
  extracted text, not the raw body. Every existing install's stored sha is a
  raw-body sha, so the first tick after upgrade fires a spurious finding on
  every feed with no snapshot to diff against. Harmless but confusing; bump a
  version key in `agenda-watch.json` and re-baseline instead of emitting a
  false change.
- [ASK] **`except Exception: pass` in both new best-effort blocks** (history
  in Consolidation Analyzer, proposed-scenarios in Debt Advisor) swallows
  silently. Best-effort is right; silent is not — `_log.warning` at minimum.
  This is what made BLOCK-10 invisible.

## Test coverage assessment

30 new tests in Workstream C, 21 in B. Coverage on the *happy* paths is good
and the writer/reader pairing between `agenda_watch._finding_markdown` and
`_parse_candidate_values` is tested from both ends, which is the right shape.

Gaps, each corresponding to a BLOCK above:
- No test feeds a non-object JSON line to `_load_history_lines`
  (`test_corrupt_history_file_never_crashes_the_tick` uses `not valid json`
  and `{{{`, both of which the JSONDecodeError filter *does* catch — the test
  passes for the wrong reason and gives false assurance on exactly the input
  class that breaks).
- No test asserts history still appends after a corrupt line, only that the
  tick doesn't raise.
- No test for `<head>` without `</head>`.
- No test bounds `_extract_candidates`' runtime.
- `test_candidate_containing_evaluative_word_does_not_block_main_findings`
  asserts the BLOCK-8 escape as intended behavior; it needs to be inverted
  once BLOCK-8 is addressed.

## Tech debt delta vs ARCHITECTURE.md §6.6

§6.6 claims the upgrade preserves "every invariant established above
(segment/provenance guardrail, state.json hash-only convention, PKB
isolation, generic-scouting rule)." PKB isolation, the hash-only convention,
and the generic-scouting rule: confirmed true. The segment/provenance
guardrail claim is not (BLOCK-8). §6.6 must be corrected, not just the code —
this document is what the next reviewer reads first.

New debt not in §13: the seal-exempt sidecar is an unauthenticated,
unbounded-execution input channel into a trusted-provenance path. That is a
§13-worthy entry in its own right regardless of how BLOCK-8/9 are resolved.

## Required actions before merge

1. **BLOCK-8** — stop tagging live-fetched candidate values `Segment.world`.
   Add an untrusted, evaluative-checked provenance tier, or keep candidates
   out of agent-authored documents entirely. Correct the docstring's
   "isn't a new trust decision" claim and ARCHITECTURE.md §6.6's
   preserves-every-invariant claim.
2. **BLOCK-9** — bound `_extract_candidates` by wall clock or reject
   structurally dangerous patterns at load time. Delete the caps-suffice
   comment.
3. **BLOCK-10** — require `isinstance(..., dict)` in `_load_history_lines`;
   log instead of `pass` in the caller.
4. **BLOCK-11** — end the `head` skip on `<body>`/first body-level tag.
5. Add the four missing tests named above; invert
   `test_candidate_containing_evaluative_word_...` after action 1.
6. Resolve the `verified_as_of` ASK in the sprint record one way or the other.

---

# Addendum 9 — round 10 (deals / education / tracking capability upgrade)

**Date:** 2026-07-31
**Build:** `f175d29` (round-9 fixes `fb7c48c`, `ba90978`, `7c7ef91`,
`de1128d`, `cb2bd25`, `2715171`, plus the orchestrator's own `f175d29`)
**Architecture:** `sprints/2026-07-26-world-of-debt-finance/ARCHITECTURE.md`

## Verdict: BLOCK

One BLOCK (BLOCK-12), three ASKs, three INFOs. BLOCK-8 and BLOCK-10 are
confirmed fully fixed. BLOCK-9's fix is confirmed sound *after* the spawn
change, with follow-ups. BLOCK-11 is **only partially fixed** — the exact
same failure mode remains reachable through a different, equally
spec-legal HTML omission.

## 1. Re-verification of the round-9 BLOCKs

### BLOCK-8 (candidate-value trust escape) — **FIXED, correctly.**
`Provenance.SCOUTED_UNVERIFIED` (`debt_finance_compliance.py:213`) is
handled on *both* guardrail branches, not just the one that was reported:

- Evaluative check (`:411`) — `SCOUTED_UNVERIFIED` is joined with `AGENT`
  into `checkable_text`, so a candidate value is scanned exactly like
  ungrounded agent prose.
- Institutional-character check — the tier is excluded from the case-1
  trusted-verbatim branch (`:422`, which admits only `WORLD`/`OPERATOR`),
  and `_is_name_voucher` requires `WORLD`/`OPERATOR` *and* `is_name`,
  while `Segment.scouted_unverified` (`:281`) structurally cannot set
  `is_name`. A candidate value therefore can neither self-vouch nor vouch
  for a neighbour.

Call site verified: `_builtin_debt_advisor.py:399` tags each value
`Segment.scouted_unverified(v)`; only feed/checked/path metadata
(`:386`, `:388`, `:390`) remains `Segment.world(...)`, which is correct —
those are the finding's own PKB metadata, not fetched page content. The
previously-inverted test is inverted (`test_debt_finance_agents.py:305`)
and the institutional-character angle has its own coverage (`:949`,
`:962`). No residual `Segment.world(...)` on any candidate-derived text.

### BLOCK-10 (non-dict history lines) — **FIXED, correctly.**
`_load_history_lines` now requires `isinstance(parsed, dict)`
(`_builtin_consolidation_analyzer.py:515-517`), mirroring `_load_balances`'s
container-shape validation. The silent `except Exception: pass` in the tick
is now a logged warning carrying no rate, dollar figure, or institution
name — which satisfies both the BLOCK and the round-9 ASK about the
silence that hid it. Test `test_non_dict_json_history_lines_are_dropped_not_kept`
covers `5`, `"x"`, `null`, `[1, 2]` and asserts the downstream reader
survives what remains. Correct.

### BLOCK-11 (dropped body on implied `</head>`) — **PARTIALLY fixed. See BLOCK-12.**
The boolean `_in_head` with a hard reset on `<body>`/`<frameset>` does fix
the reported repro, and the three new tests pass. But the fix bounds the
implied-close rule to an allowlist of *two* tags while its own docstring
claims the general rule. See BLOCK-12.

### BLOCK-9 (ReDoS wall-clock bound) + the spawn change — **the spawn fix is sound.**
I independently confirmed the orchestrator's characterization rather than
taking it on trust:

- The subprocess (not thread) rationale holds: catastrophic backtracking
  runs inside a single C call that never releases the GIL, so `join(timeout)`
  on a thread cannot bound it. Only OS-level `terminate()`/`kill()` can.
- The fork hazard is real. `lancedb` is loaded in the portal process
  (PKB/wiki vector index) and wraps a native async runtime with its own
  worker threads; `fork()` duplicates only the calling thread, so a lock
  held by a lancedb worker at fork time is inherited held with no thread
  alive to release it. A hang *before the child ever reaches the worker*
  would defeat the very bound this code exists to provide.
- The spawn switch is correct and required no redesign, for exactly the
  stated reason: `_extract_candidates_worker` (`agenda_watch.py:356`) takes
  only picklable plain args (`str`, list of tuples, `Queue`) and recompiles
  each pattern from `regex_src` (`:370`) rather than relying on a compiled
  `re.Pattern` crossing the boundary. `regex_src` is deliberately retained
  alongside the compiled object at `:327` for this. Spawn-compatible by
  construction, as claimed.
- Measured on this checkout: `_extract_candidates_bounded` returns a
  correct result in ~0.08 s (spawn startup + `import
  arail.research.agenda_watch` measured at 0.10 s cold — comfortably
  inside the 2.0 s budget, so the added spawn cost does not eat the
  ReDoS timeout), and the `(a+)+$` repro returns `{}` in 2.006 s.
- The `__main__` re-execution hazard that spawn (unlike fork) introduces
  is **not** live on the shipped path: the only caller is
  `_builtin_librarian.py:151` inside the uvicorn process, whose `__main__`
  is the console-script wrapper, which is `if __name__ == '__main__'`-guarded
  and is re-run by `runpy` under `__mp_main__`. Same for pytest. No
  recursive-spawn risk in any shipped entry point.
- 176 tests pass across `test_agenda_watch.py`, `test_debt_finance_agents.py`,
  `test_librarian_scout.py`, `test_scouting.py`,
  `test_debt_finance_compliance.py`,
  `test_debt_finance_consolidation_arithmetic.py`.

## 2. Findings

### [BLOCK] BLOCK-12 — BLOCK-11's failure mode survives an omitted `<body>`, which is equally spec-legal

`src/arail/research/agenda_watch.py:235` —
`_HEAD_ENDING_TAGS = frozenset({"body", "frameset"})`, consumed at `:244`.

In HTML5 `<body>` is **optional in exactly the same way `</head>` is**. The
head element ends at the first start tag that is not head-content (`base`,
`basefont`, `bgsound`, `link`, `meta`, `title`, `noscript`, `script`,
`style`, `template`). The fix enumerates the *closing* signal instead of
the *head-content* set, so any page that omits both `</head>` and `<body>`
reproduces BLOCK-11 verbatim: `_in_head` is never cleared, every character
is dropped, `_visible_text` returns `""`, the stored hash becomes a stable
hash of the empty string, and **the watch never fires again** — the one
failure mode a scouting system cannot self-report, which is precisely why
BLOCK-11 was a BLOCK.

Repro (run against the current worktree):

```python
from arail.research.agenda_watch import _visible_text as v
v('<html><head><title>t</title><div>REAL RATE 7.99%</div></html>')          # -> ''
v('<html><head><title>t</title><p>REAL RATE 7.99%</p>')                      # -> ''
v('<html><head><meta charset="utf-8"><table><tr><td>APR 5.25%</td></tr></table></html>')  # -> ''
v('<html><head><title>t</title><body>REAL 7.99%</body></html>')              # -> 'REAL 7.99%'  (the fixed case)
```

The code's own docstring at `:230-234` asserts the behaviour the code does
not implement: *"treating any of them as a hard 'head is now over' signal
… covers both the common case (`<body>`) and the 'no `<head>` at all'
case"*, and `:218-220` claims *"seeing `<body>` (or any other
non-head-content start tag) can unconditionally clear it"*. The parenthetical
is the correct rule; the implementation is the two-tag subset.

**Required fix (two parts — both, not either):**

1. Invert the allowlist. Track `_HEAD_CONTENT_TAGS = frozenset({"base",
   "basefont", "bgsound", "link", "meta", "title", "noscript", "script",
   "style", "template", "head"})` and, in `handle_starttag`, clear
   `_in_head` for any tag **not** in that set. That is the actual HTML5
   rule and closes the whole class, not another instance of it.
2. Add the structural guard that makes this class of parser bug
   non-silent regardless of parser correctness. At `agenda_watch.py:680`,
   `text = _visible_text(raw_text)` is used with no sanity check. If
   `_visible_text` returns empty (or near-empty) from a substantially
   non-empty `raw_text`, that is a parser failure, not a page: log a
   warning naming the feed and fall back to `raw_text` rather than
   silently sealing an empty-string baseline that can never change again.
   Had this guard existed, BLOCK-11 would have been a logged anomaly
   rather than an invisible dead watch — and BLOCK-12 would not have
   been reachable at all.

**Required tests:** the three shapes in the repro above, plus a test that
a page whose visible text extracts to empty while `raw_text` is non-empty
produces a warning and does not seal an empty baseline.

### [ASK] ASK-13 — a spawned child that dies before `queue.put` yields `{}` with no signal at all

`src/arail/research/agenda_watch.py:456-462`. If the child exits non-zero
before writing to the queue, `proc.join()` returns, `proc.is_alive()` is
false, the timeout branch is skipped, `queue.get_nowait()` raises `Empty`,
and the broad `except` converts it to `{}` — **no log, no exception,
nothing.** `proc.exitcode` is never inspected.

Under `fork` this was close to impossible (the child was a memory copy).
Under `spawn` it is a real class: the child must `exec` `sys.executable`
and re-import `arail.research.agenda_watch` in a fresh interpreter, any of
which can fail on a machine where the import graph, the interpreter path,
or `__main__` differs from this one. I demonstrated the shape accidentally
— an unguarded caller produced `cold 0.09 {}` with a child traceback on
stderr and *zero* visibility in the return value or the log. The result is
that a permanently broken extraction path is indistinguishable from "this
page had no candidates."

Fix: after `join`, check `proc.exitcode`; if it is not `0`, log a warning
naming the feed and the exit code before returning `{}`. Cheap, and it
converts a silent permanent degradation into an operator-visible one.
(Also consider `queue.get(timeout=0.5)` instead of `get_nowait()` — the
child's `put` is flushed by a feeder thread, and `get_nowait()` immediately
after `join` has a documented spurious-`Empty` window.)

### [ASK] ASK-14 — `ctx.Queue()` / `proc.start()` can raise and abort the whole watch pass

`agenda_watch.py:436` and `:440` are called from `:688`, which sits
**outside** the `try` that begins at `:689`. A raise there propagates out
of `tick()`'s per-feed loop entirely, skipping `_save_state` at `:699`, so
every feed's `last_checked_ts` and `sha256` update from the pass is lost.

`spawn` widens this surface versus `fork`: `ctx.Queue()` needs POSIX
semaphores (`OSError: [Errno 38] Function not implemented` is a well-known
failure in restricted containers and some musl images), and `start()` must
locate and exec `sys.executable`. ARAIL is a blueprint other people run on
machines we do not control, so "this environment can't spawn" is a
scenario, not a hypothetical. Wrap the queue/process construction in a
`try` that logs and degrades to `{}` for that feed — matching the
"candidates are a best-effort annotation, never fatal" contract the
worker's own docstring already states.

### [ASK] ASK-15 — a result larger than the OS pipe buffer deadlocks the child until the timeout, and the log blames the wrong cause

Measured on this checkout: five patterns × ten matches of ~60 KB each →
`_extract_candidates_bounded` returned `EMPTY` after **2.072 s**, logging
*"did not finish within 2.0s and was killed … possible catastrophic-backtracking
pattern."* There was no backtracking. The child completed matching, then
blocked in `Queue`'s feeder thread because the parent — sitting in
`proc.join()` — never drains the pipe, so the payload exceeded the ~64 KB
buffer and the child was killed holding a correct result.

Reachable in production: `_MAX_PATTERNS`(20) × `_MAX_PATTERN_MATCHES`(10)
= 200 matches with **no per-match length cap**, over text bounded only by
`_MAX_FETCH_BYTES` (512 KB). A World-authored pattern as ordinary as
`[^<]+` or `.+` in the seal-exempt `scout-patterns.json` sidecar hits it.
Not introduced by the spawn change (fork had the same pipe), but it is
unreviewed and it actively misdiagnoses itself in the log, which is worse
than failing plainly.

Fix: cap each match and the total payload in `_extract_candidates_worker`
before `queue.put` (a candidate value is a short literal by design — a
few hundred characters is generous), and distinguish "killed on timeout"
from "child produced nothing" in the log message.

### [INFO] INFO-16 — the start-method fallback is now unreachable, and fails in the wrong direction

`agenda_watch.py:426`. `spawn` is available on every platform CPython
supports, so `"spawn" not in mp.get_all_start_methods()` is dead code
(the old `fork` check was genuinely reachable on native Windows). Harmless
to leave, but note it degrades to running the match **unprotected** —
failing *open* on a ReDoS bound for a feature the module itself calls a
best-effort annotation. Returning `{}` would be the right direction. If
the branch is kept, say in the comment that it is defensive and expected
to be unreachable, so a future reader does not assume it is tested.

### [INFO] INFO-17 — docstring overstates the implementation

`agenda_watch.py:218-220` and `:230-234` describe the general HTML5
implied-close rule; the code implements a two-tag subset. Fixing BLOCK-12
per part 1 above makes the docstring true. Do not fix the docstring
instead of the code.

### [INFO] INFO-18 — this worktree's editable install resolves to the *other* checkout

`.venv/lib/python3.11/site-packages/__editable__.arail-1.0.0.pth` points at
`/Users/netsushi/ProJects/qukaizen-arail/src`, not at this worktree, so a
bare `pytest` here imports and tests the **main checkout**, silently. All
numbers in this addendum were produced with
`PYTHONPATH=<worktree>/src`. Any prior round's pass counts collected
without that override should be treated as unverified. Worth a `conftest.py`
`sys.path` pin or a note in the sprint record.

## 3. Test coverage assessment

176 passing across the six relevant suites with the path override. Coverage
of the round-9 BLOCKs is genuine (each has a test that fails without its
fix), with one caveat: `test_catastrophic_pattern_is_bounded_by_wall_clock_not_left_to_hang`
asserts `result == {}`, which is also what a *systematically broken*
subprocess returns — it cannot by itself distinguish "bounded" from
"never worked." `test_extract_candidates_bounded_returns_result_of_fast_pattern`
covers that gap, so the pair is adequate; keep them together and say so.

Gaps, all named above: BLOCK-12's three HTML shapes, the empty-visible-text
guard, non-zero child exitcode (ASK-13), oversized payload (ASK-15).

## 4. Tech debt delta

No new debt beyond the findings above. The `SCOUTED_UNVERIFIED` tier is a
net *reduction* — it replaces an implicit trust assumption with an explicit,
type-level one, and ARCHITECTURE.md §6.6 was updated with it. The spawn
switch trades tens of milliseconds of child startup for the removal of a
whole class of unreproducible native-runtime hangs; the right trade, and
the measurement above confirms the cost does not encroach on the timeout
budget.

## Required actions before merge

1. **BLOCK-12** — invert `_HEAD_ENDING_TAGS` into a head-content allowlist
   so any non-head-content start tag ends the head, **and** add the
   empty-visible-text guard at `agenda_watch.py:680`. Both parts. Tests for
   the three repro shapes plus the guard.
2. **INFO-17** — correct the `_TextExtractor` docstring once the code
   implements what it already claims.
3. **ASK-13** — check `proc.exitcode` and log a non-zero child exit.
4. **ASK-14** — wrap `ctx.Queue()` / `proc.start()` so a spawn failure
   degrades that feed instead of aborting the pass before `_save_state`.
5. **ASK-15** — cap per-match and total payload size in the worker; stop
   the timeout log from misattributing a pipe-blocked child to
   catastrophic backtracking.
6. **INFO-16 / INFO-18** — comment the unreachable fallback; pin or
   document the worktree test path.

Actions 3–5 may ship as a follow-up ticket if the orchestrator prefers, in
which case the verdict on the remainder is WEAK_PASS. Action 1 may not:
it is the same finding as BLOCK-11, at the same severity, still open.

---

# Addendum 10 — Round 11 review (2026-07-31)

**Build:** `b87a408` ("fix(agenda-watch): close BLOCK-12 …")
**Scope:** verification of the BLOCK-12 fix and the three round-10 ASKs, plus a
fresh sweep of Workstreams A/B/C.

## Verdict: WEAK_PASS

BLOCK-12 is genuinely closed — verified by running the current code, not by
reading the diff. No BLOCK findings remain. Four ASKs below are follow-up
material, none of them reachable from the World as shipped.

## 1. BLOCK-12 — FIXED, and fixed at the right level

`agenda_watch.py:238-241` now enumerates head *content*
(`head,title,base,link,meta,style,script,noscript,template`) and
`:250-251` clears `_in_head` on any start tag outside that set while in
head. Verified against the exact repro and five neighbouring shapes:

| input | result |
|---|---|
| `<html><head><title>t</title><div>A</div></html>` | `'A'` |
| `<html><head><title>t</title></head><p>C<meta name=x>D</p>` | `'CD'` |
| `<head><meta charset=x><title>t</title></head><body>B</body>` | `'B'` |
| `<html><body><meta name=y>F</body>` | `'F'` |
| `plain text` | `'plain text'` |

The edge I specifically probed — a `<meta>` appearing *after* the head has
already been implicitly closed — correctly stays closed: the guard is
`if self._in_head and …`, and only a literal `<head>` start tag can set
`_in_head` back to true. Head content is still stripped; the closed class
is closed, not another instance of it. INFO-17 (docstring overstating the
code) resolves with it: the docstring now describes what the code does.

## 2. ASKs 13/14/15 — two closed, one half-closed

- **ASK-14 (spawn-start failure aborts the pass)** — closed.
  `:444-456` wraps `get_context`/`Queue`/`Process`/`start` and degrades to
  `{}` for that feed, so `_save_state` still runs.
- **ASK-13 (silent non-zero child exit)** — closed. `:496-499` logs the
  exit code. The `(0, None)` tuple is right: `None` is the not-yet-reaped
  case, and a `0` exit with no payload is caught by the `result is None`
  branch above it.
- **ASK-15** — the *misattribution* half is closed; the *payload cap* half
  is not. See ASK-20.

**The queue-then-join reordering is sound, and does not introduce a new
hang.** `mp.Queue.get(timeout=…)` does not observe child liveness, so a
child that dies before ever calling `put()` does not hang the parent — it
raises `Empty` at the deadline and falls into the `result is None` branch.
Worst-case wall clock is unchanged in shape: `_EXTRACT_TIMEOUT_SEC` (2.0 s)
plus at most 3 × 1.0 s of reap grace. No path leaves the queue unclosed and
no path leaves the child unreaped.

## 3. New tests — they exercise what they claim

- `test_visible_text_survives_omitted_head_close_and_body_tag` is the
  verbatim BLOCK-12 repro (`<html><head><title>t</title><div>REAL RATE
  7.99%</div></html>`) and fails on the pre-fix parser.
- `test_large_but_fast_result_is_not_mistaken_for_a_hang` builds
  5 × 10 × 3000 chars ≈ 150 KB — comfortably past the ~64 KB pipe buffer —
  and asserts correctness, un-truncated match lengths, **and**
  `elapsed < _EXTRACT_TIMEOUT_SEC`. Pre-fix this returned `{}` at ~2.07 s,
  so the assertion is load-bearing, not decorative.

265 tests pass across the twelve debt-finance / agenda-watch / scouting /
librarian / world-forge-seal suites with `PYTHONPATH` pinned to this
worktree (INFO-18 still applies — a bare `pytest` here tests the *other*
checkout).

## 4. Findings

### [ASK] ASK-19 — candidate values are interpolated into the review file without the fencing the excerpt gets
`agenda_watch.py:562` — `", ".join(f"`{v}`" for v in values)`. The excerpt
immediately above is deliberately fenced (`:550`, "untrusted web content
headed for a human review queue — fence it so it renders as inert text"),
but a candidate value gets only a single-backtick inline wrap and no
length cap. A matched substring containing a backtick or a newline escapes
that wrap and can inject markdown — including a forged authoritative line
like `# Verified rate: 0.00% APR` — into the file a human approves from,
which is precisely the trust boundary `SCOUTED_UNVERIFIED` exists to
protect. **Not reachable with the shipped World**: both patterns in
`scripts/worlds_src/debt-finance/scout-patterns.json` are tightly numeric
(`\b\d{1,2}\.\d{2}%\s*APR\b`), and the sidecar is operator-authored. Fix
is two lines: strip backticks/newlines and truncate each value.

### [ASK] ASK-20 — ASK-15's payload cap is still open
No per-match or total cap before `queue.put` (`:380`). Bounded overall by
`_MAX_FETCH_BYTES`, so a pattern like `[^<]+` over 20 labels can still put
low-single-digit MB through the pipe and inline all of it into the finding.
The reordering removed the *misdiagnosis*; it did not remove the size.
Same one-line worker-side fix serves ASK-19 and ASK-20.

### [ASK] ASK-21 — a valid result is discarded if the child is slow to exit
`:473-487`. If `queue.get` succeeded but `proc.join(1.0)` leaves the child
alive, the code terminates and returns `{}`, logging "did not finish within
2.0 s and was killed … possible catastrophic-backtracking pattern" — a
misleading message on a run that actually produced a correct answer. Very
low probability (the worker exits right after `put`), but the fix is to
return `result` when it is not `None`, and reserve the backtracking wording
for `result is None`.

### [INFO] INFO-22 — `handle_startendtag` is a `pass`, so a self-closing non-void tag cannot end the head
`:257-258`. `<head><title>t</title><div/>E</html>` still extracts `''`
(verified). Malformed-in-the-wild only, and it now trips the new
empty-extraction warning rather than dying silently. Routing
`handle_startendtag` to the same `_in_head` reset would close it.

### [INFO] INFO-23 — BLOCK-12 part 2 shipped as warn-only, not warn-and-fall-back
`:715-728` logs when a non-empty fetch extracts to nothing but still seals
the empty-string hash; round 10 asked for a fallback to `raw_text`. I
accept the deviation — falling back to raw HTML would make every ad/nonce
token a "change" and flood the review queue — but it is a deliberate
divergence from the required action and is recorded here as such. The
warning is what converts the failure mode from invisible to operable,
which was the point.

### [INFO] INFO-16 / INFO-18 — unchanged from round 10
The unreachable `"spawn" not in get_all_start_methods()` fallback still
fails open and still carries no "expected unreachable" note; the worktree
editable-install path is still unpinned.

## 5. Sweep across Workstreams A/B/C
No new findings beyond the above. The seal is byte-identical
(`world_sha256` `7a12152…b5564075`), confirming these changes are
runtime-only and touch no sealed World artifact. The consolidation
arithmetic, agent-seed, compliance, isolation and reveal-slot suites are
unchanged from round 10 and still green.

## Required actions before merge
None. ASK-19/20/21 and INFO-16/18/22 should be filed as a single
follow-up ticket ("agenda-watch scout hardening: cap and fence candidate
values, tighten the extraction-timeout log, pin the worktree test path")
and referenced from `sprints/BACKLOG.md`.
