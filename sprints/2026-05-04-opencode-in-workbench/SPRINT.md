# Sprint: opencode-in-workbench

**ID:** 2026-05-04-opencode-in-workbench
**Started:** 2026-05-04
**Product:** arail

## Task

Add opencode (`sst/opencode`, MIT, Go) as a max-tier-only surface inside the renamed Workbench tab (formerly Notebooks) of the ARAIL portal. opencode becomes "the way you change the lab without leaving the lab" — paired with a small local code model via the existing Compute Source pivot. Sprint 1 of two from the approved plan at `~/.claude/plans/also-want-to-consider-synthetic-wreath.md`. Sprint 2 (Skills folded into Agents) is queued separately.

## Phases

| Phase | Subagent | Artifact | Status | Started | Finished | Verdict |
|---|---|---|---|---|---|---|
| think | visionary | VISION.md | skipped | — | — | — |
| plan | architect (design) | ARCHITECTURE.md | done | 2026-05-04 | 2026-05-04 | proceed (revised after kickoff probes; commit 50ce5ad) |
| build | builder | BUILD_LOG.md | done | 2026-05-04 | 2026-05-04 | 6 commits (final 14fba3b), 41 new tests green |
| review | architect (review) | REVIEW.md | done | 2026-05-04 | 2026-05-04 | PASS (0 BLOCK, 0 ASK, 2 INFO style polish) |
| test | qa | TEST_REPORT.md | done | 2026-05-04 | 2026-05-04 | PASS — 38 new QA tests, 0 defects, 590 suite passing, no new regressions; live `lsof` confirmed 127.0.0.1 binding |
| ship | — | PR | done | 2026-05-04 | 2026-05-04 | PR #34 open against main from `qukaizen/arail-opencode-in-workbench` (cherry-picked clean off origin/main) |

## Decisions log

| Date | Decision | Rationale |
|---|---|---|
| 2026-05-04 | Skip visionary phase | User and orchestrator already completed a full planning round with explicit user-question round (tab name = Workbench, sprint shape = two sprints opencode-first). Win condition, wedge, and displacement are documented in the approved plan. VISION.md would be a paraphrase. |
| 2026-05-04 | Tab name: Workbench (not IDE/Studio/Notebooks) | User selected Workbench from a 4-option AskUserQuestion. Rationale: names the room, not any one tool; sidesteps IDE/notebookLM namespace overlap. |
| 2026-05-04 | Two sprints, opencode first | User selected this option from a 3-option AskUserQuestion. opencode is higher-leverage and higher-risk; gets dedicated architect + qa attention. |
| 2026-05-04 | Reverse-proxy pattern (Option B) for opencode | Plan recommendation: keeps basic-auth password server-side, satisfies CSP, deep-links cleanly. New pattern for this codebase but small (~40 lines in opencode.py). |
| 2026-05-04 | **REVERSED** — adopt direct-iframe pattern (Option A) instead of reverse proxy | Kickoff probe: opencode `GET /` returns SPA with strict CSP `default-src 'self'` and root-absolute asset paths (`/favicon-…`, presumably `/assets/*.js`). A `/opencode/proxy/` mount can't serve the SPA without rewriting the bundle; in-app `fetch()` calls can't be reached by HTML rewriting. Existing lab pattern (Jupyter/Marimo/Open-Notebook iframe-direct) has equivalent code-execution capability — applying a stricter perimeter only to opencode is theater. Lab's real trust boundary is "127.0.0.1 = trusted." `OPENCODE_SERVER_PASSWORD` not set. Architect revised ARCHITECTURE.md (commit 50ce5ad), verdict PROCEED. Routes drop from 4 to 3 (no `/opencode/proxy/*`); `httpx` dep dropped. |
| 2026-05-04 | Readiness probe: `GET /doc` (not `/healthz`) | OpenAPI lists only `/auth/{providerID}` PUT/DELETE and `/log` POST — no `/healthz`. `/doc` returns the OpenAPI JSON; small and unambiguous. |
| 2026-05-04 | Explicit `--port 4096` (opencode default is 0/random) | opencode `serve --port` defaults to 0 (OS-assigned). Plan/architect assumed 4096; must pass explicitly. |
| 2026-05-04 | F-IFRAME-3 resolved at orchestrator layer (no X-Frame-Options) | Probe confirms opencode emits no `X-Frame-Options` header and CSP omits `frame-ancestors`. Direct iframe is permitted. Builder unblocked from architect's "verify as step 1" caveat. |
| 2026-05-04 | opencode is max-only via piggybacking on `notebooks` surface | No new key in `_TIER_SURFACES`. `/opencode*` routes gate on `"notebooks" in _visible_surfaces()`. Falls out for free since the Workbench tab itself is max-only. |

## Skipped phases

| Phase | Reason |
|---|---|
| think | Win condition already established via approved plan + user-question round. See Decisions log. |

## Notes

- Approved plan: `/Users/netsushi/.claude/plans/also-want-to-consider-synthetic-wreath.md`
- Default model recommendation: Qwen3-Coder-30B-A3B-Instruct (Apache-2.0, MoE 30B/3.3B-active, 256K ctx). Doc-only; opencode picks up whatever Compute Source serves.
- Per arail/CLAUDE.md, QA allocation: 30% setup / 30% Buddy / 20% security / 10% happy / 10% regression. **Security carried extra weight this sprint** because (a) the auth/proxy design was dropped after kickoff probes — trust model became "127.0.0.1 = trusted, same as Jupyter/Marimo" and (b) opencode can edit arbitrary repo files (max-tier gate had to be airtight on all three remaining routes).
- **Branch note:** sprint commits landed on `qukaizen/arail-airllm-subprocess-isolation` (the working branch at sprint kickoff), not on `qukaizen/arail-models-admin-dashboard` (the session-start banner). Opencode commits c7eaf48..6af38e9 + 325910b are clean and isolated to opencode-related files; airllm WIP on this branch is independent and untouched.

## Sprint 2 follow-up candidates

Tracked here for the next sprint's intake; none block ship of this one.

1. **`/api/system/health` info-disclosure (QA INFO #1).** The endpoint reports `services["opencode"]` to all callers regardless of tier — same behavior as marimo/open-notebook/neo4j etc. Not opencode-specific; gating only opencode would be inconsistent. Cross-cutting redesign of the health endpoint (filter optional services by tier) is the right fix. Ticket separately.
2. **`PRIVACY.md` trust-model note** (architect F-SEC-6 follow-up). One-paragraph doc addition: "the lab's trust boundary is 127.0.0.1 — anyone reaching localhost can shell the host." Keep simple.
3. **opencode version probe** (F-INSTALL-2, builder deferral). If a user has an old opencode without `serve` subcommand, error is opaque subprocess failure. Add a one-line `opencode --version` parse on first start.
4. **Token redaction in opencode logs** (F-SEC-4, builder deferral). opencode writes its own logs (`lab/logs/opencode.log`) which may contain provider tokens it received via env. Redact at write time or rotate aggressively.
5. **`os.setsid` cleanup** (F-PROC-3, builder deferral). If portal SIGKILLs, opencode subprocess orphans. Add `os.setsid` so portal SIGTERM cascades.
6. **Sprint 2 — Skills folded into Agents.** From the approved plan; queued.
