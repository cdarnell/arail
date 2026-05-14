# Sprint: airgap-onetap-toggle

**ID:** 2026-05-14-airgap-onetap-toggle
**Started:** 2026-05-14T18:51:02Z
**Product:** arail

## Task

Simplify the Network policy airgap toggle to a true one-click toggle. The
current implementation (sprint `2026-05-07-airgap-runtime-toggle`) locks up
the UI with a 3-second forced confirm countdown, a two-step confirm-token
protocol, a modal close-and-reopen dance, and stale in-process `LAB_MODE`
caches that don't reflect the new mode without process restart.

**Scope:**
1. Collapse `POST /api/airgap/toggle` from 2-step token protocol to 1-step
   (CSRF Origin + loopback-bind gates already cover the threat the
   confirm-token was meant to address).
2. Replace the confirm-countdown UI in
   `src/arail/portal/templates/_airgap_modal.html` and
   `src/arail/portal/static/nav.js` with a single segmented control or
   switch that flips optimistically and reverts on error.
3. Bust cached `lab_mode()` lookups in `arail.airgap` and `arail.egress`
   so the portal reflects the new mode without process restart.
4. Keep intact: audit-log append, `.env` atomic write, loopback-bind gate,
   CSRF Origin gate.

**Out of scope:** subprocess restart of AirLLM / researcher workers
(document as known limitation in the modal copy).

## Phases

| Phase | Subagent | Artifact | Status | Started | Finished | Verdict |
|---|---|---|---|---|---|---|
| think | visionary | VISION.md | skipped | — | — | — |
| plan | architect (design) | ARCHITECTURE.md | done | 2026-05-14T18:51Z | 2026-05-14T18:55Z | proceed |
| build | builder | BUILD_LOG.md | done | 2026-05-14T18:55Z | 2026-05-14T19:35Z | 8 commits, 73/73 airgap tests pass |
| review | architect (review) | REVIEW.md | done | 2026-05-14T19:35Z | 2026-05-14T19:40Z | PASS |
| test | qa | TEST_REPORT.md | done | 2026-05-14T19:40Z | 2026-05-14T19:55Z | PASS (after cleanup pass) |
| ship | — | PR | pending | — | — | — |

## Decisions log

| Date | Decision | Rationale |
|---|---|---|
| 2026-05-14 | Skip visionary phase | Bug fix with obvious win condition: existing surface is locking up the lab; user has explicitly chosen one-tap UX and called this a critical fix. No strategic ambiguity to resolve. |

## Skipped phases

| Phase | Reason |
|---|---|
| think | Bug fix with obvious win condition; user-directed scope is concrete. |

## Notes

- Prior sprints establish the security baseline:
  `sprints/2026-05-05-airgap-honest-mode/` (egress guard + audit log)
  and `sprints/2026-05-07-airgap-runtime-toggle/` (the current 2-step
  toggle being simplified). Architect should read both REVIEW.md files
  before designing; do not relitigate what's already settled.
- Per `arail/CLAUDE.md` QA allocation: 30% setup / 30% Buddy / 20% security
  / 10% happy / 10% regression. **Security tests are mandatory** and must
  cover: rapid double-click race, CSRF cross-origin attempt, non-loopback
  bind attempt, audit-log line emitted per flip.
- Affected files (working set):
  - `src/arail/portal/app.py` — `/api/airgap/toggle` (lines ~6982–7090)
    and `/api/airgap/status` (lines ~6810–6868)
  - `src/arail/portal/templates/_airgap_modal.html`
  - `src/arail/portal/static/nav.js` (lines ~131–396)
  - `src/arail/airgap.py` / `src/arail/egress.py` — cache invalidation
  - `src/arail/env_writer.py` — atomic write (preserve, do not touch)
- Branch: continue on `qukaizen/arail-experiment-branches` only if it's
  empty of unshipped commits the architect needs to coordinate with;
  otherwise architect should recommend a fresh branch
  `qukaizen/arail-airgap-onetap`.

## How to resume this sprint

If interrupted, run:
```
cat sprints/2026-05-14-airgap-onetap-toggle/SPRINT.md
```
Then continue from the next pending phase row.
