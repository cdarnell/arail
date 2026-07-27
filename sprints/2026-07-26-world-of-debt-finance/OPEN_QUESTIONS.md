# Open questions for the operator — World of Debt Finance

Surfaced by the finalize pass after adversarial review. None block writing
code except where noted; all should be decided before `/builder` seals the
World bundle so the answers land in the artifacts rather than being
retrofitted.

1. **Canonical disclaimer wording.** `compliance/DISCLAIMER.md` needs exact,
   operator-approved text for (a) the "not a licensed financial advisor /
   educational information only" core disclaimer both agents append in code,
   and (b) a CROA / state debt-management-licensing caveat for anyone forking
   this for third-party or commercial use. This is quasi-legal product text
   (same category as the repo's existing Llama/Gemma disclosure language) —
   should not ship with AI-drafted wording as final.

2. **Real institutions to cite.** `spec.json`/`terms.json` currently carry
   placeholders for a specific real credit union and a specific real card
   issuer's balance-transfer page. Naming a specific commercial entity in a
   sealed, versioned World bundle is a real accuracy/liability surface (rates
   change, terms get misquoted). Confirm which real institutions to name, or
   confirm it's fine for the architect/builder to pick defensible,
   well-known, easily-reverifiable ones (e.g. a major NCUA-insured credit
   union with public rate tables).

3. **Real-data test commitment.** Win condition #1 is strongest if tested
   against real balances at least once during the sprint window. Willing to
   hand-transcribe real numbers into `lab/data/user-import/debt-finance/`, or
   should the team use a realistic stand-in dataset and treat the real-data
   test as a fast-follow? (Also disconfirming signal #1 in VISION.md — worth
   deciding deliberately.)

4. **Airgapped vs. hybrid intent.** Plan to flip `LAB_MODE` to `hybrid` and
   approve at least one scouting consent for this World during the test
   window, or should this ship explicitly framed as curated-content-only for
   now? Affects how much authoring effort is worth spending on additional
   real URL-kind `knowledge_sources` beyond the 3 the agenda-cap will
   actually use live.

5. **Reveal-affordance fast-follow.** v1 requires opening the findings file
   directly (Finder/text editor) — no new portal route is added. Acceptable,
   or is the small, generic `user_data` reveal-whitelist-slot addition
   (extending the existing `/api/system/reveal` mechanism) worth building
   now instead of deferring?

6. **Two cross-repo `qukaizen-dac` proposals.** (a) making the
   agenda-derivation cap in `dac_world/seal.py` kind-aware instead of
   position-based, and (b) a non-strippable, gate-enforced disclaimer field
   in `face.json`. Both are real fixes but live in a sibling repo with its
   own review process. File either as a proposal now, or leave as documented
   future ideas until a second World's needs make the case more concretely?

7. **Cross-World policy question.** This sprint discovered that ARAIL's
   agent folders under `lab/pkb/` are explicitly designed to be
   wiki-indexed and searchable by anyone with portal access — incompatible
   with any future personal-data World (health, career, relationships) using
   the same location for sensitive output. Should "sensitive/personal agent
   output never lives under `lab/pkb/`, always under `lab/data/`" become a
   written rule in this repo's CLAUDE.md now, so the next personal-data World
   doesn't have to rediscover this the way this sprint did?
