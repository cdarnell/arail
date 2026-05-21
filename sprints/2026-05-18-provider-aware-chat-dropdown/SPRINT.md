# Sprint: provider-aware-chat-dropdown

**ID:** 2026-05-18-provider-aware-chat-dropdown
**Started:** 2026-05-18
**Product:** arail
**Branch:** qukaizen/arail-provider-aware-chat-dropdown

## Task

Make the chat input model dropdown reflect the user's Compute Source selection.
Today, when a user flips Compute Source from "My Machine" to Claude / NVIDIA NIM /
OpenRouter / HuggingFace / Custom, the dropdown stays pinned to the local Ollama
catalog. The provider-switching pattern works for routing (`/api/providers/active`
sets `COMPUTE_SOURCE` env, opencode restarts), but the **chat input is blind to it**
because `/api/chat/models` reads the primary local backend's catalog and ignores
the active provider.

This sprint closes that gap on the active template (`chat.legacy.html`). It does
not touch the new template (`chat.html`) which is mid-conversion and missing
`renderModelRail` / `renderSourcesRail` — that's a separate concern.

Why it matters (from MEMORY): **`project_pluggable_provider_thesis`** — the lab's
product thesis is that provider-switching must be effortless (one click in Compute
Source) and never require revamping setup. A dropdown that lies about available
models breaks the thesis.

Source audit: explore agent output captured in conversation; key gap is the
provider-unaware `/api/chat/models` endpoint at `app.py:5775-6089` plus the
missing change-listener that re-calls `loadModels()` in `chat.legacy.html:957-959`.

## Scope (explicit)

**In scope:**
1. `/api/chat/models` accepts `?provider=<name>` and returns that provider's
   model list (uses `/api/providers/models` plumbing already present at
   `app.py:1313-1349`).
2. `chat.legacy.html` Compute Source radio change listener re-calls
   `loadModels()` with the new provider.
3. Per-provider curated model list for HuggingFace (which has no `/models`
   endpoint), plus a sensible default for OpenRouter (~50 most-used IDs, paginate
   or filter for the rest).
4. Empty-state CTA: when provider has no saved token, the dropdown shows
   "Save a key in ⚙ Manage providers" instead of going silent.
5. Tests: unit (endpoint per-provider behavior), integration (radio change →
   dropdown refresh, mocked), regression (local-only `/api/chat/models` behavior
   unchanged when no `?provider=`).

**Out of scope:**
- `chat.html` (new template, WIP) — separate sprint.
- New provider integrations (Cohere, Mistral, Google, Together) — current 6 only.
- Per-provider model defaults / cost ceilings / auto-selection logic — UI exposes,
  user picks.
- Token save/test flow — already works via the Manage Providers modal.

## Scope expansion — 2026-05-20 (user-directed; packaging: one expanded sprint)

The original scope above is **Layer 1** and stands. The operator broadened the
sprint to a single expanded sprint covering four layers. Items previously
"out of scope" (new providers, ctx, override) are pulled IN.

**Layer 1 — Provider-aware dropdown (original scope, unchanged).**
`/api/chat/models?provider=`, radio change → `loadModels()`, curated HF list,
empty-key CTA, airgap refusal, loading/error states. Applies to the
**second model slot especially** (operator framing: default = local model that
ships with the lab; second slot = all provider options).

**Layer 2 — Five new providers (was out of scope).**
Add xAI (Grok, `https://api.x.ai/v1`), Google Gemini (`/v1beta/openai`),
Mistral, Cohere (`/compatibility/v1`), Together — all OpenAI-compatible, bearer
auth. Registry-only: `_PROVIDER_KEY_ENVS`, `_PROVIDER_META`, frontend radios +
JS `PROVIDER_META`/`CLOUD`. `_CLOUD_PROVIDERS` (derived) and `_auth_headers`
(bearer fallback) need no change. Manage-Providers modal renders them
automatically (data-driven off `/api/providers/status`).

**Layer 3 — ctx: show + auto-fill + set (was out of scope).**
- New parser `model_specs.context_tokens()` / `context_label()` ("128K"→131072).
- Picker cards show context window + resource-cost hint (OOM caution on local).
- Wire the EXISTING `ARAIL_MODEL_CTX_OVERRIDES` store into inference:
  `CPUBackend` reads it for `n_ctx` at load; new `OllamaNativeBackend` hits
  `/api/chat` with `options.num_ctx`. ctx is **load-time** — UI must say so.
- Reuse `set-ctx` persistence via a thin `POST /api/chat/models/set-ctx`
  delegate; purge `_RUNTIME_BACKEND_CACHE` on change.

**Layer 4 — Chat-wide default override (was out of scope).**
One control sets default provider+model for ALL chat (per-message overrides win).
Store: `COMPUTE_SOURCE` (existing) + new `ARAIL_CHAT_DEFAULT_MODEL` in
secrets.env. `POST /api/chat/default` (+ clear/revert). `_apply_chat_defaults`
shim in the send path. **Chat tab only** — not autoresearch, not agents.

**Still out of scope:** `chat.html` (new template) — legacy only; lab-wide
override across autoresearch/agents; per-provider cost ceilings.

## Phases

| Phase | Subagent | Artifact | Status | Started | Finished | Verdict |
|---|---|---|---|---|---|---|
| think | visionary | VISION.md | done | 2026-05-18 | 2026-05-18 | proceed (commit 6a1481d); 3 risks flagged |
| plan | architect (design) | ARCHITECTURE.md | done | 2026-05-18 | 2026-05-20 | PROCEED; 5 corrections (F-VALIDATE/F-CATALOG/F-CLOUD-CURRENT/F-CACHE/F-DEFAULT-LEAK) + 3 load-bearing regressions (R1/R2/R3) |
| build | builder | BUILD_LOG.md | done | 2026-05-20 | 2026-05-20 | 15 commits (ba9f136..bf5a3f6); 98 sprint tests; full suite 1733 pass / 12 pre-existing fail unchanged; all 5 corrections + R1/R2/R3 in |
| review | architect (review) | REVIEW.md | done (loop 1) | 2026-05-20 | 2026-05-20 | BLOCK (commit 7698f2e); B1 cloud-gallery-empty + B2 ollama-ctx-unwired; F-CLOUD-CURRENT fixed, scope clean, no regression |
| build | builder (fix-loop) | BUILD_LOG.md | done | 2026-05-20 | 2026-05-20 | 4 commits (6cd007b..cf10b91); B1+B2 fixed w/ reachability tests; R1 hardened; 124 sprint tests |
| review | architect (re-review) | REVIEW.md | done (loop 2) | 2026-05-20 | 2026-05-20 | PASS (commit 40d8523); B1+B2 cleared w/ reachability tests, R1 hardened, no regression/drift; 3 carryovers for qa |
| test | qa | TEST_REPORT.md | done | 2026-05-20 | 2026-05-20 | WEAK_PASS; 51 new QA tests (175 sprint total, 0 fail); zero new full-suite failures; security PASS on XSS/airgap×10/token-echo/traversal; 3 carryovers resolved/accepted; 1 finding QA-1 (test clobbers real secrets.env — non-blocker, fix before merge) |
| ship | — | PR | pending | — | — | — |

## Decisions log

| Date | Decision | Rationale |
|---|---|---|
| 2026-05-18 | Legacy template only; chat.html WIP deferred | chat.legacy.html is what users actually see; finishing chat.html is bigger surface area + risk |
| 2026-05-18 | `?provider=` query param, not `COMPUTE_SOURCE` env coupling | Avoids server-state side-effects on dropdown refresh; client controls request, server stateless |
| 2026-05-18 | HF gets a curated hardcoded list (no `/models` endpoint exists) | Per audit: `_CLOUD_PROVIDERS["huggingface"]` has `models_path: ""` — no upstream API to call |
| 2026-05-20 | Scope expanded to one sprint, 4 layers (dropdown + 5 providers + ctx + chat-wide default) | User-directed packaging = "one expanded sprint"; see Scope expansion section |
| 2026-05-20 | ctx applied at backend load-time, not threaded through per-call dispatch | llama.cpp `n_ctx` fixed at `Llama()`; Ollama reloads on `num_ctx` change — keeps `complete()` byte-identical (protects local regression) |
| 2026-05-20 | Ollama ctx via native `/api/chat` `options.num_ctx`, not OpenAI `/v1` | Ollama's OpenAI-compat shim silently ignores `num_ctx`; Modelfile mutates user's model globally — native API is the clean revertible path |
| 2026-05-20 | Override is chat-wide default, NOT lab-wide | User chose Chat-tab scope; autoresearch/agents stay independent (frozen-surface + OOM caution) |

## Skipped phases

| Phase | Reason |
|---|---|

## Notes

- **Frozen surfaces** (MEMORY): paperagents-gated surfaces (agents, skills, landing) — not in scope here.
- **Pluggable provider thesis** (MEMORY): "feel like a modern AI lab by being pluggable into real-world providers; never require revamping setup." This sprint is a direct expression.
- **Educational-disclosure principle** (MEMORY): an empty dropdown with "save a key" CTA fits the "teach when expanded" pattern — making the missing-key state pedagogical rather than broken.
- **First-paint loading rule** (MEMORY, commit 097df62): the dropdown must show a loading state during the refresh, not silent empty.
