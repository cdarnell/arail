# Sprint: airgap-runtime-toggle

**ID:** 2026-05-07-airgap-runtime-toggle
**Started:** 2026-05-07
**Product:** arail
**Branch:** `qukaizen/arail-airgap-runtime-toggle` (cut from `origin/main` @ a77dc2c, post-PR-#36)

## Task

Make `LAB_MODE` togglable from the Network Policy modal — without
editing `.env` and restarting. The airgap-honest-mode sprint (PR #35)
shipped the modal as informational only; the only mechanism to flip
airgapped ↔ hybrid today is hand-editing `.env`. User feedback:
*"This is fundamental to all ARAIL modes. The toggle has to be in the
UI."*

This sprint adds the **persistent** toggle (option B):

1. Backend endpoint `POST /api/airgap/toggle` (or similar) that:
   - Updates `os.environ["LAB_MODE"]` so the change takes effect
     immediately for read-on-every-call sites
     (`arail.airgap.lab_mode()` reads `os.getenv` per call).
   - Rewrites the `LAB_MODE=` line in the user's `.env` so it survives
     restart.
   - Emits an activity-log line + nudges Buddy's airgap watcher.
2. Frontend: a toggle button in `_airgap_modal.html` calling that
   endpoint, with a "are you sure" confirmation since this changes
   the security posture.
3. Concurrency: file-write race-free `.env` rewriter (atomic temp +
   rename). No data loss on power-cut mid-write.
4. Security: confirm threat model. The portal binds to localhost by
   default; should this endpoint require any auth beyond that? Probably
   no — same threat model as the rest of the portal — but architect
   reviews.
5. Tests: backend toggle, `.env` writer edge cases (comments,
   missing line, quoted values), frontend interaction smoke.

## Phases

| Phase | Subagent | Artifact | Status | Started | Finished | Verdict |
|---|---|---|---|---|---|---|
| think | visionary | VISION.md | done | 2026-05-07 | 2026-05-07 | proceed (with 2 non-negotiable constraints) |
| plan | architect (design) | ARCHITECTURE.md | pending | — | — | — |
| build | builder | BUILD_LOG.md | done | 2026-05-07 | 2026-05-07 | 9 commits, 111 tests pass |
| review | architect (review) | REVIEW.md | done | 2026-05-07 | 2026-05-07 | WEAK_PASS — 3 documented follow-ups |
| test | qa | TEST_REPORT.md | pending | — | — | — |
| ship | — | PR | pending | — | — | — |

## Decisions log

| Date | Decision | Rationale |
|---|---|---|
| 2026-05-07 | Persist to `.env` (option B), not in-memory only | User explicitly chose persistence. Toggle that doesn't survive restart is a footgun in airgapped mode (lab silently re-airgaps after restart). |
| 2026-05-07 | Branch cut fresh from origin/main | Independent of `qukaizen/arail-opencode-curation` (in flight, stashed). |
| 2026-05-07 | Stash protocol | 2 stashes parked: `stash@{0}` (PKB sre + compiled README), `stash@{1}` (27 src files), both tied to opencode-curation branch. Restore on return. |
| 2026-05-07 | Canonical config file = `.env` (project root, chmod 600), NOT `secrets.env` | All docs (README, INSTALL, PRIVACY) consistently reference `.env` for `LAB_MODE`. `secrets.env` is for API tokens only. Visionary flagged the ambiguity; orchestrator audited and resolved. |
| 2026-05-07 | Two non-negotiable architect constraints (per visionary) | (a) bind-address gate — refuse the toggle endpoint if the portal binds to `0.0.0.0`. (b) Two-step modal-confirm UX — single-click is a footgun. |

## Skipped phases

| Phase | Reason |
|---|---|
| (none) | full pipeline — security-relevant change (flips network policy) |

## Notes

- Buddy's airgap watcher (`_watch_airgap_events`) already detects
  `LAB_MODE` toggle by comparing `lab_mode()` to a cached value in
  `state.json`. The toggle endpoint should set the env var BEFORE
  emitting the activity-log line so the next watcher tick sees the
  new mode.
- The QA pass should hammer .env write race conditions and the
  "single-click toggle" UX. Per arail product gating: 30% setup,
  30% Buddy, 20% security, 10% happy, 10% regression.
- PR #35 (airgap-honest-mode) and PR #36 (docs refresh) both merged
  before this sprint started; all helpers (`arail.airgap`,
  `arail.egress`) are available.
