# Sprint: recap-core

**ID:** 2026-05-17-recap-core
**Started:** 2026-05-17
**Product:** arail
**Branch:** qukaizen/arail-recap-core (to be cut from main)
**Reference plan:** /Users/netsushi/.claude/plans/i-feel-like-we-radiant-snail.md (approved)

## Task

Sprint 1 of the ReCAP adoption plan. Build the `src/arail/agents/recap/`
module that implements Algorithm 1 from the ReCAP paper (NeurIPS 2025,
arXiv:2510.23822):

1. `core.py` — recursive plan-ahead loop with parent re-injection on
   backtrack. Algorithm 1 verbatim.
2. `prompts.py` — five prompt templates from paper §D.1 (initial,
   recursive-downward, leaf-backtrack, non-leaf-completion, leaf-failure).
3. `state.py` — context tree, sliding window K=64, JSON `{think, subtasks}`
   schema validation.
4. `router_adapter.py` — wraps `arail.router.ModelRouter.complete()` with
   multi-turn history support. Extension only — backends untouched.
5. Tests against a mocked Robotouille-shaped env fixture.
6. Cost telemetry: add `recap_depth` field to `arail.cost_tracker`.

**Out of scope:** integration with the Researcher agent (that is Sprint 2).
No changes to backends. No UI surface.

**Exit criterion:** unit tests green; passes Robotouille-shaped fixture
at parity with paper expectations (success on a known task within step
budget).

## Phases

| Phase | Subagent | Artifact | Status | Started | Finished | Verdict |
|---|---|---|---|---|---|---|
| think | visionary | VISION.md | **skipped** | — | — | covered by approved plan |
| plan | architect (design) | ARCHITECTURE.md | done | 2026-05-17 | 2026-05-17 | proceed |
| build | builder | BUILD_LOG.md | done | 2026-05-17 | 2026-05-17 | 8 commits, 142 new tests, suite green |
| review | architect (review) | REVIEW.md | done | 2026-05-17 | 2026-05-17 | WEAK_PASS (2 non-blocking carryovers) |
| test | qa | TEST_REPORT.md | done | 2026-05-17 | 2026-05-17 | PASS (32 new tests, 1644/1657, 0 new regressions) |
| ship | — | PR | in-progress | 2026-05-17 | — | — |

## Decisions log

| Date | Decision | Rationale |
|---|---|---|
| 2026-05-17 | Skip visionary phase | Plan file `i-feel-like-we-radiant-snail.md` covers vision (win condition, scope, AeroLLM/qukaizen exclusion). User explicitly approved scope. |
| 2026-05-17 | QA allocation adjusted | This is a framework module, not a user-facing surface. Default ARAIL QA mix (30% setup / 30% Buddy / 20% security / 10% happy / 10% regression) doesn't fit. Shift to: 60% algorithm correctness (sliding window, re-injection invariant, plan-ahead semantics), 20% edge cases (malformed JSON, depth limits, env failures), 10% cost ceiling (assert recap_depth tracked + total cost bounded), 10% regression (no churn in router/cost_tracker for non-recap callers). |

## Skipped phases

| Phase | Reason |
|---|---|
| think | Vision and scope already established and user-approved in plan file. |

## Notes
- Reference paper sections: §2 (framework), §D.1 (prompts), §A (retry/truncation), Algorithm 1 (figure 2).
- ARAIL package internal name stays `arail`. No rebrand-breaking imports.
- ReCAP code must remain model-agnostic — works against MLX, AirLLM, AeroLLM, cloud uniformly via ModelRouter.
