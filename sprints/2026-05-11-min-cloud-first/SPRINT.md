# Sprint: min-cloud-first

**ID:** 2026-05-11-min-cloud-first
**Started:** 2026-05-11
**Product:** arail
**Predecessor:** 2026-05-10-min-tier-simplification (PR #45)

## Task

Reposition `min` tier as a **cloud-first lab** plugged into 10 model-as-a-service providers. Min works on VMs and small systems by punting heavy inference to the cloud. Max remains the local-first, air-gapped-capable tier.

**Five concrete changes:**

1. **LAB_MODE default flips per tier.** Min ships `LAB_MODE=hybrid` (cloud reachable out of the box). Max ships `LAB_MODE=airgapped` (privacy-first; the previous default for everyone).
2. **10 curated providers.** 5 direct labs (Anthropic, OpenAI, Google Gemini, Mistral, xAI) + 5 aggregators (OpenRouter, HuggingFace Inference, NVIDIA NIM, Together AI, Groq). All wired into `_PROVIDER_KEY_ENVS`, `_PROVIDER_META`, the JS `PROVIDERS` list, and `secrets.env` writer.
3. **`docs/CLOUD_PROVIDERS.md`** — per-provider sign-up → get key → paste here instructions. One section per provider, ordered by direct labs first then aggregators.
4. **Compute Source modal UX** — add "Sign up" link + "Where do I find my key?" tooltip per provider row.
5. **Tier framing rewrite** — README, setup prompt, pyproject descriptions, CLAUDE.md all reframed: min = cloud-first lab (VM-friendly), max = local-first frontier inference (12 GB+ GPU or 32 GB+ Apple Silicon, optionally air-gapped).

## Open-question resolutions (locked before sprint start)

| Decision | Value |
|---|---|
| LAB_MODE default | min → hybrid, max → airgapped (per tier) |
| Provider set | Top 10 mixed: 5 labs + 5 aggregators |
| Onboarding depth | Docs + improved Compute Source modal (sign-up links + tooltips). No first-run wizard. |
| Scope | New sprint, fresh branch (qukaizen/arail-min-cloud-first) cut from min-tier-simplification HEAD |

## Phases

| Phase | Subagent | Artifact | Status | Started | Finished | Verdict |
|---|---|---|---|---|---|---|
| think | visionary | VISION.md | skipped | — | — | (user defined wedge via the AskUserQuestion answers) |
| plan | architect (design) | ARCHITECTURE.md | done | 2026-05-11 | 2026-05-11 | complete |
| build | builder | BUILD_LOG.md | done | 2026-05-11 | 2026-05-11 | complete |
| review | architect (review) | REVIEW.md | done | 2026-05-11 | 2026-05-11 | PASS |
| test | qa | TEST_REPORT.md | done | 2026-05-11 | 2026-05-11 | WEAK_PASS (2 non-blocking followups) |
| ship | — | PR | in-progress | 2026-05-11 | — | — |

## Skipped phases

| Phase | Reason |
|---|---|
| think | Win condition defined: "min = cloud-first lab, max = local-first/air-gapped". User answered 4 framing questions before sprint start. |

## Notes

- Predecessor PR #45 (min-tier-simplification) is open; this branch cuts from its HEAD so it inherits the `arailctl enable compare` add-on machinery + Ollama-only min install. PR #46 will be stacked on PR #45.
- QA allocation per arail CLAUDE.md is 30% setup / 30% Buddy / 20% security / 10% happy / 10% regression. Adapted for this sprint: **35% provider-wiring / 25% setup-flow / 20% security (keys never leak; airgapped guard still honored on max) / 10% UI / 10% regression**.
- Pre-existing bug flagged by the architect-design pass: the chat.html JS calls `/api/tokens/{provider}` while the server implements `/api/providers/*`. This sprint will *not* fix that bug (out of scope — pre-dates min-cloud-first), but the new modal JS will use the correct `/api/providers/*` namespace so the new functionality works.
