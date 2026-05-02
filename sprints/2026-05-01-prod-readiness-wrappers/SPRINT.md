# Sprint: prod-readiness-wrappers

**ID:** 2026-05-01-prod-readiness-wrappers
**Started:** 2026-05-01
**Product:** arail
**Branch:** qukaizen/arail-prod-readiness (off main, fast-forwarded to origin/main 89bbcda)

## Task

ARAIL is about to be released as a product. The user already runs an instance at qukaizen.com. Three pain points need wrappers before ship:

1. **Performance** — chat/local-LLM inference starves lightweight tab polling (dashboard, knowledge, agents). No semaphore, queue, or rate-limit middleware exists today.
2. **Security** — Mythos-class adversarial LLMs make any internet-exposed lab a target. No CVE scanning, no `/admin` security surface.
3. **Operator runbook** — no `docs/PUBLISH.md` for users who want to publish their own lab the way the user did with qukaizen.com.

Sprint adds: an in-process inference priority queue (Phase 1; uvicorn worker isolation Phase 2 deferred), a "Production Readiness" admin section (Performance / Cleanup / Security cards) with `/api/admin/{perf,cleanup,security}/*` endpoints, two new SRE watchers (CVE + lab-cleanup), a hybrid-mode boot scan, and a deployment guide.

Approved plan seed: `/Users/netsushi/.claude/plans/i-have-the-site-tranquil-milner.md`. Note: line references in that plan are stale by ~210 lines in app.py and ~9 in admin.html due to the post-plan rebase against origin/main — architect must re-verify.

## Phases

| Phase | Subagent | Artifact | Status | Started | Finished | Verdict |
|---|---|---|---|---|---|---|
| think | visionary | VISION.md | skipped | — | — | — |
| plan | architect (design) | ARCHITECTURE.md | in_progress | 2026-05-01 | — | — |
| build | builder | BUILD_LOG.md | pending | — | — | — |
| review | architect (review) | REVIEW.md | pending | — | — | — |
| test | qa | TEST_REPORT.md | pending | — | — | — |
| ship | — | PR | pending | — | — | — |

## Decisions log

| Date | Decision | Rationale |
|---|---|---|
| 2026-05-01 | Skip visionary | User has a concrete, validated framing (release wrapper) and an approved plan file with locked decisions — no strategic ideation needed. Per workspace CLAUDE.md "skip visionary when win condition is obvious." |
| 2026-05-01 | Phase 1 perf only | User chose "queue now, worker isolation as phase 2." Architect must call out worker isolation as a follow-up sprint, not build it. |
| 2026-05-01 | `pip-audit` opt-in | Goes in `[project.optional-dependencies] security`, not base. `LAB_MODE=airgapped` stays default; no involuntary outbound calls. |
| 2026-05-01 | Auto-remediation = suggest only | CVE findings surface a one-click "install fix" suggestion; never auto-applied. |
| 2026-05-01 | Branch off main | Committed `knowledge: kb CLI + terminal/dashboard polish` on qukaizen/knowledge-ux-quirky-whisper first; this sprint is on a fresh branch off rebased main. |

## Skipped phases

| Phase | Reason |
|---|---|
| think (visionary) | Win condition obvious; user already approved a plan with locked decisions. |

## Notes

- ARAIL product gating (per arail/CLAUDE.md): setup-on-clean-machine, Buddy quality, security (runs on others' machines), onboarding clarity, failure-mode grace.
- QA allocation for ARAIL: 30% setup / 30% Buddy / 20% security / 10% happy / 10% regression.
- Architect should treat the approved plan as the design intent and produce ARCHITECTURE.md with explicit failure modes, test strategy, tech-debt assessment — sections the plan file does not have.
