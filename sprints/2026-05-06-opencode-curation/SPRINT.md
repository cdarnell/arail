# Sprint: opencode-curation

**ID:** 2026-05-06-opencode-curation
**Started:** 2026-05-06
**Product:** arail
**Branch:** `qukaizen/arail-opencode-curation` (off `origin/main` at `a77dc2c`)

## Task

Sprint 2 from approved plan at `~/.claude/plans/also-want-to-consider-synthetic-wreath.md` ("opencode default model + lab curation"). Sprint 1 (PR #34, opencode in Workbench) is merged. Sprint 2 closes the gaps Sprint 1 left: cold-blank UX, no LLM-ready gate, AirLLM has no HTTP server (so opencode can't talk to the lab's actual local backend), no curated codex starter, RAM pressure.

Five workstreams (per plan, ordered by dependency):

1. **OpenAI-compat shim** at `/api/openai/v1/{chat/completions,models}` (new `src/arail/portal/openai_compat.py`, ~150 lines). Foundational because AirLLM has no HTTP server.
2. **Pre-flight LLM-ready gate** on `/api/opencode/start` + 4-state Workbench card UI.
3. **Generated `opencode.json`** at start time (lab-scoped via `OPENCODE_CONFIG_HOME=$LAB_HOME/.opencode`) with locked-to-current-model provider, six lab-aware slash commands, and CLAUDE.md-aware system prompt.
4. **Curated codex starter** in `setup.sh` — Qwen2.5-Coder-3B-Instruct, format-detected per platform, `--with-coder` flag.
5. **Provider-switch hook** extension — Sprint 1's restart hook also rewrites `opencode.json` first.

## Phases

| Phase | Subagent | Artifact | Status | Started | Finished | Verdict |
|---|---|---|---|---|---|---|
| think | visionary | VISION.md | skipped | — | — | — |
| plan | architect (design) | ARCHITECTURE.md | done | 2026-05-06 | 2026-05-07 | proceed-with-caveats (3 caveats, 2 resolved upfront, 1 builder-kickoff verification) — commit 0967b7f |
| build | builder | BUILD_LOG.md | in_progress | 2026-05-07 | — | — |
| review | architect (review) | REVIEW.md | pending | — | — | — |
| test | qa | TEST_REPORT.md | pending | — | — | — |
| ship | — | PR | pending | — | — | — |

## Decisions log

| Date | Decision | Rationale |
|---|---|---|
| 2026-05-06 | Skip visionary | Win condition + wedge documented in approved plan after explicit user-question rounds (default codex model = Qwen2.5-Coder-3B-Instruct, endpoint shim, sprint scoping). Same justification as Sprint 1. |
| 2026-05-06 | Curated codex starter: Qwen2.5-Coder-3B-Instruct | User selected via AskUserQuestion. Apache-2.0, ~2 GB Q4, code-specialized. Phi-4-mini and Gemma 3 4B noted as alternatives but not pre-installed. |
| 2026-05-06 | AirLLM endpoint gap: build `/api/openai/v1/*` shim in portal | User selected via AskUserQuestion. ~150 lines, single OpenAI-compat surface that opencode AND any future tool (MCP, Claude Desktop) can consume. Avoids "require Ollama" punt. |
| 2026-05-06 | Sprint ordering: this sprint first, Skills consolidation → Sprint 3 | User selected via AskUserQuestion. Stays close to opencode while context is hot. |
| 2026-05-06 | Lab-scoped opencode config dir | Avoid overriding the user's personal `~/.config/opencode/` if they use opencode outside the lab. Plan-level mitigation for "locked model picker UX" risk. **Corrected env name (2026-05-07):** real var is `OPENCODE_CONFIG_DIR=$LAB_ROOT/.opencode` (verified via `strings /opt/homebrew/bin/opencode`); plan said `OPENCODE_CONFIG_HOME` which doesn't exist in v1.14.31. ARCHITECTURE.md uses correct name throughout. |
| 2026-05-07 | `enabled_providers` schema field — verify at builder kickoff | Architect caveat 3. Sprint 1's locked-picker decision relies on this field. Builder must verify against opencode v1.14.x docs before relying on it. Fallback path documented in ARCHITECTURE.md F-LOCK-3: omit other providers from `provider:` map and set `OPENCODE_DISABLE_MODELS_FETCH=true` (verified env var exists in binary). |
| 2026-05-07 | Shim wraps existing `_run_chat_completion[_stream]` helpers (app.py:4565/4413), NOT a non-existent `/api/chat/completions` route | Architect caveat 2. Plan reference to `/api/chat/completions` was incorrect — actual routes are `/api/chat`, `/api/chat/stream`, `/api/chat/eject` with the helper already factored. Shim is a thin wrapper, no extraction needed. ARCHITECTURE.md §A5 documents this. |
| 2026-05-06 | Locked model picker via `enabled_providers: ["lab-local"]` | Prevents opencode loading a second model alongside chat. RAM pressure mitigation per user concern. User must swap in Chat to swap in opencode (existing restart hook follows). |
| 2026-05-06 | Sprint 1 already merged into main (PR #34) | Sprint 2 branches cleanly off `origin/main`. No stacking, no conflict surface. |

## Skipped phases

| Phase | Reason |
|---|---|
| think | Win condition + wedge already established via approved plan + user-question round. See Decisions log. |

## Notes

- Approved plan: `~/.claude/plans/also-want-to-consider-synthetic-wreath.md` (Sprint 2 section)
- Per arail/CLAUDE.md QA allocation: 30% setup / 30% Buddy / 20% security / 10% happy / 10% regression. Setup-heavy this sprint (new starter-model download path). Security weight stays on (a) LLM-ready gate not bypassable, (b) **opencode.json must NEVER embed provider tokens in plaintext** — cloud providers reference via `env: ["NAME"]` so opencode reads from process env at runtime.
- Reuse from Sprint 1: opencode subprocess lifecycle (`start`/`stop`/`restart`/`is_running`), 3-state Workbench card pattern (extended to 4 states), provider-switch fire-and-forget restart hook (extended to also rewrite config first).
- Reuse from earlier infra: `_load_active_provider()` (app.py:898), `_provider_token()` (app.py:905), `_PROVIDER_META` (app.py:816), `_scan_local_models()` (app.py:3549), `_CHAT_MODEL_LOAD_STATE` (app.py:4832).
- Sprint 3 (Skills folded into Agents) is queued separately — do not pull in here.

## Sprint 1 follow-ups carried over (decide which land here vs Sprint 3+)

These were captured in Sprint 1's SPRINT.md as deferred:

1. `/api/system/health` info-disclosure — cross-cutting; not opencode-specific. Defer to Sprint 3+.
2. PRIVACY.md trust-model paragraph — doc-only; could land in this sprint as a freebie if scope allows.
3. opencode version probe (F-INSTALL-2) — small; could land here.
4. Token redaction in opencode logs (F-SEC-4) — relevant to cloud-provider env injection; **fold into this sprint's security tests**.
5. `os.setsid` cleanup (F-PROC-3) — small; could land here.

Architect to decide in design phase.
