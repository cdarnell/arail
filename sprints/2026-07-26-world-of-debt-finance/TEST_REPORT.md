# Test report: World of Debt Finance

**Date:** 2026-07-27
**Build:** [BUILD_LOG.md](./BUILD_LOG.md) at `eb296cd`
**Review:** [REVIEW.md](./REVIEW.md) — WEAK_PASS after 6 rounds
**New tests:** `tests/test_debt_finance_qa_adversarial.py` (37 tests, 31 failing)
**Verdict (round 1):** **FAIL**
**Verdict (round 2, after `2d5513f`/`63d818d`/`393fcc7`/`e3c0e9a`): FAIL — see
[Round 2](#round-2--re-verification-after-the-builder-fixes) at the bottom of
this file.** F1/F2/F3 are genuinely closed, but the F3 fix opened a new escape
of the same family (F10, BLOCK).

Three BLOCK-severity findings. Two of them are the seventh and eighth
escape routes in the same guardrail the architect closed six times, and the
first one is a straightforward violation of an explicitly-written spec
clause (§6.1) that also permanently kills the agent's async loop while
`.status` keeps reporting `"running"`.

The data-isolation property that was the *original* BLOCK (§0.1) was
re-verified end-to-end under current code with real-shaped staged data and
**holds**. That is the good news.

---

## Test inventory

| # | Test | Category | Covers | Status |
|---|---|---|---|---|
| 1–6 | `test_bad_field_value_warns_and_does_not_crash_the_tick[*]` | edge / agent-quality | §6.1 "the tick does not crash" for 6 malformed *value* classes | **FAIL** |
| 7–12 | `test_bad_field_value_never_echoes_content_into_the_activity_stream[*]` | security | §6.1 "no file content or parsed fragment echoed" | **FAIL** (blocked by the crash) |
| 13 | `test_a_single_malformed_value_does_not_kill_the_agent_loop` | concurrency / agent-quality | exception escaping `tick()` escapes `_run()`'s `while True` | **FAIL** |
| 14 | `test_negative_balances_and_aprs_do_not_produce_a_nonsense_finding` | edge | negative money/APR not in the §6.1 schema, unvalidated | **FAIL** |
| 15 | `test_short_operator_name_does_not_universally_satisfy_the_institutional_branch` | **security** | `_names_match` has no minimum-length floor | **FAIL** |
| 16 | `test_whitespace_only_operator_name_does_not_satisfy_the_pairing_rule` | **security** | `institution: " "` survives the truthiness filter | **FAIL** |
| 17 | `test_allowed_names_match_on_word_boundaries_not_bare_substrings` | **security** | "Ally" vetting "Alliance Credit Union" | **FAIL** |
| 18 | `test_operator_typed_lowercase_institution_is_not_falsely_blocked` | agent-quality | `_PROPER_NOUN_RE` requires an ASCII capital initial | **FAIL** |
| 19 | `test_operator_typed_name_with_trailing_whitespace_is_not_falsely_blocked` | agent-quality | documented "whitespace-normalized" matching is `.lower()` only | **FAIL** |
| 20 | `test_non_ascii_initial_institution_name_is_not_falsely_blocked` | edge / i18n | `[A-Z]` is ASCII-only | **FAIL** |
| 21–27 | `test_evaluative_regex_covers_ordinary_advice_vocabulary[*]` | agent-quality | `_EVALUATIVE_RE` vs. the vocabulary a small instruct model actually emits | **FAIL** |
| 28 | `test_empty_disclaimer_file_refuses_to_write` | security | §7.1 precondition, empty-file edge | PASS |
| 29 | `test_disclaimer_deleted_between_read_and_write_still_writes_the_text_it_read` | security / TOCTOU | race between precondition and write | PASS |
| 30 | `test_no_operator_figure_or_institution_reaches_the_pkb_tree` | **security** | the original §0.1 BLOCK, re-verified under current code | PASS |
| 31 | `test_state_json_holds_only_hash_timestamp_and_count` | **security** | §7 state-content constraint, key-set exactness | PASS |
| 32 | `test_activity_pointer_does_not_leak_an_absolute_home_path` | security | §6 "short, non-identifying pointer" | **FAIL** |
| 33 | `test_deleting_the_findings_file_causes_it_to_be_regenerated` | regression / agent-quality | §6.5's documented deletion story vs. the no-op hash | **FAIL** |
| 34 | `test_findings_refresh_when_the_mounted_world_changes` | agent-quality | fingerprint omits World/disclaimer inputs | **FAIL** |
| 35 | `test_advisor_refreshes_when_the_approved_finding_set_churns` | agent-quality | fingerprint uses approved *count*, not identity | **FAIL** |
| 36 | `test_findings_write_does_not_follow_a_pre_placed_symlink` | **security** | `write_text` symlink-follow on a documented shared machine | **FAIL** |
| 37 | `test_findings_content_is_never_world_readable_even_transiently` | security | final mode 0600 on an inherited 0644 file | PASS |

Plus: all 118 pre-existing sprint tests (`test_debt_finance_*`,
`test_world_forge_debt_finance_seal`) still pass.

---

## Failures

| # | Finding | Severity |
|---|---|---|
| F1 | Malformed *value* in `balances.json` raises out of `tick()` and permanently kills the agent loop | **BLOCK** |
| F2 | `_names_match` has no length floor / word boundary — a 1-char operator institution name defeats the institutional-character guardrail document-wide | **BLOCK** |
| F3 | The guardrail permanently blocks the single most ordinary real input: an operator who types their own institution name in lowercase | **BLOCK** |
| F4 | `_EVALUATIVE_RE` misses ordinary advice vocabulary (`recommend`, `optimal`, `cheapest`, …) | MEDIUM |
| F5 | `_write_findings` follows a pre-placed symlink (arbitrary-file overwrite + chmod on a shared machine) | MEDIUM |
| F6 | No-op fingerprint incomplete on both agents (disclaimer edits, World changes, approved-finding churn, deleted findings all invisible) | MEDIUM |
| F7 | Activity stream carries the absolute findings path (contains the OS username on a real install) | LOW |
| F8 | Negative balances / APRs accepted and rendered verbatim | LOW |
| F9 | `_load_terms` doesn't type-check term entries — same loop-death path as F1, via the World bundle | LOW |

### F1 — [BLOCK] a malformed field *value* crashes the tick and kills the loop

ARCHITECTURE.md §6.1 is unusually explicit: *"File present but fails to
parse or fails schema validation → the tick does **not** crash … It emits
one non-specific activity-stream note … and skips the tick."*

`_load_balances` validates **container shapes only** — that the document is
a dict, that `debts`/`candidate_scenarios` are lists, that their entries are
dicts. It never touches field *types*. Every numeric read downstream is a
bare `float(d.get("balance", 0.0))`, and `breakeven_months` ends in
`math.ceil`.

Minimal repro (each of these raises out of `tick()`):

```json
{"debts":[{"institution":"X","balance":"1,200.00","apr":19.99}]}   ValueError
{"debts":[{"institution":"X","balance":1200,"apr":"19.99%"}]}      ValueError
{"debts":[{"institution":"X","balance":null,"apr":19.99}]}         TypeError
{"debts":[{"institution":"X","balance":NaN,"apr":19.99}], ...}     ValueError (math.ceil of NaN)
{"debts":[{"institution":"X","balance":Infinity,...}], ...}        ValueError
{"debts":[{"institution":"X","balance":1e308,"apr":1e308}], ...}   ValueError
```

Note that `NaN` and `Infinity` are accepted by `json.loads` by default, so
they survive the parse step cleanly. `"1,200.00"` and `"19.99%"` are not
adversarial inputs — they are what a human hand-authoring a JSON file from a
statement types.

The consequence is worse than a skipped tick. `_run` is:

```python
while True:
    await asyncio.sleep(interval)
    self.tick()
```

inside a `try` that catches only `CancelledError`. Verified by driving the
real loop (test 13):

```
status: running   task done: True
task exception: TypeError("float() argument must be a string or a number, not 'NoneType'")
```

The agent is dead for the rest of the process lifetime, `.status` reports
`"running"`, and **nothing is emitted to the activity stream** — the
operator's only feedback channel. A user who mistypes one balance silently
loses the agent. The module docstring's claim "Never crashes; always logs a
path-only pointer or a non-identifying warning" is false.

Fix shape: a guarded `_as_finite_float` that raises `_MalformedInput`
(rejecting NaN/inf via `math.isfinite`), applied at parse time in
`_load_balances` rather than at use time; plus a defensive
`try/except Exception` around `self.tick()` in both agents' `_run`, so no
future field can convert an input bug into permanent agent death.

### F2 — [BLOCK] the seventh escape route: `_names_match` has no length floor

This is the same defect class as ASK-C, on the branch it was never applied
to. In addendum 4 the architect added `_MIN_QUOTED_SPAN_LEN = 5` to the
**evaluative** branch, on exactly this reasoning: a short, common string used
as a global substring operation blanks/matches things it has nothing to do
with. The **institutional** branch's matcher —

```python
def _names_match(candidate_lower, vetted_lower):
    return vetted_lower in candidate_lower
```

— is unanchored substring containment with no minimum length and no word
boundary, and `operator_names` is built from raw operator input with no
normalization beyond `.lower()`.

Minimal repro:

```python
text = ("- **A** (as you entered it) — PenFed Credit Union member loan "
        "(as entered), rate 5.00%.")

check_guardrail(text, frozenset(), operator_names=frozenset({"mybank"}))
# -> ok=False   (control: correctly blocked)

check_guardrail(text, frozenset(), operator_names=frozenset({"a"}))
# -> ok=True    (guardrail defeated)
```

Reachable through the product: an operator with a debt entry
`{"institution": "A", ...}` (an abbreviation, a placeholder, a typo) makes
`"a"` a member of `operator_names`, and `"a"` is a substring of essentially
every candidate proper noun in the document. Every institutional-character
claim anywhere in the findings file then passes — including one carried in a
*different* scenario's `product`/`source` field naming an entity the
operator never typed and the World never verified. `institution: " "` does
the same thing (it is truthy, survives the `if s.get("institution")`
filter, and is a substring of every multi-word proper noun).

The non-degenerate case matters too: `"ally"` (a real 4-character lender)
vets `"Alliance Credit Union"`, because containment is unanchored.

Fix shape: apply the same floor the other branch already has, plus require a
word-boundary-anchored match rather than bare containment, plus
`.strip()`/collapse-whitespace normalization when building `operator_names`.

### F3 — [BLOCK] the guardrail permanently blocks lowercase-typed institution names

The over-restrictive direction, which nobody in six rounds probed. The
trigger regex `_INSTITUTIONAL_CHARACTER_RE` is `re.I`; the candidate-name
regex `_PROPER_NOUN_RE = \b[A-Z][\w&'.-]*...` requires an **ASCII capital
initial**. So the trigger fires on lowercase text but no candidate name is
ever extracted from it.

Minimal repro — a completely ordinary `balances.json`:

```json
{"debts":[{"institution":"navy federal credit union","balance":8000,"apr":21.5}],
 "candidate_scenarios":[{"institution":"navy federal credit union",
   "product":"loan","rate":9.5,"fee_pct":0.0,
   "source":"operator","as_of":"2026-07-27"}]}
```

Result: guardrail blocks, no findings file is ever written, and the emitted
hint says *"an institutional-character claim … must be paired with an
institution name you typed yourself or one this World has verified"* — which
the operator did. There is no rephrasing that fixes it except discovering,
undocumented, that they must capitalize.

BLOCK-5 was raised for precisely this shape of harm ("the guardrail
permanently blocked the single most likely real input to this agent: a plain
credit-union consolidation offer"). This reintroduces it through a different
mechanism. Two adjacent variants fail the same way:

- `"Éole Credit Union"` — `[A-Z]` is ASCII-only, so an accented initial is
  never a candidate. Any non-Latin-script institution name is worse.
- `operator_names` containing `"penfed credit union "` (trailing space from
  a hand-edited file) never matches, because `_PROPER_NOUN_RE` candidates
  are word-boundary-trimmed. `check_guardrail`'s own docstring and the task
  framing both describe this matching as whitespace-normalized; it is not.

Fix shape: make `_PROPER_NOUN_RE` case-insensitive-tolerant (or match
allowed names against the raw chunk window directly, case-folded, on word
boundaries), use `str.casefold()` rather than `.lower()`, and normalize
whitespace on both sides.

### F4 — [MEDIUM] the evaluative check works against the words already tested

`_EVALUATIVE_RE` is seven alternations: `best|guaranteed|top[- ]pick|top
choice|lowest|you should|you must`. All of the following pass:

```
"We recommend this option."
"This is the optimal choice for you."
"The cheapest path is consolidation."
"The smartest move is to transfer the balance."
"You'd be better off consolidating."
"This one is a no-brainer."
"Our advice is to consolidate."
```

§5.4 states ranking a product for a specific person is "a line this product
must not cross regardless of what a user asks for," and §7.2 promotes that
from persona instruction to a code check. The check is the only thing
standing between `_framing_prose`'s model output and a compliance-relevant
document. `recommend` and `advice` are, given the CROA framing in §7.4, the
two most consequential words in the language for this feature, and neither
is listed. Documented as a heuristic (§13.2) — but this gap is not at the
adversarial-phrasing margin, it's the centre of the distribution for a small
instruct model told to summarize a debt comparison.

### F5 — [MEDIUM] `_write_findings` follows a pre-placed symlink

`Path.write_text` writes *through* a symlink, and the subsequent
`os.chmod(path, 0600)` retargets the victim file's mode. On the
shared-machine convention this workspace explicitly documents (multiple
macOS accounts on one box), a local user who can create
`lab/data/user-import/debt-finance/findings/consolidation_analyzer.md`
first gets an arbitrary-file-overwrite-plus-chmod primitive running as the
operator, with the operator's financial figures as the payload. Verified:
the victim file's contents are replaced.

Fix shape: `os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC |
os.O_NOFOLLOW, 0o600)`. This also closes the transient-permissions window
(currently the file is created with the process umask and chmod'd
afterwards).

### F6 — [MEDIUM] the no-op fingerprint doesn't cover everything that changes the output

- **Consolidation Analyzer**: fingerprint is `sha256(balances.json)` alone.
  The disclaimer text and the vetted-institution set both come from the
  mounted World, both appear in the output, and neither is hashed. Editing
  `compliance/DISCLAIMER.md` — the file the whole §7.1 mechanism is built
  around — never propagates to an existing findings file.
- **Debt Advisor**: fingerprint is `(terms hash, approved finding *count*)`.
  Approving one finding while un-approving another leaves the count
  identical, so the cited feed/date metadata silently goes stale in a
  document whose entire value proposition is verifiable provenance.
- **Both**: neither checks whether the findings file still exists. §6.5
  documents deletion as the v1 forget story ("the operator can delete the
  files directly"). Doing so permanently suppresses regeneration until the
  *input* changes.

### F7 — [LOW] absolute path in the activity stream

Both agents emit `f"… see {_findings_file()}"`, an absolute path. §6 says
the activity stream carries "a short, non-identifying pointer to the
findings file." On a real install `DATA_DIR` resolves under the repo/lab
root, which on the documented shared-machine setup sits under a home
directory containing the operator's OS username — and `activity.jsonl` is
rendered on the dashboard. This repo already carries a dedicated regression
test for this class (`test_bench_ai_eng_no_hostname_leak.py`). Emit a
lab-relative path.

### F8 — [LOW] negative money accepted

`{"balance": -500, "apr": -19.99}` produces a findings document containing
`rate -5.00%` and negative "monthly savings". Not in the §6.1 schema, not
validated, silently rendered as a real result.

### F9 — [LOW] `_load_terms` doesn't type-check entries

`_load_terms` guards `OSError`/`JSONDecodeError` and then does
`list(doc.get("terms"))` with no per-entry check. A hand-edited
`terms.json` with a non-dict entry raises `AttributeError: 'str' object has
no attribute 'get'` out of Debt Advisor's `tick()` — same permanent
loop-death path as F1, sourced from the World bundle rather than operator
input.

---

## Security review

| Surface | What I actually checked | Findings |
|---|---|---|
| Data isolation (the original §0.1 BLOCK) | Staged real-shaped data (two named issuers, `12345.67`/`4321.00` balances, `24.99`/`19.24` APRs, a PenFed balance-transfer scenario), ran **both** agents' full `tick()`, then content-scanned every file under the PKB root via `rglob` for each of the six secrets. Zero hits. Separately confirmed both `state.json` files' key sets are *exactly* `{input_hash, last_run_at}` and `{terms_hash, approved_finding_count, last_run_at}` — no numeric or institution content, and no room for drift because the assertion is on the key set, not on absence of a specific string. | **Clean.** Holds under current code, not just as of the fix commit. |
| User input (`balances.json`) | Container-shape validation exists; **field-type/finiteness validation does not**. `json.loads` accepts `NaN`/`Infinity` by default. Six crashing payloads (F1). Negative values unvalidated (F8). Unicode institution names parse fine but break name matching (F3). | **F1 BLOCK, F8 LOW** |
| Guardrail bypass (institutional branch) | Read `_names_match` directly rather than trusting the 118 passing tests. Unanchored containment, no length floor, no word boundary, `.lower()`-only normalization. Confirmed a 1-char and a whitespace-only operator name each defeat the check document-wide, with a working control case. | **F2 BLOCK** |
| Guardrail bypass (evaluative branch) | Probed the `quoted_spans` global-`replace` masking for cross-field swallowing: to exploit it an operator-controlled span would have to occur verbatim inside a fixed template string containing an evaluative word — I enumerated both agents' template literals and none contain a `_EVALUATIVE_RE` match, so the ASK-C residue is not currently exploitable. The `<5`-char floor likewise cannot cause a false block for real short lender names (`SoFi`, `Ally`, `USAA`, `PNC`, `BECU`) because none contain an evaluative substring. Coverage of the regex itself is the real gap. | **F4 MEDIUM**; masking itself clean |
| Disclaimer precondition | Empty file → refuses (phrase absent). Phrase-altered → refuses. Deleted between `read_disclaimer` and `_write_findings` → the already-read text is what's appended, so no findings file can exist without the disclaimer. Negation constructions ("we are NOT not licensed financial advisors") do pass, but the file is World-sealed operator content and the check is a tamper-detector, not a semantic classifier — not filed as a finding. | Clean |
| File I/O | `write_text` follows symlinks; `chmod` after write, not at create. Fixed path components (no traversal surface — nothing operator-controlled reaches the path). `lab/data/user-import/` confirmed present in `.gitignore` (line 16). Final mode verified `0600` even when inheriting a pre-existing `0644` file. | **F5 MEDIUM** |
| Network I/O | Neither agent performs any network I/O; `_approved_findings` reads only already-approved local files, and the only figure-bearing path (`scouting` excerpts) is deliberately never parsed for numbers. | Clean |
| Deserialization | `json.loads` only, no `pickle`, no `yaml.load`. Untrusted-input surface is `balances.json` (operator-authored) and the sealed World bundle. | Clean apart from F1/F9 |
| Crypto | Only `hashlib.sha256` over file bytes, used as a change-detection fingerprint, not as a security primitive. No secrets, no comparison of secrets, no IV/nonce surface. `input_hash` is a sha256 over the whole balances document and lands in a PKB-indexed `state.json` — a theoretical confirmation oracle against a *known-exact* file, which is not a meaningful threat here. Noted, not filed. | Clean |
| Info leakage in logs | Malformed-input warning echoes no content (verified by asserting the staged figures never appear in any emitted message — this assertion currently fails only because F1 crashes before the warning is reached). Success pointer leaks an absolute path. | **F7 LOW** |
| Dependencies | None added by this sprint. | Clean |

---

## Performance

N/A. Neither agent is on a hot path (default tick interval 86400 s, floor
60 s), and no benchmark-relevant code changed.

---

## Regression

Full suite run on `eb296cd` and on the pre-sprint parent `9c51502`,
same interpreter, same ordering (`-p no:randomly`), failure sets diffed:

```
after:  106 failed, 3478 passed, 3 skipped, 1 xfailed, 14 errors
before: 101 failed, 3328 passed, 3 skipped, 1 xfailed, 14 errors

new failures not attributable to tests/test_debt_finance_qa_adversarial.py:
  (none)
```

**Zero regressions.** The ~101 shared failures are pre-existing and
environment-dependent (they need untracked runtime state such as
`lab/worlds/photography`, which does not exist in this worktree); the
`test_build_tab.py` failures trace to `c1162cb`, confirmed a pre-sprint
ancestor. The Worlds surface specifically was re-run
(`test_world_mount`, `test_world_loader`, `test_world_skill_mount`,
`test_world_kb`, `test_world_switcher`, `test_default_worlds_catalog`,
`test_world_qa_probes`, `test_world_verify_shipped`) — the shared
`loader.py`/`builtin_seed.py`/`skill_seed.py` changes did not disturb the
existing Worlds.

All 118 existing debt-finance tests pass.

---

## Coverage delta

Not measured numerically (this repo has no coverage gate). Qualitatively:
before this pass, `debt_finance_compliance.check_guardrail` had no test for
short/degenerate allowed names, no test for case or script variation in
institution names, and no test asserting the evaluative regex against
vocabulary outside its own alternation list; `_load_balances` had no test
for field *values*, only for container shapes; neither agent's async `_run`
loop was exercised at all. 37 tests added, covering all of those.

---

## Notes for the next QA pass

- **The bug class this codebase produces is "the check is correct for the
  strings someone thought to type."** Six review rounds and 118 tests
  hardened one branch of `check_guardrail` while the *matcher* both branches
  share kept a length-floor gap that the same architect had already
  identified and fixed on the other branch three commits earlier. When a fix
  introduces a defensive constant, immediately ask which other call site has
  the same shape and didn't get one.
- **Nobody probed the over-restrictive direction.** Five of six BLOCKs were
  "the guardrail lets something through." F3 is "the guardrail blocks the
  most ordinary possible input," and it was sitting in plain sight in a
  one-character regex class (`[A-Z]`). Every future guardrail sprint here
  should carry a mandatory false-positive test tier.
- **§13.11's deferred segment-based provenance refactor is still the right
  call**, and this pass did *not* find a live exploit in the global-replace
  masking — but that's only because neither agent's fixed template text
  currently contains an evaluative word. That's a property of today's
  strings, not of the design. Any new template line is a chance to
  reintroduce it; add a test asserting no template literal matches
  `_EVALUATIVE_RE`.
- **`tick()` is called from an unguarded `while True`.** That pattern is
  copied from Buddy. Worth checking whether Buddy, SRE, and Researcher have
  the same permanent-death-on-one-exception property; if so it's a
  cross-agent finding, not a debt-finance one.
- **Under-tested and not covered here:** `find_mounted_bundle_dir` behavior
  when a *different* World is mounted mid-tick; two ticks genuinely
  concurrent (both agents share no state, but both write into the same
  `findings/` directory and `mkdir(parents=True, exist_ok=True)` races were
  not exercised); the seal-time `knowledge_sources[]` ordering check from
  §3.2.

---
---

# Round 2 — re-verification after the builder fixes

**Date:** 2026-07-27
**Commits reviewed:** `2d5513f` (my round-1 tests) · `63d818d` (F2/F3/F4) ·
`393fcc7` (F1/F5–F9) · `e3c0e9a` (BUILD_LOG)
**New tests:** 6 added to `tests/test_debt_finance_qa_adversarial.py` (43 total)
**Verdict:** **FAIL** — one new BLOCK (F10), introduced by the F3 fix.

I re-ran my own adversarial file rather than trusting the report, read the
diffs in all four commits line by line, and probed specifically for the
"one level deeper" pattern that took the architect six rounds to close on
this same guardrail. That pattern is present again.

## What is genuinely closed

| Round-1 finding | Status | How I verified |
|---|---|---|
| F1 [BLOCK] malformed value crashes tick + kills loop | **Closed** | All 6 malformed-value classes pass; `_validate_numeric_field` rejects non-numeric / `bool` / non-finite / negative / `>1e12`; both agents' `_run` now wrap `self.tick()` in `except Exception` with `CancelledError` re-raised first — read the diff, the ordering is correct. |
| F2 [BLOCK] no length floor / unanchored containment in `_names_match` | **Closed for the reported repro** | 1-char and whitespace-only allowed names no longer match (`_MIN_ALLOWED_NAME_LEN`, casefold, `\b` anchoring). "ally" no longer matches inside "alliance". **But see F10** — the defect *class* is not closed, it moved. |
| F3 [BLOCK] lowercase/accented operator names permanently over-blocked | **Closed** | `sofi is a credit union…` and `éole is a credit union…` now pass with the corresponding `operator_names` entry. |
| F4 [MEDIUM] evaluative vocabulary gaps | **Fixed** | recommend/advice/advis*/optimal/cheapest/smartest/"better off"/"no-brainer" added. Builder correctly chose to rephrase its own template line rather than narrow the new vocabulary — the right direction. |
| F5 [MEDIUM] symlink-followed findings write | **Fixed** | `os.O_WRONLY\|O_CREAT\|O_TRUNC\|O_NOFOLLOW` at create time, not an `islink()` pre-check (no TOCTOU), in **both** agents; callers check the `False` return and skip the success emit. Residual LOW: only the final path component is `O_NOFOLLOW`-protected, and a pre-existing attacker-owned *regular* file (or hard link) at that path is still truncated into. Not new, not worth blocking on for a fixed, non-operator-controlled path under `lab/data/`. |
| F6 [MEDIUM] no-op fingerprint gaps | **Fixed** | Analyzer hashes (balances, disclaimer text, vetted names) + findings-file-exists; Advisor hashes approved-finding *identity* rather than a bare count. Covers all four gaps I named. |
| F7/F8/F9 [LOW] | **Fixed** | `_relative_pointer()` in both modules; negatives folded into `_validate_numeric_field`; `_load_terms` filters to dict entries. |

**Credit where due:** the builder disclosed a self-inflicted regression it
caught during the F3 work (an early case-insensitive approach reintroduced
the BLOCK-1 tautology), and disclosed that it could not run a full-repo
before/after diff in its sandbox. Both disclosures are accurate and both are
the behavior I want. The problem below is not a disclosure failure — it is
that the guard the builder added against that self-inflicted regression is
one level too shallow.

## New failures

| # | Test | Symptom | Minimal repro | Severity |
|---|---|---|---|---|
| F10 | `test_allowed_name_that_is_a_word_of_the_trigger_phrase_does_not_self_vet` (+4 siblings) | An allowed name that is a *word of* the trigger phrase — or any ≥3-char common word in the proximity window — vets every institutional-character claim in the document. **Regression:** these inputs were correctly blocked before `63d818d`. | below | **BLOCK** |
| F11 | `test_capitalized_trigger_phrase_does_not_self_vet_via_candidate_path` | BLOCK-1's tautology still fires on the *primary* candidate path when the trigger phrase appears capitalized in the text. Pre-existing, not a regression — but it shows the new tautology guard was added to only one of the two paths. | below | MEDIUM |

### F10 — [BLOCK] the F3 window-fallback reintroduces BLOCK-1 at word granularity

The F3 fix matches an allowed name against the **raw proximity window**
instead of against an extracted proper-noun candidate. The window
necessarily contains the trigger phrase's own text and the ordinary English
prose around it, so the fallback admits matches the candidate path
structurally could not. The tautology guard added alongside it excludes only
an allowed name whose *whole normalized form is identical* to the trigger's
matched text. It does not exclude an allowed name that is a single **word
of** that text.

```python
from arail.agents.debt_finance_compliance import check_guardrail
F = frozenset

check_guardrail("Payday Express is a credit union.", F(), F({"Union"})).ok
# -> True   (guardrail defeated; "union" is found inside the trigger itself)
# pre-63d818d: False  (correctly blocked)

check_guardrail("Payday Express is a credit union.", F(), F({"Credit"})).ok
# -> True

check_guardrail("Payday Express is the credit union.", F(), F({"the"})).ok
# -> True   ("the" clears _MIN_ALLOWED_NAME_LEN=3 and is in every window)
# pre-63d818d: False

check_guardrail("Payday Express is a credit union.", F(), F({"is a"})).ok
# -> True   (not a name at all — an arbitrary prose fragment)
```

Blast radius is document-wide, exactly as in F2: one such entry in
`operator_names` (or `vetted_institutions`) suppresses the guardrail for
every claim in the output, verified with a two-claim text. Reachability is
the same operator-typed `balances.json` path F2 used — `union`, `credit`,
`loan`, `bank`, `trust`, `first` are all plausible short operator-typed
account labels, and `union`/`credit` are additionally *inside the trigger
phrase*, which makes them a pure tautology rather than a coincidence.

The root cause is structural, and matches the note I filed in round 1: the
length floor is a *magnitude* defense against what is a *provenance*
problem. `_MIN_ALLOWED_NAME_LEN = 3` stops `"x"` and stops `" "`; it cannot
stop `"the"`. Two properties the fallback needs and doesn't have:

1. The matched span must not **overlap** the trigger phrase's own matched
   text — not merely "not be identical to it". (`match.span()` is already in
   hand at the call site; a span-overlap test is a two-line change.)
2. The fallback should match against the window with the trigger occurrence
   **excised**, or require the match to look like a name (e.g. not a member
   of a stopword set, or ≥2 tokens, or bounded by non-prose context) —
   otherwise "matched a common English word in prose" and "matched the
   operator's institution name" remain indistinguishable.

I am not prescribing the fix; both notes are for the builder's judgment.
What must hold is that all 6 new tests pass **and** the existing 155 keep
passing — in particular the round-1 BLOCK-1 control
(`"Payday Express is a credit union"` with an unvetted set) and the F3
lowercase-`sofi` case, which pull in opposite directions and are where the
builder's first attempt went wrong.

### F11 — [MEDIUM] the tautology guard covers only one of the two match paths

```python
check_guardrail("Payday Express is a Credit Union.", F({"credit union"})).ok
# -> True   (also True before 63d818d — pre-existing, not a regression)
```

`_PROPER_NOUN_RE` extracts `"Credit Union"` as a candidate, which matches a
generic vetted entry exactly. Whether this is live depends on `terms.json`
never carrying a generic `institution_type` entry — which is the invariant
the architect's BLOCK-1 closure rests on, so the guardrail is currently
relying on data hygiene for a property it claims to enforce in code. The
same `match.span()`-overlap defense that fixes F10 fixes this too, which is
why I am filing it here rather than deferring it.

Related and lower: a vetted entry that is a generic *superset* of the
trigger (`"federal credit union"`) also vets an unrelated institution
(`"Payday Express is a federal credit union."` → `ok=True`). Same root
cause, same fix.

## Regression

Full suite at HEAD, same interpreter (`PYTHONPATH=src`, repo venv):

```
47 failed, 3545 passed, 2 skipped, 1 xfailed, 7 errors  (661 s)
```

None of the 47 failures or 7 errors are in a debt-finance module. They are
in `test_build_tab`, `test_aerollm_*`, `test_world_forge_api`,
`test_r1_r3_chat_models`, and peers — the same environment-dependent,
untracked-runtime-state set documented in round 1's regression section.
**No regression attributable to `63d818d`/`393fcc7`.**

Debt-finance selection: **155 passed** before my 6 new tests; **155 + 37
passed / 6 failed** after. The 6 failures are F10/F11 only.

## Security review (round 2, delta only)

| Surface | What I actually checked | Findings |
|---|---|---|
| Guardrail bypass (institutional branch) | Read the new `_names_match` and the F3 fallback rather than trusting the 155 green tests; enumerated 16 probes against the fallback (sub-word-of-trigger, generic superset of trigger, stopwords at the length floor, multi-word prose fragments, regex metacharacters in the allowed name, zero-width joiners, embedded newlines, plural/hyphen forms, whitespace/case normalization of both sides), and diffed each result against the pre-fix implementation to separate regressions from pre-existing behavior. | **F10 BLOCK, F11 MEDIUM.** Regex metacharacters are correctly `re.escape`d; zero-width and newline variants correctly fail closed; the length floor and `\b` anchoring do what they claim. |
| Loop liveness (F1) | Read both `_run` bodies: `except asyncio.CancelledError: raise` precedes `except Exception`, so cancellation still terminates. Residual LOW, not filed as a finding: if `_host.emit` itself raises inside the handler the loop still dies — narrow, and `emit` is a local append. | Clean |
| File I/O (F5) | `O_NOFOLLOW` at create in both modules, no `islink()` pre-check, callers branch on the `False` return. Residual noted in the table above (pre-existing regular-file/hard-link at the target path). | Clean, LOW residual |
| Info leakage (F7) | `_relative_pointer` falls back to `path.name` on `ValueError`, so no absolute path escapes on either branch; checked every interpolation site in both modules. | Clean |
| Data isolation (§0.1) | Not re-run; the round-1 end-to-end scan holds and none of these four commits touch the state-file key sets. | Unchanged |

## Notes for the next QA pass

- **The F10 pattern is round 1's note coming true verbatim.** I wrote:
  "when a fix introduces a defensive constant, immediately ask which other
  call site has the same shape." The F3 fix introduced a defensive
  *identity* check and did not ask which weaker relation (overlap,
  containment, sub-word) the same tautology survives under. Identity
  guards on a matching predicate are almost always one level too shallow.
- **The two directions are still fighting each other.** Every fix that
  widens matching to close a false *block* (F3) reopens a false *pass*
  (F10), and vice versa. This guardrail has now had 8 escapes and 1
  over-block across 7 rounds. The next fix should come with the two
  control cases pinned in the same test (unvetted-blocks, lowercase-real-
  name-passes) so the pull is visible in one place.
- Still not covered: concurrent ticks racing on `findings/`,
  `find_mounted_bundle_dir` changing mid-tick, §3.2 seal-time
  `knowledge_sources[]` ordering.

---

# Round 3 — final confirmation pass

**Date:** 2026-07-27
**Build:** `d4c19e4` (branch `qukaizen/modern-finance-world-plan-a34437`), tree clean
**Baseline for regression:** `9c51502` (main)
**Verdict:** **WEAK_PASS**

Invoked after the architect's round-8 terminal WEAK_PASS ("ship it, do not
schedule a round 9"). Scope was five explicit questions; all five are
answered below. Four came back clean. The fifth (regression) came back
clean, and a **new, adjacent finding (F12) surfaced while verifying the
trust boundary that the round-7/8 work leans on** — the authoring-time half
of the guardrail, which no round of this review has actually exercised.

## Test inventory

| # | Test | Category | Covers | Status |
|---|---|---|---|---|
| R3-1 | `test_future_dated_verification_is_treated_as_fresh` | edge | `is_verification_fresh` negative timedelta | PASS (documents F13) |
| R3-2 | `test_verification_exactly_at_boundary` | edge | 365/366-day boundary | PASS |
| R3-3 | `test_degenerate_name_segment_still_vouches` | edge | `""`, `"   "`, `"\n"`, `"-"`, `"0"` as `is_name` voucher | PASS (documents F14) |
| R3-4 | `test_trigger_split_across_two_agent_segments_is_not_detected` | edge | per-segment `finditer` vs. docstring's "full concatenation" | PASS (documented precondition) |
| R3-5 | `test_residual_shape_2_unreachable_agent_trigger_next_to_name` | security | ARCH §13.10 residual shape 2, both agents, benign + adversarial data | PASS |
| R3-6 | `test_no_trigger_ever_spans_a_segment_boundary_in_real_templates` | security | proves R3-4's precondition holds in real templates | PASS |
| R3-7 | `test_no_agent_segment_is_operator_or_world_derived` | security | untrusted text never lands in an AGENT segment | PASS |
| R3-8 | `test_evaluative_phrase_split_across_agent_segments_is_not_detected` | edge | `" ".join` fusion/splitting | PASS (unreachable) |
| R3-9 | `test_unicode_homoglyph_name_still_only_vouches_by_tag` | security | homoglyph name cannot fake vetting | PASS |
| R3-10 | `test_no_user_figure_or_institution_reaches_the_pkb_tree` | security | **original BLOCK**, fresh end-to-end | PASS |
| R3-11 | `test_state_json_for_both_agents_holds_only_a_hash_and_a_timestamp` | security | both `state.json` files, opaque-digest assertion | PASS |
| R3-12 | `test_findings_land_outside_the_pkb_tree_and_do_contain_the_figures` | happy | positive control for R3-10 | PASS |
| R3-13 | `test_activity_events_never_carry_a_figure_or_institution_name` | security | F7 regression, activity stream | PASS |
| R3-14 | `test_forge_evaluative_vocabulary_matches_the_runtime_guardrail` | security | seal-time/runtime vocabulary parity | **FAIL → F12a** |
| R3-15 | `test_preflight_scans_the_fields_that_actually_become_world_segments` | security | preflight field coverage (4 params) | **FAIL → F12b** |
| R3-16 | `test_evaluative_world_name_reaches_the_rendered_findings_document` | security | end-to-end consequence of F12 | PASS (demonstrates the escape) |

Plus: the full 163-test debt-finance suite, a 218-test Worlds/agent-loader
subset, and the whole 3602-test repo suite.

## Answers to the five questions asked

**1. Can the `is_name` mechanism itself be broken?**
No, not by content. `is_name` is a constructor-set boolean, so no string —
homoglyph, casing, whitespace, unicode — can change it (R3-9). Two
*degenerate* weaknesses exist but are unreachable (F13, F14 below).

**2. Are the §13.10 residual shapes actually unreachable through real code
paths?** Yes — verified against the real `_build_output` of both agents (not
hand-built `Segment` lists), under both benign and deliberately hostile
World/operator data, by capturing the real segment list via a recording
`check_guardrail` (R3-5). In both templates the only AGENT segments adjacent
to an `is_name=True` voucher are the static literals `"- **"` and
`"** ("` / `"** (as you entered it) — "`, none of which can carry a trigger.
Cross-line vouching is additionally blocked because every line is separated
by an AGENT `"\n"` segment. R3-6 separately proves no trigger phrase ever
spans a segment boundary in either real template, which is the documented
precondition for `check_guardrail`'s per-segment `finditer`.

**3. Round-1/round-2 adversarial suite re-run at HEAD?** Yes.
`tests/test_debt_finance_qa_adversarial.py` 42/42, full debt-finance suite
163/163. F1–F11 all remain closed.

**4. Original data-isolation constraint, re-verified fresh?** Yes, and it
holds. Driving both agents' real `tick()` end-to-end with distinctive
markers, the *only* files written under `lab/pkb/` are the two
`agents/<id>/state.json`, and neither contains any balance, APR,
institution, product, or source string. Every `state.json` value is either a
64-char hex digest or a float timestamp — including
`approved_finding_count`, which is stored as a **sha256 of the count**, not
the count. Activity-stream messages carry only the relative pointer
`user-import/debt-finance/findings/<agent>.md`. A positive control confirms
the figures genuinely *are* written — to `lab/data/`, outside the PKB walk —
so R3-10 cannot pass trivially. The seeded `lab/pkb/agents/*/AGENT.md` files
contain only prose about the rule, no figures.

**5. Regressions in shared Worlds/agent-loader paths?** None. A 218-test
Worlds/forge/mount/scout/loader subset is fully green. The full repo suite
shows 47 failures across 8 files — every one of them reproduced identically
on baseline `9c51502` (main), with environmental signatures (blocked egress
to `huggingface.co`, absent local `lab/worlds/photography` runtime state,
process/shell probes). Main's failure set is a strict superset of the
branch's. **Zero regressions attributable to this sprint.** `horticulture`,
`physics` and `video-games` all mount and scout correctly
(`test_default_worlds_catalog.py`, `test_world_mount.py` green).

## Failures

### F12 — [MEDIUM] the seal-time preflight does not back the trust boundary the runtime exemption is documented to rest on

`debt_finance_compliance.py`'s module docstring makes an explicit, load-bearing
claim about why WORLD segments may skip the evaluative check:

> a World's own authoring-time content (including its `terms.json`
> institution entries) is expected to pass the preflight evaluative-language
> scan in `scripts/forge_debt_finance_world.py` before it is ever sealed —
> [...] that seal-time check is what actually keeps evaluative language out
> of WORLD segments today. If that preflight check is ever removed,
> **weakened**, or bypassed for a reseal, this runtime exemption stops being
> backed by anything and this section must be revisited.

ARCHITECTURE §13.11 records this as "confirmed present as of this fix".
Presence was confirmed; **coverage was not**. It is weakened in two
independent ways.

**F12a — the vocabulary has already silently drifted.**
`forge_debt_finance_world.py:63` keeps a hand-maintained copy of the runtime
regex, with a comment asserting the discipline: *"kept as an
independently-maintained copy [...] so a change to one is a deliberate edit
to both, not a silent shared dependency."* That discipline has already
failed once, with no test to catch it. Runtime has 16 alternations; the
forge copy has 7. Missing from the forge:

```
recommend(ed|ation|s)?   advice   advis(e[sd]?|able)
optimal   cheapest   smartest   better off   no-brainer
```

`recommend`/`recommendation` were added to the runtime regex deliberately
(documented at `tests/test_debt_finance_agents.py:146`) and never propagated.

**F12b — the preflight scans fields that no agent renders, and skips every field that does.**
Preflight scans `short`, `definition`, `example`. Neither agent's
`_build_output` renders any of those three. The four term fields that
actually become `Segment.world(...)` in Debt Advisor are **`term`**
(→ `v.name`, the `is_name=True` segment), **`institution_type`**,
**`verification_source`**, and **`verified_as_of`** — none are scanned.

**Minimal repro (F12b + end-to-end consequence):**

```python
terms = [{"term": "Best Rate Credit Union", "category": "institutions",
          "institution_type": "credit-union",
          "verification_source": "https://mapping.ncua.gov/x",
          "verified_as_of": "2026-07-27"}]

# seal time: passes, no 'language:' problem reported
[p for p in forge.preflight(spec, terms, face) if p.startswith("language:")]
# -> []

# run time: WORLD segments are evaluative-exempt by construction
body = _builtin_debt_advisor._build_output(Path("/unused"), terms, [])
# -> "- **Best Rate Credit Union** (credit union, verification source: ...)"
```

The evaluative phrase lands verbatim in the findings document, under the
heading *"Institutions whose character claims this World verified"*, with no
"as the World states it" marker — a gap the module docstring itself already
flags ("a reader cannot tell WORLD voice from AGENT voice on the page").
This is exactly the outcome §7.2's guardrail exists to prevent, reachable by
exactly the actor the seal-time check was designed against.

**Why MEDIUM and not BLOCK.** Mounting a World is an explicit, documented
trust act; the shipped `examples/worlds/debt-finance` bundle is first-party
and clean; a hostile World's blast radius here is marketing prose in a local
markdown file, not data exfiltration or code execution. Runtime behaviour is
unchanged from all 8 review rounds — this is not a late regression. The
serious half is that the **documentation asserts a protection that does not
exist**, and a future reviewer would reasonably rely on it.

**Note for the builder — this is a design trade, not a typo.** Naively
scanning `term` would false-block legitimate institution names ("Best Buy
Credit Union" is a real institution). The fix should be a deliberate
decision — widen coverage to `institution_type`/`verification_source`/
`verified_as_of` (where evaluative language is never legitimate), decide
`term` explicitly, add a vocabulary-parity test, and correct the docstring's
claim to match whatever ships.

### F13 — [LOW] future-dated `verified_as_of` is treated as fresh forever

`is_verification_fresh` computes `(today - parsed).days <= 365`. A
far-future date yields a large negative value, which satisfies `<= 365`.

```python
is_verification_fresh("2999-01-01", today=date(2026, 7, 27))  # -> True
```

The check is documented to "degrade closed"; on this input it degrades open,
and permanently. Unreachable in the shipped World (`verified_as_of` is
`2026-07-27` throughout) and only settable by a World author, who is already
trusted for the vetted set. Suggested fix: `0 <= (today - parsed).days <= 365`.

### F14 — [LOW] a degenerate `is_name` segment still vouches

`_is_name_voucher` checks only `provenance is not AGENT and is_name`. It
does not require the segment to be non-empty, so an empty or whitespace-only
name vouches for an adjacent AGENT institutional-character claim:

```python
check_guardrail([Segment.agent("This is a credit union offering "),
                 Segment.operator("", is_name=True),
                 Segment.agent(" rates.")]).ok    # -> True
```

Unreachable today: it requires an AGENT segment carrying a trigger to be
adjacent to a name voucher, which R3-5 proves neither template produces. It
is the same *shape* as §13.10's tripwire and should be closed with it. Fix
is one clause: `and s.text.strip()`.

## Security review

| Surface | What I actually checked | Findings |
|---|---|---|
| Provenance/`is_name` tagging | That `is_name=True` is set at exactly 2 sites (`v.name`, `r.institution`), defaults `False`, and cannot be influenced by text content — verified via captured real segment lists under hostile input | Clean; F14 (degenerate value, unreachable) |
| Untrusted-input containment | That no operator- or World-supplied string ever lands in an AGENT segment — asserted with marker strings against both real `_build_output`s | Clean |
| Guardrail bypass | Trigger-splitting across segments, evaluative-phrase splitting, homoglyph/unicode names, casing | All unreachable in real templates (R3-6 proves the precondition) |
| Data isolation (`lab/pkb/`) | Walked the entire PKB tree after both real `tick()`s; only 2 `state.json` written; asserted every value is a hex digest or float; positive control that figures land in `lab/data/` | Clean |
| Activity stream | Serialized every emitted event, asserted no balance/APR/institution/product/source marker; F7 relative-pointer fix still in place | Clean |
| Seal-time preflight (authoring-time trust boundary) | Ran the real `preflight()` against the 4 term fields that actually render as WORLD segments; diffed the forge's evaluative vocabulary against the runtime's alternation-by-alternation | **F12a, F12b** |
| Staleness clock | Boundary (365/366) and future-dated input | F13 |
| Deserialization | `terms.json`/`balances.json` parsed with `json` only; non-dict entries filtered in both agents (F9 symmetry fix verified present) | Clean |
| Crypto | Only sha256 as an opacity/fingerprint device (`state.json` digests, no-op fingerprint). No secrets, no key material, no comparison of secrets — constant-time compare not applicable | Clean |
| File I/O | F5 symlink fix still present in `_write_findings`; findings paths derived from the host's data dir, never operator-controlled | Clean |

## Performance

N/A. Not a hot path; both agents are tick-driven over a handful of JSON
entries. No benchmark warranted.

## Regression

Full repo suite: 3553 passed / 47 failed / 2 skipped / 1 xfailed / 7 errors.
All 47 failures reproduce identically on baseline `9c51502` and are
environmental. Debt-finance: 163/163. Worlds/agent-loader subset: 218/218.

## Verdict

**WEAK_PASS.** Every question this round was convened to answer came back
clean: the `is_name` mechanism holds against adversarial input, the §13.10
residual shapes are genuinely unreachable through real code paths, the
round-1/2 findings stay closed, the original data-isolation BLOCK survives
intact with a positive control, and there are zero regressions.

F12 is real and reproducible but does not block: it is an authoring-time
gap with a low-impact blast radius, unchanged across all 8 rounds, in a
World the project ships clean. It is filed as a follow-up rather than a
return-to-builder because the honest summary of this feature's runtime
guardrail is: **it is done.**

## Notes for the next QA pass

- **The pattern across all three of my rounds and the architect's eight:
  the mechanism gets fixed, the prose overclaims what the fix covers.**
  §13.11's "no adjacency math", §13.10's residual shapes, and now the
  docstring's preflight claim are three instances. Read every load-bearing
  prose claim as an untested assertion and go run it.
- **The authoring-time half of this feature has never been adversarially
  tested.** Eight rounds went into `check_guardrail`; `preflight()` got one
  presence check. F12 was sitting in the first place nobody looked.
- Duplicated-regex-with-a-comment-promising-discipline is a recurring
  antipattern here. Any such pair needs a parity test at birth.
- Both `_framing_prose` functions are the only non-static AGENT text. If a
  future template ever interpolates a dynamic value into an AGENT segment,
  or splits AGENT prose around a WORLD/OPERATOR value, R3-5/R3-6/R3-7 are
  the tests that will catch it — they belong in the repo, not my scratchpad.

---

# QA round 12 — post-review gate on the capability upgrade (2026-07-31)

**Date:** 2026-07-31
**Build:** [BUILD_LOG.md](./BUILD_LOG.md) at `e6a4cdc`
**Reviewed against:** [REVIEW.md](./REVIEW.md) addendum 10 (round 11, WEAK_PASS)
**New tests:** `tests/test_debt_finance_qa_round12.py` (60 passing, 6 xfail)
**Verdict: FAIL** — 4 tests in this sprint's own new code fail in the
canonical `pytest tests` invocation and pass in isolation. Everything the
round-11 review asserted about the trust boundary, PKB isolation, activity
honesty and the seal re-verified clean.

## How this run was invoked

Per INFO-18, every run used
`PYTHONPATH="$(pwd)/src:/Users/netsushi/ProJects/qukaizen-dac"` with
`.venv/bin/python3 -m pytest`. A pre-sprint baseline was taken by adding a
worktree at `73f02d9` and running the identical full suite there, so
"pre-existing" is a measurement, not an assumption.

| run | result |
|---|---|
| base `73f02d9`, full suite | 55 failed, 3867 passed, 7 errors |
| branch `e6a4cdc`, full suite | 60 failed, 3978 passed, 7 errors |
| branch, `tests/test_agenda_watch.py` alone | 29 passed |
| branch, new QA round-12 file alone | 60 passed, 6 xfailed |

Set-differencing the two failure lists: **the only new failures attributable
to this sprint's files are the four `tests/test_agenda_watch.py` ones below.**
The other ~55 (aerollm defaults, model-UX, dashboard, world-forge, swarm,
shell-source-safety, reset-scope) are present identically at `73f02d9` and
are unrelated to this sprint. Three `tests/test_cli_*` driver failures differ
in granularity between the two runs but sit in files this sprint does not
touch (`git diff --stat 73f02d9..HEAD -- src scripts tests` is 11 files, all
debt-finance/agenda-watch); treating them as machine noise.

## Test inventory

| # | Test | Category | Covers | Status |
|---|---|---|---|---|
| 1 | `test_proposed_scenarios_write_refuses_a_pre_placed_symlink` | security | new Workstream-C write path vs F5 invariant | PASS |
| 2 | `test_history_jsonl_write_refuses_a_pre_placed_symlink` | security | new Workstream-C write path vs F5 invariant | PASS |
| 3 | `test_symlinked_directory_component_is_still_refused` | security | O_NOFOLLOW's known parent-dir limit, pinned | PASS |
| 4 | `test_snapshot_write_refuses_a_pre_placed_tmp_symlink` | security | QA-1 | XFAIL |
| 5 | `test_state_write_refuses_a_pre_placed_tmp_symlink` | security | QA-1 | XFAIL |
| 6 | `test_finding_write_refuses_a_pre_placed_symlink` | security | QA-1 | XFAIL |
| 7 | `test_shipped_world_feed_slugs_are_currently_distinct` | regression | guards the sealed agenda against a future colliding feed | PASS |
| 8 | `test_shipped_feed_urls_are_at_the_truncation_boundary` | edge | documents the zero margin | PASS |
| 9–10 | `test_two_long_sibling_urls_do_not_share_a_{snapshot,finding_stem}` | edge | QA-2 | XFAIL |
| 11 | `test_snapshot_collision_shows_the_wrong_feeds_text_in_a_diff` | edge | QA-2's user-visible consequence | PASS |
| 12 | `test_backtick_and_newline_in_a_candidate_escape_the_inline_wrap` | security | ASK-19, confirmed empirically | PASS |
| 13 | `test_the_agent_side_parser_does_not_propagate_the_injected_line` | security | ASK-19 blast radius is bounded at the agent reader | PASS |
| 14 | `test_excerpt_fence_breakout_is_neutralised` | security | the excerpt fence still holds | PASS |
| 15 | `test_enormous_candidate_value_is_rendered_unbounded` | edge | ASK-20 witness | PASS |
| 16–22 | `TestScoutedUnverifiedIsNeverPromoted` (7) | security | provenance tier cannot be spoofed or vouched | PASS |
| 23–26 | `TestPkbIsolationOfEveryNewFile` / state+activity honesty | security/regression | §0.1 BLOCK across every new artifact | PASS |
| 27–31 | threshold-crossing boundary/None/no-refire | edge | Workstream C arithmetic edges | PASS |
| 32–48 | malformed `history.jsonl` (9 shapes) + `scout-patterns.json` (10 shapes) | edge | new read paths never raise | PASS |
| 49–52 | `TestSpawnDependsOnParentProcessState` | concurrency/failure-injection | QA-3 | PASS (see failures) |
| 53–61 | `TestVisibleTextBoundaries` (9) | edge | comments, entities, nesting, unclosed script, binary | PASS (1 XFAIL = INFO-22) |

## Failures

| # | Test | Symptom | Minimal repro | Severity |
|---|---|---|---|---|
| QA-3 | `test_candidate_values_extracted_and_rendered`, `test_works_identically_for_a_non_finance_pattern`, `test_extract_candidates_bounded_returns_result_of_fast_pattern`, `test_large_but_fast_result_is_not_mistaken_for_a_hang` | All 4 fail under `pytest tests`; all 4 pass under `pytest tests/test_agenda_watch.py`. Candidate extraction returns `{}`. | see below | **HIGH** |

### QA-3 — candidate extraction is silently disabled by parent-process state, and the log blames the wrong thing

`_extract_candidates_bounded` uses `mp.get_context("spawn")`. `spawn`
re-derives the child from the **parent's** cwd, `sys.path`, and `__main__`
module, and pays a full interpreter+import startup out of the same 2.0 s
`_EXTRACT_TIMEOUT_SEC` budget that is supposed to bound *matching*. Rounds
9–11 verified the child's behaviour thoroughly and the start-method choice
correctly; nobody tested what the parent's state does to it.

Deterministic repro (no test-suite state needed):

```python
import os, re, tempfile
from arail.research import agenda_watch as aw
pats = [{"label": "n", "regex": re.compile(r"\d+"), "regex_src": r"\d+", "max_matches": 5}]
d = tempfile.mkdtemp(); os.chdir(d); os.rmdir(d)
aw._extract_candidates_bounded("x 12", pats, "u")   # -> {}   (should be {'n': ['12']})
```

Two further measurements:

- **Startup already eats a third of the budget.** From a plain script with
  `lancedb` imported (i.e. roughly the portal's process shape), a trivial
  `\d+` match over a 15-character string costs **0.60–0.61 s** wall clock,
  every call. The docstring's estimate is "tens of ms". The remaining margin
  before a *correct* run is reported as a ReDoS kill is ~1.4 s, on a laptop
  that is also expected to be running local inference.
- **The child re-executes the parent's `__main__`.** With an unguarded entry
  script, `spawn`'s `_fixup_main_from_path` re-runs the launcher's top-level
  code inside the extraction child, once per feed per tick. The shipped
  launcher is safe — `scripts/start.sh` runs the `uvicorn` console script,
  which is `if __name__ == "__main__":`-guarded — but this is an undocumented
  constraint on every future entry point, and nothing tests it.

Why this is HIGH rather than an ASK: when the spawn fails or the budget is
exhausted, the tick **returns `ok: True`** and stages the finding *without*
candidate values, and the operator-facing log line says "did not finish
within 2.0s and was killed — possible catastrophic-backtracking pattern in
the mounted World's scout-patterns.json". A World author reading that will
go rewrite a regex that was never the problem. This is the same
silently-dead-capability family the sprint blocked on twice already
(BLOCK-11, BLOCK-12), one layer up: the watch still fires, but the
deals-finding half of the capability is off and the diagnostic misdirects.

**Suggested fix shape (builder's call):** separate the two budgets — an
explicit startup deadline (child ready) and a matching deadline — and only
emit the backtracking wording when matching, not startup, timed out;
consider a persistent worker or a `concurrent.futures` pool so startup is
paid once per process rather than once per feed per tick; and emit the
"candidates unavailable" fact into the tick's return dict so it is
observable, not log-only. ASK-21's fix (return `result` when it is not
`None`) belongs in the same change.

**Not yet isolated:** which specific earlier test module leaves the process
in the state that trips this. It does not reproduce from `tests/portal +
tests/test_a*.py` (615 tests), from any single `tests/test_a*.py` module
paired with `test_agenda_watch.py`, or under 10 spinning CPU hogs — it needs
the full ~4000-test session. A `pytest -x` bisect over the full ordering is
the next step and is the builder's to run.

## Findings filed, not failing

### QA-1 (MEDIUM) — `agenda_watch.py`'s writes follow symlinks; the agents' do not

This sprint's own F5 fix established `_safe_write_0600` (`O_NOFOLLOW`,
0600) as the write discipline for this feature, and both agents honour it
on all four of their files, including the two new ones
(`proposed_scenarios.md`, `history.jsonl` — tests 1–2 above confirm).
`agenda_watch.py` uses bare `Path.write_text` on all three of its
destinations, and a pre-placed symlink at the `.tmp` path is written
*through*:

| path | new this sprint? | symlink honoured? |
|---|---|---|
| `DATA_DIR/agenda-watch/<world>-<node>-<url>.txt` (+`.tmp`) | **yes** (Workstream B) | no — writes through |
| `DATA_DIR/agenda-watch.json` (+`.tmp`) | no | no — writes through |
| `PKB/sources/scout/<stem>-<sha8>.md` | no | no — writes through |

Verified by execution, not reading: an attacker-placed
`agenda-watch/<name>.tmp -> victim` results in `victim` containing
attacker-influenced fetched page text. Requires local write access into the
lab's own data dir, which is why it is MEDIUM and not HIGH — but that is
exactly the threat model F5 was fixed under, and ARAIL's stated posture is
"it runs on other people's machines". The inconsistency is the finding: two
files in the same feature disagree about whether this matters.

**Fix shape:** lift `_safe_write_0600` into a shared helper (or copy it a
third time, matching the existing per-module duplication convention) and
use it for the snapshot, state, and finding writes. Note the `.tmp`
sidecar needs the same treatment as the final path — the current
`tmp.write_text(...); tmp.replace(path)` pattern makes `.tmp` the
attack surface, not `path`.

### QA-2 (MEDIUM) — 48-character slug truncation collides two feeds onto one snapshot and one finding stem

`_slugish()` truncates to 48 characters. `_snapshot_path` and
`_write_finding`'s `stem` are both built from `f"{world}-{node_slug}-{url_slug}"`,
so two feeds under the same watch node whose URLs share a 48-character
normalised prefix become **the same snapshot file and the same finding
filename family**, while `state["feeds"]` remains correctly keyed by full
URL. Consequences, in order of severity:

1. Feed A diffs against feed B's snapshot, so a finding **attributed to
   feed A renders feed B's content as A's "change"** — a false attribution
   in the human review queue, in a feature whose entire premise is
   "quoted verbatim, provenance-tagged".
2. `_write_finding`'s unreviewed-pruning globs `f"{stem}-*.md"`, so feed
   A's pending finding can be pruned as feed B's overflow.
3. Every tick shows a spurious change, because each feed keeps overwriting
   the other's snapshot.

**The shipped World has zero margin.** Two of its three feed URLs already
produce a 48-character (i.e. truncated) slug:
`https-creditcards-chase-com-balance-transfer-cre` and
`https-www-navyfederal-org-loans-cards-personal-l`. Adding any sibling URL
under either path — the obvious next step for a "deals-finding" World, and
exactly what Workstream A's expansion of `knowledge_sources` was about —
collides. Test 7 above is a regression guard on the sealed bundle so this
fails loudly rather than silently mis-attributing.

**Fix shape:** append a short hash of the full URL to the slug
(`f"{slug}-{sha256(url)[:8]}"`), the same trick `_write_finding` already
uses for the content sha. This changes existing snapshot filenames once,
which costs one baseline re-take per feed and no findings.

### QA-4 (LOW, disagreement) — ASK-19's "not reachable" argument is a configuration argument, not a structural one

I reproduced ASK-19 exactly as filed: a candidate value containing a
backtick and a newline breaks out of the single-backtick wrap and renders
`# Verified rate: 0.00% APR — approved by ARAIL` as a real markdown heading
inside the file a human approves from (test 12). The backlog entry justifies
non-blocking with "needs an operator-authored loose pattern (not any of the
shipped ones) to reach."

I accept the ship decision and disagree with the reasoning. `agenda_watch.py`
is explicitly and deliberately World-generic, and
`debt_finance_compliance.py`'s own module docstring states the threat model
plainly: "a World bundle is third-party-authorable and mountable". A
`scout-patterns.json` sidecar is a World artifact, not an operator artifact,
and the module documents it as "semi-trusted, seal-exempt input… not
integrity-protected the way the rest of a sealed bundle is". So the
protection today is "the one World we happen to ship has tight patterns" —
which is a property of the current configuration, not of the code.

What keeps it LOW, and what I verified rather than assumed: the blast radius
really is confined to the finding document. Debt Advisor's reader
(`_CANDIDATE_LINE_RE` is line-anchored, `_BACKTICK_VALUE_RE` is
`` `[^`]*` ``) cannot return a value containing a backtick or a newline, so
an injected line **cannot** travel into `proposed_scenarios.md` (test 13).
The deception stops at the human review queue. That is still the wrong place
for it to stop — that queue *is* the trust boundary `SCOUTED_UNVERIFIED`
exists to protect — but it is not a path to a forged number in an agent
document.

Recommendation: fold the two-line fix into whatever change addresses QA-3,
since it touches the same function, and restate the backlog rationale as
"blast radius is bounded at the review document" rather than "the shipped
patterns are tight".

### On the other three backlog items — I agree with the non-blocking calls

- **ASK-20 (no payload cap):** agreed, low. Confirmed unbounded (test 15,
  a 100 KB candidate renders in full) but bounded above by
  `_MAX_FETCH_BYTES`; it is a document-bloat and I/O concern, not a trust
  one. Same fix site as QA-4.
- **ASK-21 (slow child, valid result discarded):** agreed as filed, and it
  should be fixed as part of QA-3 — QA-3 makes the misleading
  backtracking log line a routine occurrence rather than a rare one, which
  raises ASK-21's cost.
- **INFO-23 (warn-only, no raw_text fallback):** agreed, and I'd go further:
  falling back to `raw_text` would be a regression, and the record in the
  backlog is the right artifact. The one thing missing is that the warning
  is log-only — nothing surfaces it in `status`, the activity stream, or
  the tick's return dict, so "loud" is only loud to someone reading logs.
  Same observability gap as QA-3's; worth fixing once, together.

## Security review

| Surface | What I actually checked | Findings |
|---|---|---|
| Trust boundary — can scraped text reach a rendered document unchecked? | Traced every `Segment.*` construction site in `src/` by grep (89 sites across both agents). `_build_proposed_scenarios` is the only place a live-fetched string enters, and every one is `Segment.scouted_unverified(v)`. Executed `check_guardrail` against a scouted segment containing "credit union" (blocked), containing "best guaranteed" (blocked), and containing neither (allowed). Confirmed `_build_proposed_scenarios` raises `_GuardrailBlocked` *before* returning a body, and the caller does not write on that path. | Clean |
| Can `SCOUTED_UNVERIFIED` inherit WORLD/OPERATOR exemptions? | `check_guardrail`'s evaluative branch filters on `provenance in (AGENT, SCOUTED_UNVERIFIED)` — scouted text is checked, not exempt. The institutional-character branch's Case 1 (`provenance in (WORLD, OPERATOR)`) cannot match it, and `_is_name_voucher` requires `is_name`, which `Segment.scouted_unverified` structurally cannot set (no parameter exists). Verified the *residual* round-8 adjacency escape is real for scouted text (a `Segment.world(name, is_name=True)` immediately adjacent to a scouted trigger passes) and then verified it is unreachable in the shipped assembler: every candidate value is flanked by AGENT backtick segments. Test 22 asserts that structurally, so a future refactor that reorders the line trips it. | Clean, with a structural guard now added |
| PKB isolation | `_findings_file`, `_proposed_scenarios_file` (debt advisor) and `_findings_file`, `_history_file` (analyzer) all resolve under `<DATA_DIR>/user-import/debt-finance/`, asserted by monkeypatching `_host.get_data_dir` and checking `data in path.parents` and `pkb not in path.parents`. Confirmed `history.jsonl` is the most sensitive new artifact — it holds the operator's institution names and computed rates verbatim — and is correctly outside the PKB. `state.json` (the only PKB write) is `{input_hash, last_run_at}` / `{terms_hash, approved_finding_count, last_run_at}`, literal dict constructions, unchanged this sprint. | Clean |
| Activity-stream honesty | `threshold_crossings` returns `scenario_key` strings only; asserted no rate/dollar substring appears in them. The `_host.emit` on a crossing is a fixed string plus `_relative_pointer(_findings_file())` — no count, no key, no figure. The `_GuardrailBlocked` emit carries `data={"reason": reason}`, and `reason` is either the fixed `REASON_EVALUATIVE` constant or `REASON_INSTITUTIONAL_PREFIX` + the matched *trigger phrase* (`credit union`/`nonprofit`/`member-owned`) — a closed vocabulary from a 3-alternative regex, never operator content. | Clean |
| File I/O — symlinks, malformed files | See QA-1. Agents clean; `agenda_watch` not. Malformed-input resilience exercised across 9 `history.jsonl` shapes (empty, whitespace, non-JSON, `5`, `null`, `[1,2]`, truncated, NUL bytes, 2000 lines) and 10 `scout-patterns.json` shapes (wrong schema, non-list patterns, non-dict entries, missing regex, uncompilable regex, non-numeric `max_matches`, negative `max_matches`, 200 patterns, non-JSON) — none raise, all degrade to empty. `history.jsonl` as a *directory* also degrades to empty. | QA-1 |
| Path traversal | `_snapshot_path`/`_write_finding` derive filenames through `_slugish`, which is `[^a-z0-9]+ -> "-"` — `.` and `/` cannot survive, so a hostile feed URL or node name cannot escape the directory. Confirmed by construction and by the 48-char cap. The `scout-patterns.json` read *does* follow a symlink (test 48, pinned) but is read-only and confined to JSON pattern definitions. | Clean, with QA-2's collision as the residual |
| Network I/O / egress | Untouched this sprint: `is_airgapped()` short-circuits `tick()` before any consent or network machinery; feed URLs remain verbatim from the sealed agenda with `_URL_RE` requiring `^https?://`; `_MAX_FETCH_BYTES` (512 KB) and `_FETCH_TIMEOUT_SEC` (20 s) both still enforced; the fetch runs inside `scouting.check_watch`'s consent scope. No SSRF surface added — no code path composes a URL. | Clean |
| Deserialization | Only `json.loads` on `history.jsonl`, `terms.json`, `scout-patterns.json`, `agenda.json`, `agenda-watch.json`. No `pickle` on untrusted input. The one `pickle` use is `multiprocessing`'s own, over a `str`, a list of plain tuples, and a `Queue` — asserted picklable-by-reference in test 51 so a refactor that closures the worker fails loudly. | Clean |
| Regex / ReDoS | The sidecar's caps (`_MAX_PATTERN_LEN` 200, `_MAX_PATTERNS` 20, `_MAX_PATTERN_MATCHES` 10) are enforced, verified including the negative-`max_matches` clamp. The wall-clock bound works — `test_catastrophic_pattern_is_bounded_by_wall_clock` genuinely kills `(a+)+$`. But see QA-3: the same 2.0 s budget is where startup cost lands. | QA-3 |
| Crypto | No crypto added. `_sha`/`_terms_content_hash`/the fingerprint are SHA-256 used as content identity, not as a MAC and not for a secret comparison, so constant-time comparison is not applicable. No MD5/SHA-1 anywhere in the touched files. | Clean |
| Dependencies | Zero new dependencies. `git diff 73f02d9..HEAD` touches no `pyproject.toml`, no lockfile. `multiprocessing`, `html.parser`, `difflib` are stdlib. | Clean |

## Seal verification

Re-ran
`PYTHONPATH=<worktree>/src:/Users/netsushi/ProJects/qukaizen-dac .venv/bin/python3 scripts/forge_debt_finance_world.py`.
Output: `44 terms, sourced {'model': 0, 'sourced': 44, 'total': 44}`,
`world_sha256 7a121526e5674ce038b396c5c6df6895df94adcc7fed16ea7528effbb5564075`
— matches the recorded hash, and `git status --porcelain examples/worlds/debt-finance`
is empty, so the reseal is byte-identical, not merely hash-equal. **Confirmed.**

## Performance

N/A as a benchmark — but QA-3 records a measured 0.60 s per-feed-per-tick
fixed cost for candidate extraction in a portal-shaped process, against a
2.0 s budget. That is a number the sprint should own rather than discover.

## Coverage delta

Not measured as line coverage. Test-count delta: +60 passing, +6 xfail
in `tests/test_debt_finance_qa_round12.py`. The six xfails are QA-1 (3),
QA-2 (2), and INFO-22 (1), marked non-strict so a fix reports XPASS rather
than breaking the suite; un-mark them in the fixing commit.

## Notes for the next QA pass

- **The round-11 "265 tests pass across the twelve suites" claim is true and
  was measured on the wrong population.** Four of this sprint's tests fail in
  the full suite. Targeted-suite runs are how BLOCK-3 hid in round 1 (a
  synthetic fixture that didn't resemble the sealed bundle) and it is how
  QA-3 hid in round 11 (a targeted suite that didn't resemble the real
  session). Any future round on this feature must quote a full-suite number
  and a baseline number, not a subset.
- **Twelve rounds of review went into `check_guardrail` and zero went into
  the file I/O around it.** QA-1 and QA-2 are both in `agenda_watch.py`'s
  plumbing — path construction and write mode — which no review round
  examined, because every round was drawn to the provenance argument. The
  guardrail is, at this point, genuinely done; the code around it has not
  had a single adversarial pass.
- **`spawn` has a much larger contract than "it isn't `fork`".** It couples
  this module to the parent's cwd, `sys.path`, and `__main__` guard. That
  contract is undocumented and untested; tests 49–52 are a start, not
  coverage.
- The `_slugish` truncation pattern (QA-2) is worth grepping for elsewhere in
  the repo — any other place that derives a filesystem identity from a
  truncated slug of a user- or World-supplied string has the same shape.

---

# QA round 13 — re-verification of the round-12 fixes (2026-07-31)

**Date:** 2026-07-31
**Build:** [BUILD_LOG.md](./BUILD_LOG.md) at `0cdadf1`
**Re-verifies:** QA round 12's FAIL (QA-3 HIGH, QA-1 MEDIUM, QA-2 MEDIUM)
**New tests:** `tests/test_debt_finance_qa_round13.py` (26 passing) +
`tests/_agenda_watch_workers.py` (spawn-injectable worker stand-ins)
**Verdict: PASS**

## How this run was invoked

`PYTHONPATH="$(pwd)/src:/Users/netsushi/ProJects/qukaizen-dac"
.venv/bin/python3 -m pytest tests -q -p no:randomly` — the full suite, per
round 12's own note that targeted-suite runs are how QA-3 hid.

| run | result |
|---|---|
| base `73f02d9`, full suite (round-12 measurement) | 55 failed, 3867 passed, 7 errors |
| branch `e6a4cdc` (pre-fix), full suite (round-12 measurement) | 60 failed, 3978 passed, 7 errors |
| **branch `0cdadf1` + round-13 tests, full suite** | **56 failed, 4016 passed, 7 skipped, 3 xfailed, 7 errors (19m48s)** |
| branch, `test_agenda_watch.py` + round-12 + round-13 alone | 119 passed, 1 skipped, 1 xfailed |

The four sprint-owned failures round 12 filed as QA-3 are **gone**: `grep`
over the full-run failure list for `agenda|debt|round1` returns **zero**.
The remaining 56 + 7 all sit in files this sprint never touches
(`test_world_forge_api`, `test_bench_ai_eng_harness`, `test_aerollm_*`,
`portal/test_build_tab`, …) and match the pre-existing baseline population.
`git diff --stat 73f02d9..HEAD -- src scripts tests` is 12 files, all
debt-finance/agenda-watch. Independently re-derived, not taken on trust.

## Re-verification of each round-12 finding

### QA-3 (HIGH) — CLOSED, and the fix's own new surface was attacked

Re-ran round 12's exact deterministic repro (delete the cwd, then call
`_extract_candidates_bounded`). Before: `{}` plus a log line blaming
"possible catastrophic-backtracking pattern in the mounted World's
scout-patterns.json". Now: `{}` plus **"could not start the
candidate-extraction subprocess"** — an honest diagnosis pointing at the
right layer. Confirmed by execution, not by reading the diff.

The two-phase Pipe protocol is *new concurrency code*, so it got its own
failure-injection battery rather than a re-read. Injecting a stand-in worker
requires an importable module (spawn pickles the target by reference), which
is what `tests/_agenda_watch_workers.py` exists for.

| injected failure | expected | observed |
|---|---|---|
| child sends `ready` then `os._exit(9)` (OOM-killer / segfault shape) | EOF via `poll()`, not a hang, not a burned budget | returns `{}` in well under the 2.0 s matching budget |
| same | log must not accuse backtracking | logs "exited (code …) without producing a result"; the word "backtracking" is absent |
| child sends `ready` then sleeps forever | this IS the backtracking case | killed at ~2 s, backtracking wording present — the wording is still reachable when it is correct |
| child sleeps **3.0 s before** `ready`, then answers instantly | the old single 2.0 s budget would have killed this | result delivered intact — the QA-3 regression guard |
| child never sends `ready` | bounded by `_STARTUP_TIMEOUT_SEC`, named honestly | "startup problem", no backtracking wording |
| result payload 500 KB (> a pipe buffer, reachable per ASK-20) | parent drains, no deadlock | full payload returned |
| all of the above, then `mp.active_children()` | no leaked/zombie children | none alive |

Answering the two questions posed at me directly: a child that dies between
`ready` and `result` does **not** hang the parent — the write end closing
makes `poll()` return immediately and `recv()` raise `EOFError`, which
`_recv`'s `except Exception` converts to `None`; and because `proc.is_alive()`
is then false, the honest "exited without producing a result" branch is taken
rather than the backtracking one. Same for an OS kill mid-match. The
`child_conn.close()` in the parent right after `proc.start()` is what makes
that EOF possible at all, and it is present.

### QA-1 (MEDIUM) — CLOSED; the corrected-in-flight fix re-checked for the same class of slip

The specific worry raised (that the first attempt forgot to wrap `os.open`
itself) is closed: `_safe_write_atomic` wraps `os.open` *and* the write in
separate `try/except OSError` blocks, both returning rather than raising. New
tests attack around it rather than repeat it:

- **The docstring's load-bearing claim is now asserted, not assumed.** It
  argues the final `os.replace` needs no guard because POSIX `rename()`
  replaces a directory entry rather than writing through it. Tested with a
  symlink at the *final* path: victim untouched, `dest` is no longer a
  symlink, content correct.
- **Refusal leaves no partial file** and does not raise.
- **A stale regular `.tmp`** (killed-process leftover) is still overwritten —
  a guard that refused those would silently no-op *forever* after one crash.
  This is the failure mode an over-strict `O_EXCL` fix would have introduced.
- Mode is `0600` (no group/other bits), unicode round-trips, a **directory**
  at the tmp path degrades silently, an unwritable parent degrades silently.
- The finding site's deliberate asymmetry (raises `OSError`) is pinned twice:
  the raise itself, and the fact that `tick()`'s `_write_finding` call is
  inside an `except Exception`. A future "consistency" refactor that made it
  silent would advance `entry["sha256"]` while dropping the finding —
  permanently hiding a real change — so the asymmetry is correct and now
  guarded.

### QA-2 (MEDIUM) — CLOSED, with two properties the fixing commit did not cover

- URLs sharing the **entire** 39-char readable prefix and differing only in
  the truncated tail are now distinct (the exact Chase/Navy-Federal shape).
- **Two URLs with no ASCII alphanumerics** (`https://例え.test/…` vs
  `https://別の.test/…`) previously normalised to the *same* slug outright —
  worse than truncation, and not covered by the fixing commit. Distinct now.
- Slug is sha256-derived, therefore stable across processes — asserted
  explicitly, because a `hash()`-based digest would be `PYTHONHASHSEED`-salted
  and would make every tick look like a change.
- Length bounded ≤ 48 for a 4000-char URL; no `/`, `\` or `..` can survive;
  empty/punctuation-only input still yields a usable non-leading-dash slug.

## New findings

| # | Test | Symptom | Severity |
|---|---|---|---|
| — | — | none blocking | — |

### INFO-24 (LOW, filed not failing) — the slug change is an un-migrated rename for already-running labs

QA-2's fix changes every snapshot filename and every finding stem. For a lab
that has already run, `state.json` still holds the old sha but the old
snapshot file is orphaned under its old name, so `_read_snapshot` returns
`None` on the first post-upgrade change. Pinned as behaviour in
`TestSlugChangeMigration`: it degrades to an **Excerpt** section rather than
a unified diff (honest, not silent), the `Change: <old> → <new>` line is
still correct, and nothing crashes. Residue: the orphaned `.txt` snapshots
and any pre-upgrade unreviewed findings under the old stem are never pruned
(the prune glob uses the new stem). One-off, bounded, cosmetic. Backlog, not
a blocker.

### INFO-25 (LOW) — one round-12 test became vacuous under the fix

`test_shipped_feed_urls_are_at_the_truncation_boundary` asserts some shipped
URL yields a 48-char slug. Post-fix, *every* sufficiently long URL yields
exactly 39 + 1 + 8 = 48 chars, so the test can no longer fail and no longer
documents what its name and docstring claim. Harmless, but it is now a
tautology sitting in the regression set. Its sibling
(`…slugs_are_currently_distinct`) still carries the real guard.

### INFO-26 (LOW) — the `.tmp` staging name is fixed per destination

`_safe_write_atomic` derives the tmp name deterministically
(`path.with_suffix(".tmp")`), so two concurrent writers to the same
destination could interleave. Checked whether that is reachable:
`agenda_watch.tick` has exactly one caller in `src/` (the Librarian's
`watch_horizon`, `await`-ed via `asyncio.to_thread`), and no API route or
second call site exists — so it is serialized today. Recorded as a
constraint on any future "run the watch on demand from the portal" feature,
not as a live defect.

## Security review

| Surface | What I actually checked this round | Findings |
|---|---|---|
| File I/O — symlink following | All three `agenda_watch` write sites re-tested by execution against a pre-placed symlink: state (`.tmp`), snapshot (`.tmp`), finding (final path). None writes through. Additionally verified the *final*-path symlink case for the rename step, the directory-at-tmp case, the unwritable-parent case, and the stale-regular-tmp case. `O_NOFOLLOW` is guarded by `hasattr` for non-POSIX, and the resulting mode is `0600`. | Clean — QA-1 closed |
| Path traversal via derived filenames | `_slugish` still collapses `[^a-z0-9]+`, so `.`/`/`/`\` cannot survive; asserted against `../../etc/passwd`, `..`, `/`, `.`. The unslugified `world` component in `_snapshot_path`/`_write_finding` is bounded upstream by `world_mount._SLUG_RE` (`^[a-z0-9][a-z0-9-]*$`), validated at mount and cross-checked against `spec.json`/`face.json` — so it cannot introduce a separator. Verified in `world_mount.py`, not assumed. | Clean |
| Subprocess / IPC | The parent unpickles whatever arrives on `recv()`. The pipe fds are private to the parent/child pair (child's copy closed in the parent immediately after `start()`), so no local process can inject a pickle onto it; the only writer is our own worker, whose payloads are `str`/`list`/`dict`. Result is `isinstance(result, dict)`-checked before return. Children are daemonized and every exit path terminates→kills→joins; the leak test confirms no survivors. | Clean |
| ReDoS bound | Still real after the refactor: an injected worker that hangs post-`ready` is killed at the 2.0 s matching deadline, and `test_agenda_watch.py`'s genuine `(a+)+$` test still passes in 2.97 s for the whole file. The startup allowance (10.0 s) is *not* a widening of the ReDoS window — it only covers the interval before matching can begin, and a child that never confirms readiness is killed. | Clean |
| Crypto | The one new primitive is `hashlib.sha256(value)[:8]` in `_slugish`, used as a **filename disambiguator**, not a MAC and not a secret comparison — no constant-time requirement, no MD5/SHA-1 introduced. 8 hex chars = 32 bits: adequate for accidental collision between a handful of feeds, and a deliberate collision buys an attacker only the ability to make one World feed overwrite another's snapshot in their own lab. Sized correctly for the job. | Clean |
| Dependencies | `git diff 73f02d9..HEAD` still touches no `pyproject.toml` and no lockfile. Zero new deps; the new test helper uses only `os`/`time`. | Clean |
| Trust boundary, PKB isolation, activity honesty, guardrail | Not re-derived — round 12 verified these by execution and the fixing commit touches none of that code (`git show --stat 0cdadf1` is `agenda_watch.py` + tests + this report). | Unchanged |

## Seal verification

Re-ran `scripts/forge_debt_finance_world.py`: `44 terms, sourced
{'model': 0, 'sourced': 44, 'total': 44}`, `world_sha256
7a121526e5674ce038b396c5c6df6895df94adcc7fed16ea7528effbb5564075` — matches,
and `git status --porcelain examples/worlds/debt-finance` is empty. Reseal is
byte-identical. **Confirmed independently.**

## Performance

N/A as a benchmark. One number worth owning: the fix does **not** remove
QA-3's measured ~0.6 s per-feed-per-tick spawn cost, it only stops that cost
from being charged against the ReDoS budget. Worst-case candidate extraction
per feed is now ~10 s (startup) + 2 s (matching) before it gives up, versus
2 s total before — a longer tail on a background agent tick, in exchange for
never silently disabling extraction. Correct trade for this feature; recorded
so it is owned rather than rediscovered.

## Coverage delta

Test-count delta this round: **+26 passing** (`test_debt_finance_qa_round13.py`),
0 xfail. Full-suite passing count `3990 → 4016`. Cumulative sprint test
delta vs `73f02d9`: +2716 lines across 12 files, all sprint-owned.

## Notes for the next QA pass

- **The fix's own new code is where the next bug will be.** Round 12's
  lesson was "twelve rounds went into `check_guardrail` and zero into the
  file I/O around it". Round 13's is the same shape one level in: the QA-3
  fix replaced a simple `Queue` handoff with a two-phase Pipe protocol, and
  a protocol has states a helper function does not. It survived seven
  injected failure modes, but it is one week old.
- **`tests/_agenda_watch_workers.py` is the reusable lever.** Any future
  question about this subprocess ("what if the child is SIGSTOPped?", "what
  if it sends garbage?") is now a five-line function in that file, because
  spawn's pickle-by-reference requirement is already solved there.
- **Un-migrated identity changes deserve a checklist entry.** INFO-24 came
  from asking "what happens to a lab that already ran the old code?", which
  no round has asked systematically. Any future change to a derived filename
  or a state key in this repo should answer it before merge.
- **Prune INFO-25.** A test that cannot fail is worse than no test; it
  occupies the slot a real guard would have.
