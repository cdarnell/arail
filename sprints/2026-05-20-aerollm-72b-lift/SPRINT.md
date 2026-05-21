# Sprint: aerollm-72b-lift

**ID:** 2026-05-20-aerollm-72b-lift
**Started:** 2026-05-20
**Product:** arail
**Branch:** qukaizen/arail-aerollm-72b-lift

## Task

Lift the AeroLLM maximus-tier deep model from the `Qwen2.5-7B-Instruct-4bit`
placeholder to `mlx-community/Qwen2.5-72B-Instruct-4bit` (top of AeroLLM's proven
golden-gate envelope, same family as the ai-eng 3B default). This is commit **3b**
deferred from sprint `2026-05-18-ai-eng-v2.1` — split out because it is fully
independent of the ai-eng model publish (the 72B already exists on HF) and has its
own verification story.

Design basis: the ai-eng plan at `/Users/netsushi/.claude/plans/pure-forging-pizza.md`
§ "Phase 3 step 1-2" + the AeroLLM proven-envelope note (Qwen2.5 ≤72B in the 19/19
golden gates per aerollm/CLAUDE.md).

## Two bugs found during orientation (the reason this isn't a one-line config edit)

1. **`AEROLLM_MODEL_MIN_ID` stomp** — `scripts/setup.sh:114` resolves MIN_ID by
   reading `aerollm_maximus` FIRST: `models.get("aerollm_maximus", models.get("aerollm_min", ...))`.
   Currently masked because `aerollm_maximus == aerollm == 7B`. The moment we lift
   `aerollm_maximus` to 72B, the **minimalist** tier's MIN_ID also resolves to 72B
   → clean-machine minimalist installs would try to load a 72B deep model → hard OOM
   (directly hits the user's documented OOM pain point).

2. **AeroLLM has no per-tier resolution** — `capture_tier` resolves AirLLM per tier
   (`setup.sh:975-978`) but for AeroLLM `setup.sh:986` just takes the loaded `aerollm`
   value (7B) for BOTH tiers. The MIN_ID/MAX_ID vars are loaded but never applied to
   AeroLLM. So maximus users currently get the 7B deep model regardless. The lift must
   add the AeroLLM tier `case`, mirroring AirLLM.

## Scope

**In scope:**
- `pyproject.toml`: `aerollm_maximus` → 72B; add `aerollm_minimalist` = 7B; keep `aerollm` legacy alias = 7B.
- `scripts/setup.sh`: fix the MIN_ID loader stomp (read `aerollm_minimalist`/`aerollm_min` first); add AeroLLM per-tier `case` in `capture_tier`; lift the `AEROLLM_MODEL_MAX_ID` shell default to 72B; update comments.
- A memory/RAM-headroom warning when maximus selects the 72B on a machine below a safe threshold (~48 GB), consistent with the OOM-caution principle.
- A test verifying tier resolution: minimalist → 7B, maximus → 72B; and that the loader no longer stomps MIN_ID.

**Out of scope:**
- `models_catalog.yaml` (the deep model is not a user-pullable chat-gallery row; it's resolved via pyproject + setup.sh env).
- The ai-eng model build/publish/wire (3a) — blocked on operator build + publish decisions; separate.
- Actually running a 72B (no ≥96 GB machine available here) — the test verifies resolution, not execution.

## Phases

| Phase | Subagent | Artifact | Status | Verdict |
|---|---|---|---|---|
| plan | (design exists: pure-forging-pizza.md Phase 3 + bugs above) | — | skipped | win condition obvious; deferred-commit from a reviewed architecture |
| build | builder | BUILD_LOG.md | done | 4 commits (a52338c..bf189dc); 12 tests; both bugs locked; min→7B max→72B |
| review | architect (review) | REVIEW.md | done | WEAK_PASS (commit d75537d); min→7B max→72B proven; both bugs fixed; 3 carryovers |
| build | builder (fix-loop) | BUILD_LOG.md | done | CO-1/CO-2/CO-3 cleared (1085844/dad8726/4a3325a); full suite 13 fail (−1, retired red test) / 1924 pass |
| test | qa | TEST_REPORT.md | skipped (override) | Architect determined review sufficient: deterministic config/resolution change, no network/auth/secrets/exec surface; all consumers default to 7B (under-provision, cannot OOM); running a real 72B is out of scope (no ≥96GB machine) |
| ship | — | PR | done | PR #69 opened |

## Decisions log

| Date | Decision | Rationale |
|---|---|---|
| 2026-05-20 | Split 3b out of the ai-eng sprint into its own change | Independent of the ai-eng publish (72B already on HF); own verification story; architect's original 3a/3b split rationale |
| 2026-05-20 | Skip visionary | Win condition is obvious (maximus should use the proven 72B, not a 7B placeholder); deferred commit from an already-VISION'd + ARCHITECTURE'd sprint |
| 2026-05-20 | Scope excludes models_catalog.yaml | Deep-mode model is resolved via pyproject/setup.sh env, not the chat gallery; the original plan's catalog mention was imprecise |

## Notes

- **OOM discipline** (MEMORY): the MIN_ID stomp bug is precisely an OOM trap — getting tier resolution wrong sends a 72B to a minimalist clean-machine install. The test must prove minimalist stays at 7B.
- **AeroLLM proven envelope**: Qwen2.5 up to 72B dense is in the 19/19 golden gates; 72B is the ceiling of "proven," not beyond it.
