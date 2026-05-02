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
| plan | architect (design) | ARCHITECTURE.md | completed | 2026-05-01 | 2026-05-01 | ready to build |
| build | builder | BUILD_LOG.md | completed | 2026-05-01 | 2026-05-01 | 10 implementation commits + 1 BUILD_LOG fixup; ~2423 LOC |
| review | architect (review) | REVIEW.md | in_progress | 2026-05-01 | — | — |
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
| 2026-05-01 | Approved 2 architect deviations | (1) Drop new `/docs/{name}` route — existing `/docs/{path:path}` at app.py:1409-1433 already serves `.md` files with traversal protection. (2) Add a sixth `inference_slot` wrap at app.py:3532 — the synchronous default chat path the plan missed; biggest source of the lag symptom. Severity-flattening in SRE emit (architect deviation 3) deferred as post-ship follow-up. |
| 2026-05-01 | Commit cadence | Builder commits per sequencing step (8 commits total). Pre-commit hooks run; do not skip. |
| 2026-05-01 | Scope add — `/health` + `/metrics` | User added mid-sprint: top-level `/health` (with `/healthz` alias) for liveness probes (nginx, k8s, Cloudflare) and `/metrics` for Prometheus exposition. Both bypass onboarding gate (industry standard). Architect extended ARCHITECTURE.md with full design (lines 842-966). Builder lands as commit #10 before review. No new deps — Prometheus format hand-rolled. PUBLISH.md gets a reverse-proxy restriction subsection. |

## Skipped phases

| Phase | Reason |
|---|---|
| think (visionary) | Win condition obvious; user already approved a plan with locked decisions. |

## Notes

- ARAIL product gating (per arail/CLAUDE.md): setup-on-clean-machine, Buddy quality, security (runs on others' machines), onboarding clarity, failure-mode grace.
- QA allocation for ARAIL: 30% setup / 30% Buddy / 20% security / 10% happy / 10% regression.
- Architect should treat the approved plan as the design intent and produce ARCHITECTURE.md with explicit failure modes, test strategy, tech-debt assessment — sections the plan file does not have.
