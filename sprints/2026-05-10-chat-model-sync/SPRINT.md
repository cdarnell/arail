# Sprint: chat-model-sync

**ID:** 2026-05-10-chat-model-sync
**Started:** 2026-05-10
**Product:** arail

## Task

Fix model selection in the chat tab so that the UI is ground-truth synced with
what actually exists and gets called. Three interlocking issues:

1. **AirLLM must be invisible to regular users.** On MLX/Apple Silicon it must
   be completely absent. It may only surface if `ARAIL_DEV_AIRLLM=1` is set, and
   never on arm64 regardless.
2. **Model dropdown must only show installed models.** No phantom catalog entries
   in the picker. If a model isn't on the filesystem / in ollama tags, it's not
   in the list.
3. **UI chip must match what the backend actually calls.** `d.current` must be
   derived from the live Ollama state, not a stale env var.
4. **Deep backend size threshold drops from 35B to 30B.** Models >30B total
   params → aeroLLM only (never airllm).
5. **Default Model A = `ai-engineer:latest`.** Scaffold an Ollama Modelfile
   (qwen3:8b base, AI Engineer Expert persona) bundled in `models/` directory,
   wired into setup.

## Phases

| Phase | Subagent | Artifact | Status | Started | Finished | Verdict |
|---|---|---|---|---|---|---|
| think | visionary | VISION.md | skipped | — | — | — |
| plan | architect (design) | ARCHITECTURE.md | done | 2026-05-10 | 2026-05-10 | complete |
| build | builder | BUILD_LOG.md | done | 2026-05-10 | 2026-05-10 | complete (1adb527) |
| review | architect (review) | REVIEW.md | done | 2026-05-10 | 2026-05-10 | PASS |
| test | qa | TEST_REPORT.md | done | 2026-05-10 | 2026-05-10 | PASS (95 sprint, 1037 repo, 0 regressions) |
| ship | — | PR | in-progress | 2026-05-10 | — | — |

## Decisions log

| Date | Decision | Rationale |
|---|---|---|
| 2026-05-10 | Skip visionary | Bug fix sprint with explicit win conditions; no strategic question |
| 2026-05-10 | AirLLM gated behind ARAIL_DEV_AIRLLM=1, never on arm64 | User requirement: invisible to regular users; Metal GPU timeout is a dead end on MLX |
| 2026-05-10 | AI Engineer Modelfile scaffolded from qwen3:8b | User chose "scaffold now"; Project Nucleus version replaces system prompt later |
| 2026-05-10 | Size threshold 35B→30B | User requirement: anything >30G is aeroLLM-only |

## Skipped phases

| Phase | Reason |
|---|---|
| think | Bug fix with obvious win condition — no strategic question |

## Notes

- Plan file: `/Users/netsushi/.claude/plans/serene-noodling-patterson.md`
- Key files: `src/arail/model_specs.py`, `src/arail/portal/app.py`,
  `src/arail/portal/templates/chat.html`, `src/arail/portal/templates/chat.legacy.html`,
  `src/arail/chat/models_catalog.yaml`, new `models/ai-engineer.Modelfile`,
  `scripts/setup.sh`
- QA allocation per arail CLAUDE.md: 30% setup / 30% Buddy / 20% security / 10% happy / 10% regression
  → adapt here: 40% model-sync correctness / 30% platform-gating / 20% UI picker / 10% regression
