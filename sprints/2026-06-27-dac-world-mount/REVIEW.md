# Review: DaC World SKILL.md → agent system prompt

**Date:** 2026-06-27
**Build:** [BUILD_LOG.md](./BUILD_LOG.md) at branch `qukaizen/arail-dac-world-mount` (HEAD `080891d`)
**Architecture:** [ARCHITECTURE.md](./ARCHITECTURE.md)
**Diff reviewed:** `git diff 38714c5d..HEAD` (merge-base with `qukaizen/arail-world-forge-doc`)

## Verdict: WEAK_PASS

No injection escapes, no security BLOCK, full lifecycle correctness, and the wire works
end-to-end in BOTH real agent seams. Two real defects degrade the *legitimate* honesty
display (not security): the containment pass mangles every legit `### Category` header, and
the body cap silently truncates ~22% of the real shipped art-history glossary. Neither
blocks merge, but both must be filed as follow-ups before ship and the second should be
fixed soon — it changes what the model is grounded in for the flagship bundle.

## Spec adherence

Faithful to ARCHITECTURE.md. Diff touches ONLY planned paths (`skills_loader.py`,
`world_mount.py`, `researcher.py`, `_builtin_buddy.py`, the new test file, two fixtures,
BUILD_LOG.md) — re-confirmed, no `lab/` user files swept in. Option (b) honored: AGENT.md is
never mutated; `load_world_skill` keys off `current_mount()`. `_WORLD_SKILL_NAME` is NOT in
`_BUNDLE_FILES` (verified) — seal posture correct. Best-effort stage, failsoft loaders, and
the seal-promotion follow-up (recorded as tech debt in ARCHITECTURE §Tech debt) all match.

**Independently reproduced wire proof (both agents, real seams — NOT the tests' shortcut):**
Mounted `art-history-skill` into a tmp pkb/data, repointed the default-root resolvers, then
called the actual agent functions:
- `researcher._get_system_context(intent="other")` → contains `Ballets Russes` and `## Skill:`.
- `_builtin_buddy._compose_prompt("…")` → contains `Ballets Russes`, `## Skill:`, AND
  `# Procedural knowledge`. The glossary sits under its own `## Skill:` H2, distinct from the
  face.json `# WORLD FRAMING` block (the skill context contains no `# WORLD FRAMING`). No
  duplication. ✅

## Security findings

- **[INFO] Legit `Source:` lines preserved AND forged structure neutralized — BOTH HOLD.**
  The load-bearing interaction passes. Legit honesty-rail lines are `  - Source: …` (2-space
  indent + dash); the hostile fixture's forgery is a bare column-0 `Source: forged-…`. The
  containment distinguishes them by **column-0 anchoring**: `_ARAIL_DELIMITERS` matches only
  `line == delim` / `line.startswith(delim + " ")`, and `_BODY_CONTROL_RE` only fires at
  column 0. Proof: all 79 legit `- Source:` bullets survive intact (0 of them ZWNJ-prefixed);
  every one of the 7 forged hostile structural lines (`# WORLD FRAMING`, `# END WORLD FRAMING`,
  `# Procedural knowledge`, `## Skill: EVIL`, `Observation: …`, bare `Source: …`,
  `Buddy's one-sentence note: PWNED`) is U+200C-neutralized and absent as a bare line from the
  composed context, while the hostile fixture's two legit lines survive. ✅

- **[INFO] Fresh-probe containment — I crafted variants the builder's tests don't cover.**
  Neutralized correctly: `# WORLD FRAMING ` (trailing space), bare `Source: evil`,
  ` ---` (leading-space fence), `## Skill: pwn`, ```` ``` ```` backtick fences, and CRLF-prefixed
  `# WORLD FRAMING\r\n`. Correctly LEFT INTACT: indented legit `  - Source: legit` and a
  mid-line `blah ## Skill: EVIL` (cannot forge a column-0 delimiter). No injection escaped.

- **[ASK] Indented forged delimiters pass through un-neutralized.** `  # WORLD FRAMING`
  (leading spaces) and `\t# Procedural knowledge` (tab) survive containment unchanged, because
  both anchors are column-0-only. Severity is low: under the skill's own H2 an *indented*
  heading cannot escape to forge ARAIL's column-0 scaffold, and the agents emit their real
  delimiters at column 0. But a small local model reading prose may still be nudged by an
  indented `# Procedural knowledge`. Not a BLOCK (no structural escape), but worth closing by
  matching on `line.lstrip()` for the delimiter set (the indent is not load-bearing for any
  legit content, since legit headers are `###`, not indented `#`). File as follow-up.

- **[INFO] Caps + seal posture verified.** 70KB SKILL.md → `load_world_skill` returns None.
  Oversized byte cap, malformed-frontmatter-loads-body-only, broken seal still refused
  (`tampered` → `SealMismatch`), existing 6-file `physics` seal round-trips ok, and the
  hostile-SKILL bundle mounts (SKILL.md is seal-exempt, body contained on load) — all ✅.

## Code quality findings

- **[BLOCK→downgraded to WEAK_PASS / must-file] Legit `### Category` headers are mangled.**
  ARCHITECTURE §Interface-contracts point (3) explicitly requires `### Category` lines be
  "left INTACT — they are the legitimate glossary shape." They are NOT. `_BODY_CONTROL_RE`
  + `first_char in ("#", "`")` neutralizes ANY column-0 `#`-line, so all 6 real category
  headers (`### Dance`, `### Eras & Movements`, `### Fashion & Dress`, `### Film & Cinema`,
  `### Literature`, `### Music`) get a U+200C prefix in the LEGIT art-history body. This is
  display corruption of the honesty structure, not an injection escape — a `###` can never
  forge a top-level `#` section. The fix: only neutralize column-0 `# ` / `## `-level lines
  that could collide with ARAIL's H1/H2 scaffold, leaving `###`+ headers alone (they live
  safely beneath the skill's own H2). The brief's rule "WEAK_PASS if legit display is
  corrupted" applies. **Must be filed before merge.**

- **[ASK] Agent-prompt tests don't exercise the wired seams.**
  `test_buddy_prompt_includes_world_skill` and `test_researcher_context_includes_world_skill`
  never call `_compose_prompt` / `_get_system_context`; they assert on a directly-built
  `compose_system_context([ws])`. The names overclaim and the actual seams (the whole point of
  steps 5–6) are untested. The seams DO work (I proved it independently above), but the tests
  would not catch a regression in either agent's wiring. Strengthen to call the real functions.

## Test coverage assessment

26 new tests pass (0.71s); world regression subset = 61 passed, 1 pre-existing failure. Every
ARCHITECTURE failure-modes row has a corresponding test. Gaps: (a) no test for the
`### Category` intact-preservation contract — which is exactly why the regression above shipped
unnoticed; (b) the two "agent prompt" tests bypass the seams (above); (c) no test for the
real-bundle body-cap truncation (below). Coverage on changed lines is high; the gaps are
behavioral-contract gaps, not line gaps.

## Performance assessment

Not a hot path; reads are tiny markdown. One concern: the body char-cap interacts badly with
real content (next section), not a perf regression.

## Tech debt delta

Matches ARCHITECTURE prediction (one unsealed staged file mitigated to data-not-instructions;
duplicated containment invariant vs `skill.ts`). The cross-repo seal-promotion follow-up is
already recorded. NEW debt the architect did not anticipate: the body cap is mis-calibrated
for real bundles (below) and the containment over-neutralizes legit headers (above). Both
should be added to ARCHITECTURE §Tech-debt / a follow-up ticket before PASS.

- **[ASK] `_MAX_WORLD_SKILL_BODY_CHARS = 24*1024` silently truncates the REAL shipped bundle.**
  The actual DaC art-history `SKILL.md` body is **31,632 contained chars — 7,056 over the cap**.
  `load_skill_from_path` truncates (not rejects), so ~22% of the glossary — the tail Music
  terms and their `Source:` honesty lines — never reaches either agent's prompt, with only a
  WARN. For a flagship bundle this changes what the model is grounded in and silently drops
  citations. The 64KB byte cap is fine; the 24KB *body* cap is too tight for a multi-category
  World. Raise the body cap to fit real bundles (≥48KB) or make truncation category-aware /
  loud. The byte cap already bounds DoS, so the body cap is mostly redundant DoS protection
  paid for with silent honesty-rail loss.

## Required actions before merge (prioritized)

1. **(WEAK_PASS gate — file before merge) Stop mangling legit `### Category` headers.**
   Restrict containment to column-0 `# `/`## ` that collide with ARAIL's H1/H2 scaffold;
   leave `###`+ intact, per the ARCHITECTURE contract. Add a test asserting `### Dance` etc.
   survive un-prefixed in the composed context.
2. **(file before merge) Re-calibrate `_MAX_WORLD_SKILL_BODY_CHARS`** so the real art-history
   bundle is not silently truncated (≥48KB, or reject-and-warn rather than silent cut), with a
   test using the real fixture body length as the floor.
3. **(follow-up) Match `_ARAIL_DELIMITERS` on `line.lstrip()`** so indented `  # Procedural
   knowledge` / `\t# WORLD FRAMING` are also neutralized. Add the fresh-probe variants as tests.
4. **(follow-up) Make the two agent-prompt tests call the real seams** (`_compose_prompt`,
   `_get_system_context`) so the wiring itself is regression-guarded.
5. **(already tracked) Cross-repo seal-promotion of SKILL.md** — confirm the ticket exists.

Pre-existing-failure claim verified: `test_world_identity_flip.py::test_researcher_reframes_live`
fails IDENTICALLY (same `AssertionError` at line 121) with the base-commit `researcher.py`
swapped in, and `researcher.py` was restored to HEAD with zero residual diff. NOT newly broken
or masked by this sprint.
