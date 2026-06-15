# Sprint: ARAIL Two-Tier Model Architecture

**ID:** 2026-06-14-arail-two-tier-models  
**Started:** 2026-06-14T08:30:00Z  
**Product:** arail

## Task

Design and validate ARAIL's two-tier model architecture: Minimalist (TinyLlama 1.1B, default, offline) and Maximus (Mistral 7B-Q2, optional, AeroLLM layer-streaming). Goal is to get model selection RIGHT for users — default tier should be trustworthy and fast, Maximus tier should be clearly positioned for power users who need deeper reasoning. No regrets after ship.

## Phases

| Phase | Subagent | Artifact | Status | Started | Finished | Verdict |
|---|---|---|---|---|---|---|
| think | visionary | VISION.md | done | 2026-06-14T08:30Z | 2026-06-14T08:45Z | **Proceed with model correction** |
| plan | architect (design) | ARCHITECTURE.md | done | 2026-06-14T08:45Z | 2026-06-14T09:25Z | **10 findings identified** (F1 critical: Ollama install gate) |
| build | builder | BUILD_LOG.md | done | 2026-06-14T09:25Z | 2026-06-14T10:55Z | **6 commits, 17 tests, all pass** |
| review | architect (review) | REVIEW.md | done | 2026-06-14T10:55Z | 2026-06-14T11:20Z | **WEAK_PASS** (F8 display: data-present, UI-missing) |
| test | qa | TEST_REPORT.md | done | 2026-06-14T11:20Z | 2026-06-14T12:50Z | **WEAK_PASS** (hard gates ✓, flaky test + 16GB unvalidated) |
| ship | — | PR | ready | 2026-06-14T12:50Z | — | **Merge-ready with known gaps** |

## Decisions log

| Date | Decision | Rationale |
|---|---|---|
| 2026-06-14 | **Corrected model choices** | Visionary flagged: ARAIL v1.1 CLAUDE.md already ships better choices (Llama-3.2-1B minimalist, Qwen2.5-7B maximus). TinyLlama is regression; Q2 Mistral ruins reasoning quality. Proceeding with v1.1 models, not the proposed TinyLlama/Mistral-Q2. |

## Skipped phases

| Phase | Reason |
|---|---|

## Notes

- Critical: User model selection must inspire confidence. No surprises after deployment.
- Minimalist tier: TinyLlama 1.1B (proven lightweight, respects offline-first philosophy)
- Maximus tier: Mistral 7B-Q2 (2.2GB, good balance of capability and size for AeroLLM streaming)
- Future: Mixtral 8x22B option documented but not in v1 (requires 24GB+ VRAM, needs validation)
- AeroLLM handles layer-by-layer streaming (Maximus doesn't need full VRAM load)
