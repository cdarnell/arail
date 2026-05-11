# Sprint: min-tier-simplification

**ID:** 2026-05-10-min-tier-simplification
**Started:** 2026-05-10
**Product:** arail
**Predecessor:** 2026-05-10-chat-model-sync (PR #44; this sprint builds on the gated state established there)

## Task

Simplify the minimalist (`min`) tier so the first-run experience is unsurprising:

1. **No disk-streaming backend in `min`.** Drop `airllm>=2.0` from `[project.optional-dependencies.min]` so it doesn't even get installed.
2. **No deep backend in `min`.** Min runs Ollama only. AeroLLM reserved for `max`. (Resolves cleanly because `_resolve_default_deep_backend()` from PR #44 already returns `None` gracefully.)
3. **Compare deferred to add-on.** Min ships with a single chat box. New CLI verbs `./arailctl enable compare` / `disable compare` flip an `ARAIL_COMPARE_ENABLED` env flag; portal renders the `+ Compare` button conditionally.
4. **Min keeps its current surfaces** (Dashboard, Chat, Autoresearch, Knowledge, Agents). Only the deep backend and compare are pulled out.

## Open-question resolutions (locked in via user before sprint started)

| Decision | Value |
|---|---|
| Compare Model B on pure-min | Cloud Model B (Claude / OpenRouter / NIM / HF in hybrid mode) |
| Default `ARAIL_COMPARE_ENABLED` when unset | `1` (on) — preserves current behavior for upgrade-in-place users; new installs explicitly write `0` for min, `1` for max |
| CLI verb naming | `arailctl enable compare` / `arailctl disable compare` |
| Sprint order | After chat-model-sync ships (PR #44 open) |

## Phases

| Phase | Subagent | Artifact | Status | Started | Finished | Verdict |
|---|---|---|---|---|---|---|
| think | visionary | VISION.md | skipped | — | — | (plan-file approved win condition) |
| plan | architect (design) | ARCHITECTURE.md | done | 2026-05-10 | 2026-05-10 | complete |
| build | builder | BUILD_LOG.md | done | 2026-05-10 | 2026-05-10 | complete |
| review | architect (review) | REVIEW.md | done | 2026-05-10 | 2026-05-10 | PASS |
| test | qa | TEST_REPORT.md | done | 2026-05-10 | 2026-05-10 | PASS (35 sprint, 968 repo, 0 regressions) |
| ship | — | PR | done | 2026-05-10 | 2026-05-10 | shipped — https://github.com/cdarnell/arail/pull/45 (stacked on PR #44) |

## Decisions log

| Date | Decision | Rationale |
|---|---|---|
| 2026-05-10 | Skip visionary | User's approved plan at /Users/netsushi/.claude/plans/ok-one-more-minamalist-enchanted-alpaca.md is the win definition |
| 2026-05-10 | Compare on min uses cloud Model B | Preserves "min = Ollama only" while making compare meaningful; aligns with hybrid mode flow |
| 2026-05-10 | `ARAIL_COMPARE_ENABLED` defaults to "1" when unset | Avoids surprising existing min users on upgrade-in-place; new installs write explicit value |
| 2026-05-10 | New branch from chat-model-sync HEAD, not main | Builds on the `_resolve_default_deep_backend() → None` semantics shipped in PR #44; will rebase if #44 merges before this PR |

## Skipped phases

| Phase | Reason |
|---|---|
| think | Win condition already specified in approved plan; this is execution, not exploration |

## Notes

- Approved plan: `/Users/netsushi/.claude/plans/ok-one-more-minamalist-enchanted-alpaca.md`
- Key files: `pyproject.toml`, `scripts/setup.sh`, `scripts/upgrade.sh`, new `scripts/enable_compare.sh` + `scripts/disable_compare.sh`, `arail` (top-level shell), `src/arail/portal/app.py`, `src/arail/portal/templates/chat.html`, `README.md`, `docs/CERTIFIED_MODELS.md`, `CLAUDE.md`
- QA allocation per arail CLAUDE.md: 30% setup / 30% Buddy / 20% security / 10% happy / 10% regression
  → adapt here: 40% tier-correctness / 25% setup-flow (first-run min) / 20% upgrade-path (min↔max) / 15% regression
