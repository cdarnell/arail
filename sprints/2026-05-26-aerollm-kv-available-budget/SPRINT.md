# Sprint: aerollm-kv-available-budget

**ID:** 2026-05-26-aerollm-kv-available-budget
**Started:** 2026-05-26
**Product:** arail

## Task

Improve `AeroLLMBackend`'s KV cache budget so it honors *actually-available* system RAM, not just `psutil.virtual_memory().total × 0.60`. Today, on a 36 GB box already running Ollama (~5 GB) + Chrome (~3 GB) + portal (~1 GB), the runtime is told it owns 21.6 GB for KV — overrunning what's truly free and pushing the box toward swap/OOM. The user has hit OOM here before ([project_oom_pressure.md](../../../.claude/projects/-Users-netsushi-ProJects-arail/memory/project_oom_pressure.md)). Surfaced during the 2026-05-25 chat-2nd-inference-works sprint when the user observed Python at 27 GB resident after a single Box B query.

Desired shape (architect to refine):

```
budget = max(MIN_FLOOR, min(total * KV_PCT, available * 0.85 - SAFETY_HEADROOM))
```

with `MIN_FLOOR ≈ 2 GB`, `SAFETY_HEADROOM ≈ 1.5 GB`, env override `AEROLLM_KV_BUDGET_PCT` preserved, resolved budget logged via `activity_log` on backend init.

## Phases

| Phase | Subagent | Artifact | Status | Started | Finished | Verdict |
|---|---|---|---|---|---|---|
| think | visionary | VISION.md | skipped | — | — | bug fix; win condition obvious |
| plan | architect (design) | ARCHITECTURE.md | completed | 2026-05-26 | 2026-05-26 | proceed |
| build | builder | BUILD_LOG.md | completed | 2026-05-26 | 2026-05-26 | done |
| review | architect (review) | REVIEW.md | completed | 2026-05-26 | 2026-05-26 | BLOCK → loop to build |
| build (revise) | builder | BUILD_LOG.md (append) | completed | 2026-05-26 | 2026-05-26 | BLOCK items cleared; tests 14a+14b added |
| test | qa | TEST_REPORT.md | in_progress | 2026-05-26 | — | — |
| test | qa | TEST_REPORT.md | pending | — | — | — |
| ship | — | PR | pending | — | — | — |

## Decisions log

| Date | Decision | Rationale |
|---|---|---|
| 2026-05-26 | Skip visionary | Bug fix with explicit shape; win condition = "KV budget never exceeds what's actually free, never starves a healthy box, env override still works" |
| 2026-05-26 | Branch off `qukaizen/arail-chat-md-render` head (commit `22b9688`) | Continuous with the just-shipped chat fix; the chat-md-render WIP on this branch is unrelated and won't conflict with backends.py changes |

## Skipped phases

| Phase | Reason |
|---|---|
| think (visionary) | Bug fix with obvious win condition; user asked to "knock it out" |

## Notes

- Per ARAIL CLAUDE.md, this is an `arail` product sprint, so QA shifts to 30% setup / 30% Buddy / 20% security / 10% happy / 10% regression — but for a runtime allocation fix the relevant slices are happy-path + edge (OOM, psutil failure, env override). Architect to call out test allocation in ARCHITECTURE.md.
- Sibling `aerollm` repo also has a KV budget concept (the runtime's own auto-detect at 80%). This sprint changes how ARAIL *constructs* the budget kwarg it passes in; it does NOT touch the aerollm Rust runtime itself.
