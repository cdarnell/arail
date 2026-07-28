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
