# Sprint: ai-eng-v2.1

**ID:** 2026-05-18-ai-eng-v2.1
**Started:** 2026-05-18
**Product:** arail
**Branch:** qukaizen/arail-ai-eng-v2.1

## Task

Ship `qkz-opus4.7-aieng-3b-v2.1` as ARAIL's default lab model and lift the AeroLLM
maximus-tier secondary to `mlx-community/Qwen2.5-72B-Instruct-4bit`.

QuKaiZen's Project Nucleus has published the v2.1 weights as a LoRA adapter at
`huggingface.co/qukaizen/qkz-opus4.7-aieng-3b-v2.1-adapter` (LoRA r=16, alpha=16,
trained against `mlx-community/Qwen2.5-3B-Instruct-4bit`). Today setup.sh falls
back to `qwen2.5:7b` + an AI Engineer persona Modelfile because the 3B production
weights weren't published. This sprint closes that gap end-to-end: merge the
adapter, bench against both 4-bit-fused and bf16-merged candidates, publish to
HF + Ollama registry, then wire setup.sh / pyproject.toml / catalog so the
`./arailctl setup` first-run no longer fires the fallback warning. Simultaneously,
lift the AeroLLM maximus secondary from the placeholder 7B to Qwen2.5-72B-Instruct-4bit
(top of AeroLLM's proven envelope, same family as the 3B default).

Source plan: `/Users/netsushi/.claude/plans/pure-forging-pizza.md`.

## Phases

| Phase | Subagent | Artifact | Status | Started | Finished | Verdict |
|---|---|---|---|---|---|---|
| think | visionary | VISION.md | done | 2026-05-18 | 2026-05-18 | proceed (commit 64b9279) |
| plan | architect (design) | ARCHITECTURE.md | done | 2026-05-18 | 2026-05-18 | committed f0b38f5; wire split to 3a/3b; bench gate caveats filed as TD-v2.2 |
| build | builder | BUILD_LOG.md | done | 2026-05-18 | 2026-05-18 | 6 atomic commits (ad25c88..79ff686), 70 new tests passing, 1 deviation (gitignore allowlist for committed corpora) |
| review | architect (review) | REVIEW.md | done | 2026-05-18 | 2026-05-18 | WEAK_PASS (commit 50bab2f); 5 carryovers CO-1..CO-5; CO-1 is a dry-run-on-dev-box bug |
| test | qa | TEST_REPORT.md | done | 2026-05-18 | 2026-05-18 | WEAK_PASS (commit 5b240b6); 16 new tests (15+1xfail); 1729 pass / 13 pre-existing fail unchanged |
| ship | — | PR #66 | done | 2026-05-18 | 2026-05-18 | opened; fix-loop merged CO-1/CO-2/BUG-2 before push |

## Decisions log

| Date | Decision | Rationale |
|---|---|---|
| 2026-05-18 | Three-phase rollout (build → publish → wire), each a separate commit | Publish step is irreversible; want a bench gate between local build and HF/Ollama push |
| 2026-05-18 | Build both 4-bit-fused (faithful) and bf16-merged (user ask) candidates and bench | Adapter was trained on 4-bit MLX base; bf16 merge carries quality risk that needs to be measured, not assumed |
| 2026-05-18 | AeroLLM secondary = Qwen2.5-72B-Instruct-4bit (not Llama-3.1-70B) | Same family as the 3B default → consistent tokenization + prompt format; both are in AeroLLM's 19/19 golden gates |
| 2026-05-18 | Stashed recap-core ledger edit (ship-done marker) before branching off main | Sprint isolation; user will restore the stash on the recap-core branch later |
| 2026-05-18 | Architect split wire phase into 3a (ai-eng tag swap) + 3b (72B lift) → 4 commits total | Independent failure modes + verification stories; a 72B resolver bug shouldn't force revert of the ai-eng default swap |
| 2026-05-18 | Builder scope reduced to commit 1 (build/bench scripts) for this sprint | Commits 3a/3b can't ship until Phase 2 publish completes (would point setup.sh at a non-existent Ollama tag); wire-in opens as a follow-up sprint after operator publishes |

## Skipped phases

| Phase | Reason |
|---|---|

## Notes

- **Machine constraint:** MEMORY notes this dev box has OOM'd before during concurrent model work. Build phase must not run with the portal up. The 72B model is for registration only — don't load it during the build sprint unless we have 96+ GB RAM headroom.
- **Frozen surfaces:** paperagents-gated surfaces (agents, skills, landing) must not be touched.
- **License decision (D1) and publish authority (D3)** from the plan are explicit user-gated checkpoints before Phase 2 / publish.
