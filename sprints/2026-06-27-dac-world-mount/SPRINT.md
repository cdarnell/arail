# Sprint: dac-world-mount

**ID:** 2026-06-27-dac-world-mount
**Started:** 2026-06-27
**Product:** arail

## Task

Sprint 2 of the DaC↔ARAIL integration (plan: `~/.claude/plans/quizzical-chasing-lovelace.md`;
DaC-side contract: qukaizen-dac `docs/adr/0004-dac-arail-mount-contract.md`). DaC now **emits**
an ARAIL-mountable World (sealed bundle + `capabilities.json` + governed `SKILL.md` +
`arail-plugin.json`). This sprint makes **ARAIL consume it**: `arailctl world verify + mount` a DaC
WorldBundle → register its capabilities + load its `SKILL.md` into
`skills_loader.compose_system_context()` so Buddy/Researcher operate in the mounted domain instead
of only the default AI/ML world. v1 = local bundle mount (data only).

## Existing state to reconcile (DO NOT duplicate)

ARAIL already has partial mount infrastructure + staged worlds (uncommitted on
`qukaizen/arail-world-forge-doc`): `src/arail/world_mount.py` (`verify_seal`, `_BUNDLE_FILES`,
`_stage_files` → `lab/pkb/sources/world-<slug>/`), `src/arail/capabilities/*`,
`src/arail/skills_loader.py`, and staged `lab/pkb/sources/world-{physics,espresso,horticulture,…}/`
+ `lab/worlds/`. Sprint 2 must EXTEND this path, not reinvent it. The architect maps the gap
between "world staged on disk" and "Buddy's system prompt actually uses it."

## Phases

| Phase | Subagent | Artifact | Status | Started | Finished | Verdict |
|---|---|---|---|---|---|---|
| think | visionary | VISION.md | skipped | — | — | win condition locked by approved plan |
| plan | architect (design) | ARCHITECTURE.md | done | 2026-06-27 | 2026-06-27 | complete (Option b + defense-in-depth) |
| build | builder | BUILD_LOG.md | done | 2026-06-27 | 2026-06-27 | review-fixes landed (30/30); defects closed |
| review | architect (review) | REVIEW.md | done | 2026-06-27 | 2026-06-27 | WEAK_PASS → 2 display defects fixed + orchestrator-verified |
| test | qa | TEST_REPORT.md | done | 2026-06-27 | 2026-06-27 | PASS (29 adversarial; security held) |
| ship | — | commit | done | 2026-06-27 | 2026-06-27 | committed on qukaizen/arail-dac-world-mount |

> **Sprint journey:** plan (Option b + defense-in-depth) → build (26 tests) → review **WEAK_PASS**
> (security solid; 2 display defects: `###` mangling + cap truncation) → review-fix (narrowed
> containment, 56KB cap) → QA **PASS** (29 adversarial tests; homoglyph/DoS/legit-shaped-source
> probed, structural containment held). Loop closed: DaC creates Worlds → ARAIL mounts them →
> the sourced glossary enters Buddy/Researcher's prompt.

## Follow-ups (post-ship)

- **LOW** — `_contain_skill_body`: escape ARAIL delimiters (`\#`/backtick-wrap) instead of U+200C
  prefix, so a neutralized delimiter can't even be read as a section cue (QA recommendation).
- **CROSS-REPO (durable seal fix)** — promote `SKILL.md` to SEALED: DaC adds it to bundle
  `files{}` + ARAIL's `verify_seal` iterates `files{}` generically (vs the hardcoded 6). Closes the
  seal-exempt-SKILL.md gap that the load-time containment currently covers defensively.
- **NOTE** — QA gated the `world_mount` Python API, not the `./arailctl world` bash wrapper; full
  163-file `tests/` suite stalls under sandbox contention (every file passes standalone) — run a
  clean-machine `./arailctl world mount` + full-suite smoke at integration.

## Acceptance gate (definition of done)

`arailctl world mount <DaC bundle>` → (1) seal verified, broken seal REFUSES to mount; (2) the
World's capabilities appear in the registry; (3) its `SKILL.md` is loaded so Buddy answers a
domain question from the mounted World's sourced terms; (4) with nothing mounted, ARAIL falls back
to the default AI/ML world. Security: mounted content is treated as DATA, never trusted as
instructions (the SKILL.md is already DaC-sanitized, but ARAIL must not re-introduce injection).

## ARAIL product gating (from arail/CLAUDE.md — layered on the generic gates)

Local-first, airgapped-default, runs on others' machines. QA allocation shifts to ~30% setup /
30% Buddy quality / 20% security / 10% happy-path / 10% regression. Ship needs the
mount-on-a-clean-checkout path to work.

## Branch note

ARAIL is on `qukaizen/arail-world-forge-doc` with related uncommitted staged-world work. Architect
to advise: continue here vs branch `qukaizen/arail-dac-world-mount` from it. Do NOT sweep the
user's unrelated uncommitted work into sprint commits.

## Skipped phases

| Phase | Reason |
|---|---|
| think (visionary) | Win condition + wedge locked by the approved integration plan. |
