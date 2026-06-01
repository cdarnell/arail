# Sprint: model-hosting-reframe

**ID:** 2026-05-30-model-hosting-reframe
**Started:** 2026-05-30 16:16
**Product:** arail

## Task
Reframe ARAIL's model hosting strategy. (1) Replace the 70B/405B AirLLM
maximus deep-mode default with a quick-download 20–30B open-model slot,
exact ID left as a marked TODO placeholder (70B too heavy on 36GB until
MoE/efficiency lands). (2) "Bottle" ai-eng as the universal auto-install
default: a 3B Opus-distilled AI-engineering model (qwen2.5:3b base + our
LoRA adapters) published as the Ollama tag `qukaizen/ai-eng:3b` with LoRA
baked in — setup just pulls it; drop the qwen2.5:7b preview-fallback
framing and the dual Modelfile dance. (3) Do not advertise the qwen part
anywhere possible — strip qwen2.5 mentions from catalog, README,
CHANGELOG, CLAUDE.md, docs, code comments; keep qwen only in the
unavoidable internal Modelfile FROM/base line. Constraints: airgapped
default unchanged; OOM-sensitive (no heavy auto-downloads); ai-eng is the
only auto-install; 20–30B deep model is maximus quick-download.

## Phases

| Phase | Subagent | Artifact | Status | Started | Finished | Verdict |
|---|---|---|---|---|---|---|
| think | visionary | VISION.md | done | 16:16 | 16:18 | proceed |
| plan | architect (design) | ARCHITECTURE.md | done | 16:18 | 16:30 | complete (rev2: self-host) |
| build | builder | BUILD_LOG.md | done | 16:30 | 16:45 | done (9 commits, no regressions) |
| review | architect (review) | REVIEW.md | done | 16:45 | 16:52 | WEAK_PASS |
| test | qa | TEST_REPORT.md | done | 16:52 | 17:08 | WEAK_PASS |
| ship | — | PR #75 | done | 17:10 | 17:12 | PR opened to main |

## Decisions log

| Date | Decision | Rationale |
|---|---|---|
| 2026-05-30 | Deep-model ID left as TODO placeholder | User will pick the exact 20–30B model later |
| 2026-05-30 | ai-eng = published Ollama tag (LoRA baked in) | No local adapter merge; setup just pulls `qukaizen/ai-eng:3b` |
| 2026-05-30 | Ollama tag `qukaizen/ai-eng:3b` NOT published (404 verified by architect) | Pivot: self-host the bottled model on HuggingFace / GitHub release / qukaizen.com; setup pulls from the chosen host instead of the ollama.ai registry namespace |
| 2026-05-30 | Hide qwen everywhere possible | Keep only the unavoidable Modelfile FROM line |
| 2026-05-30 | Full /sprint pipeline | Strategic model-hosting change per CLAUDE.md gating |

## Skipped phases

| Phase | Reason |
|---|---|

## Notes
- arail QA allocation: 30% setup / 30% Buddy / 20% security / 10% happy / 10% regression.
- arail ship gate also requires a setup-on-clean-machine consideration.
