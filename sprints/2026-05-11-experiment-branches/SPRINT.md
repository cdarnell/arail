# SPRINT — 2026-05-11-experiment-branches

**Title:** Surface autoresearch git branches in the Research tab
**Branch:** qukaizen/arail-experiment-branches (off main 25df4b0)
**Date opened:** 2026-05-11
**Status:** Builder pending

## One-line thesis

ARAIL is A-rail for experiments. Every experiment is a git branch. If you can measure it, we can improve it. The branches already exist — this sprint makes them visible in `/research`.

## Phase ledger

| Phase | Status | Artifact | Notes |
|---|---|---|---|
| 1. Visionary | ✅ Done | `VISION.md` | User directive + win condition captured. |
| 2. Architect (design) | ✅ Done | `ARCHITECTURE.md` | Approved plan dropped in. Scope is locked: tuning loop only, read-only, rebrand-included. |
| 3. Builder | ⏳ Next | `BUILD_LOG.md` | Implement per `ARCHITECTURE.md`. Atomic commits. Tests alongside. |
| 4. Architect (review) | ⏳ Pending | `REVIEW.md` | Paranoid review against the failure modes documented in ARCHITECTURE.md § Risks. |
| 5. QA | ⏳ Pending | `TEST_REPORT.md` | arail QA gating: 30% setup / 30% Buddy / 20% security / 10% happy / 10% regression. For this sprint: heavier emphasis on **security** (branch-name injection, path traversal) and **regression** (git_ops safety tests must still pass). |
| 6. Ship | ⏳ Pending | PR | Branch is off main; PR target is main. |

## Out-of-band context

- The prior chat-model-fix sprint (`sprints/2026-05-11-chat-model-fix/`) is mid-flight on branch `qukaizen/arail-min-cloud-first`. Its WIP (modified SPRINT.md + untracked ARCHITECTURE.md + REVIEW.md) is in the stash, message `"WIP: chat-model-fix sprint artifacts"`. Resume with `git checkout qukaizen/arail-min-cloud-first && git stash pop` when ready.
- The newer chat-model-sync sprint (`sprints/2026-05-10-chat-model-sync/`) merged to main as PR #44 — we're working on top of that.

## Decisions captured before build start

- **Scope:** tuning loop only (the Researcher agent's 6-step loop will be wired in a follow-up sprint).
- **Read-only:** no delete/archive/checkout buttons on branches.
- **Rebrand:** replace the Research tab tagline and empty-state copy. Do NOT rename routes, nav items, or the internal `arail` package.
- **No new design tokens:** reuse existing `.rx-pill`, `.rx-event`, `.rx-metric`, `.rx-chip`, `.compute-opt` patterns.

## Open items

None blocking. The bench JSONL schema verification (`git_branch` field present in `append_run`?) is the only conditional decision; builder resolves on first read of `bench.py`.

## How to resume this sprint

If interrupted, run:
```
git checkout qukaizen/arail-experiment-branches
cat sprints/2026-05-11-experiment-branches/SPRINT.md
```
Then continue from the next unticked phase row.
