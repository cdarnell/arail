# Architecture: ARAIL Two-Tier Model Architecture (v1.1 models)

**Date:** 2026-06-14
**Spec:** [VISION.md](./VISION.md) (visionary rejected TinyLlama/Mistral-Q2; design targets Llama-3.2-1B default + Qwen2.5-7B deep)
**Product:** arail

## Restatement

ARAIL ships two model tiers behind one CLI. The **minimalist** default is
`llama-ai-eng` — Llama-3.2-1B-Instruct wrapped with an AI-engineer persona,
~0.9 GB, auto-installed during `./arailctl setup` via `ollama pull llama3.2:1b`
+ `ollama create`, with zero model-selection prompts and no uploaded artifact.
The **maximus** deep tier is `ai-engineer` — Qwen2.5-7B-Instruct (Apache-2.0),
opt-in via `./arailctl upgrade maximus`, served by AeroLLM (MLX, in-process
PyO3 wheel) on Apple Silicon and falling back to AirLLM (subprocess,
opt-in) on CUDA/Linux until AeroLLM's CUDA backend ships. The sprint's job is
not to invent new code paths — almost all of this already exists in
`scripts/setup.sh`, `scripts/upgrade.sh`, `src/arail/router/backends.py`,
and `src/arail/agents/deep_policy.py`. The job is to (1) make the clean-machine
default path provably honest about resources and failures, (2) make the maximus
upgrade surface an honest AeroLLM-vs-AirLLM notice, (3) write the tier-selection
copy, and (4) lock the Llama disclosure so it cannot silently drift. **This is a
hardening + wiring + copy sprint, not a greenfield build.** Critically: the repo
currently mixes two "default model" concepts — the **Ollama** default
(`llama-ai-eng`, the 1B chat persona) and the **AeroLLM/MLX** default
(`Qwen2.5-7B-Instruct-4bit`, the deep box). The builder MUST keep these
separate: the 1B is the minimalist everyday model on Ollama; the 7B is the
maximus deep "2nd inference" on AeroLLM. Conflating them is the single biggest
correctness risk in this sprint.

## Assumptions

These are the load-bearing assumptions. If any is false, a section below breaks.

1. **Ollama is the minimalist runtime path.** `llama-ai-eng` is created via
   `ollama create` and served over Ollama's native `/api/chat`
   (`OllamaNativeBackend`). The 1B default does NOT go through AeroLLM/MLX.
2. **On Apple Silicon, `ollama_default_enabled()` returns false** (setup.sh:47)
   — meaning setup skips Ollama install by default and prefers MLX. **This is a
   conflict with the minimalist default model being an Ollama model.** See
   Failure mode F1: the 1B default install requires Ollama, but the default
   macOS path skips Ollama. The builder must reconcile this — either setup
   installs Ollama whenever the minimalist default is `llama-ai-eng`, or the
   minimalist default on MLX becomes an MLX-served 1B. The architecture below
   resolves this by **always installing Ollama when the persona-wrap default is
   selected** (the model catalog's `install` field is an `ollama` command).
3. **`ollama pull llama3.2:1b` fetches a Q4_K_M GGUF (~0.9 GB)** and runs in
   <2 s TTFT on M-series. (Win-condition latency gate.)
4. **AeroLLM weights are NOT auto-downloaded by setup.** `setup_env()`
   (setup.sh:1319-1335) only *warns* if `lab/models/Qwen2.5-7B-Instruct-4bit`
   is absent; it prints a `huggingface-cli download` command. The maximus deep
   box is therefore "configured but cold" until weights land. This is by design
   (4 GB download is opt-in), but the upgrade UX must say so honestly.
5. **AeroLLM auto-build is Apple-Silicon-only today** (setup.sh:607). On CUDA,
   `prefer_deep()` returns false unless AirLLM is opted in. The honest notice
   must reflect this.
6. **16 GB is the floor for both minimalist and (4-bit) maximus.** The 7B-4bit
   is ~4 GB resident; the KV budget resolver (`_resolve_kv_budget`) defaults to
   60% of total RAM and clamps by available. 8 GB M1 cannot run maximus and
   should be told so honestly.
7. **The Llama license requires disclosure and forbids hiding the base.** The
   `ai-engineer` (Qwen/Apache-2.0) lineage is the only one where hide-the-base
   applies. These two rules must not cross-contaminate.

## Data flow

```
                       ./arailctl setup  (clean machine)
                                  |
         ┌────────────────────────┴────────────────────────┐
         |  detect_platform → PLATFORM, ACCEL                |
         |  capture_tier → LAB_TIER (default: minimalist)    |
         └────────────────────────┬────────────────────────┘
                                  |
                   install_services() [setup.sh:662]
                                  |
              ┌───────────────────┴───────────────────┐
              | ensure Ollama present (REQUIRED when    |
              | minimalist default = llama-ai-eng)      |
              └───────────────────┬───────────────────┘
                                  |
            ollama pull llama3.2:1b  (~0.9 GB, Q4_K_M GGUF)
                                  |
            ollama create llama-ai-eng -f models/ai-eng/Modelfile.default
                                  |  (SYSTEM prompt carries "Built with Llama")
                                  v
        Ollama model store: ~/.ollama/models  (NOT lab/models/)
                                  |
                                  v
        ./arailctl start → portal :8080 → Chat tab
                                  |
         Compute Source = "My Machine" → OllamaNativeBackend
                       (POST localhost:11434/api/chat, model=llama-ai-eng)
                                  |
                                  v
                      Buddy + Chat answer (offline)


        ──────────── MAXIMUS UPGRADE (opt-in) ────────────

   ./arailctl upgrade maximus  [scripts/upgrade.sh]
                |
                ├─ pip install -e ".[maximus]"   (Anthropic SDK, LangChain…)
                ├─ write LAB_TIER=maximus to .env
                └─ (setup re-run or deep path) AeroLLM build + weights
                          |
            ┌─────────────┴──────────────┐
            |  Apple Silicon (arm64)?     |
            └─────────────┬──────────────┘
                  yes     |        no (CUDA/Linux/Intel)
          ┌───────────────┘                 └───────────────┐
          v                                                 v
  scripts/build-aerollm.sh auto                  AeroLLM CUDA backend NOT ready
  → aerollm_api PyO3 wheel                        → honest notice:
  → AeroLLMBackend (in-process MLX)               "AeroLLM deep mode is Apple-
  weights: lab/models/Qwen2.5-7B-Instruct-4bit     Silicon-only today. On CUDA,
          |                                          enable the AirLLM fallback
          v                                          with ARAIL_INSTALL_AIRLLM=1
  Chat "Box B" / deep toggle → deep_policy          and set AIRLLM_MODEL."
  prefer_deep() → AeroLLMBackend.complete()              |
                                                         v
                                              AirLLMBackend (subprocess) IF
                                              opted-in AND AIRLLM_MODEL set,
                                              ELSE deep box shows config notice
```

## Interface contracts

### Component 1 — `install_services()` minimalist default install (setup.sh)
- **Promises:** After a successful clean-machine run with `LAB_TIER=minimalist`,
  `ollama show llama-ai-eng` succeeds and the model answers over
  `localhost:11434/api/chat`. The `ollama create` step uses
  `models/ai-eng/Modelfile.default` whose SYSTEM prompt ends with "Built with
  Llama."
- **Requires:** Ollama installed and on PATH; network for the pull;
  `models/ai-eng/Modelfile.default` present.
- **On bad input / failure:** If `ollama pull` fails (offline), print the exact
  manual command and continue setup (non-fatal) — the lab still starts, the chat
  tab shows "model not installed yet" with the recovery command. Idempotent: a
  pre-existing `llama-ai-eng` short-circuits (setup.sh:791).
- **CHANGE REQUIRED:** `ollama_default_enabled()` (setup.sh:47) currently returns
  false on Apple-Silicon+MLX, which skips the Ollama install block. Since the
  minimalist default is an Ollama model, the builder must force Ollama install
  whenever the persona-wrap default path will run. Resolution: gate Ollama
  install on `LAB_TIER=minimalist OR persona-wrap default selected`, not on
  ACCEL.

### Component 2 — `OllamaNativeBackend` (router/backends.py:1724)
- **Promises:** Serves `MODEL_NAME=llama-ai-eng` over native `/api/chat` with
  correct `num_ctx`. Streams deltas then a `ModelResponse(backend="ollama_native")`.
- **Requires:** Ollama daemon up; `MODEL_NAME` resolvable via
  `_resilient_chat_default` (app.py:6120) which already prefers `llama-ai-eng`.
- **On bad input:** connection refused → `health_check()` returns false → chat
  surface shows "local runtime offline."

### Component 3 — `AeroLLMBackend` (router/backends.py:1440) — maximus deep
- **Promises:** In-process MLX runtime for `Qwen2.5-7B-Instruct-4bit` resolved
  under `ARAIL_MODELS_DIR`. One resident Runtime per model per process
  (`_shared` cache — prevents double-residency OOM). KV budget clamped by
  `_resolve_kv_budget()` to 60% total / available-aware.
- **Requires:** `aerollm_api` wheel importable; weights at
  `lab/models/Qwen2.5-7B-Instruct-4bit`; Apple Silicon.
- **On bad input:** Missing wheel → `ImportError` with `./arailctl deep rebuild`
  hint. Missing weights → `RuntimeError` with the `huggingface-cli download`
  command. Both are caught by `deep_policy.complete_preferring_deep` which
  **silently falls back to fast** — never crashes, never OOMs.

### Component 4 — `prefer_deep()` / deep policy (agents/deep_policy.py:84)
- **Promises:** Returns True only when `maximus` tier AND `aerollm_api`
  importable. Foreground → deep immediately; background → only when
  `background_safe()`. Any failure → fast.
- **Requires:** `tier.is_maximus()`; `aerollm_api` importable.
- **On bad input:** Not maximus, or wheel missing → always fast. This is the
  gate that makes CUDA-without-AeroLLM degrade gracefully.

### Component 5 — Disclosure surface (NEW: a verifiable check)
- **Promises:** `models/ai-eng/Modelfile.default` SYSTEM contains "Built with
  Llama"; the model id begins with `llama-`; README + catalog + NOTICE carry the
  Llama 3.2 Community License + AUP references; `licenses/` holds both files.
- **Requires:** A test (`tests/test_llama_disclosure.py`) that asserts all of
  the above so the contract is machine-checked.
- **On bad input:** Test fails → CI (`make ci-local` / `scripts/ci-local.sh`)
  blocks. This is the hard stop-ship gate from the win condition.

## Failure modes

Every row maps to a test in the strategy below.

| # | Failure | Detection | Recovery |
|---|---|---|---|
| F1 | Apple-Silicon path skips Ollama (`ollama_default_enabled`=false) but minimalist default is an Ollama model → no model installed | `ollama show llama-ai-eng` fails post-setup; doctor check | Force Ollama install when persona-wrap default selected; gate on tier not ACCEL |
| F2 | `ollama pull llama3.2:1b` fails (offline / slow link) | Non-zero exit from `_arail_timeout 900 ollama pull` | Non-fatal: print exact manual command, continue; chat tab shows "model not installed" + recovery |
| F3 | 16 GB box, minimalist: portal+browser+Ollama crowd RAM | `psutil` available read < threshold at start | Ollama 1B is ~1 GB resident — no OOM expected; doctor prints headroom; honest notice only if available RAM < 2 GB |
| F4 | 16 GB box, maximus + AeroLLM: KV budget too aggressive → swap/OOM | `_resolve_kv_budget` source="floor"; activity_log warn | KV clamped to 60%/available; floor 2 GiB; emits warn-level activity entry. 7B-4bit fits with headroom |
| F5 | maximus on CUDA, AeroLLM not ready | `prefer_deep()` false (not arm64); build-aerollm.sh skips | Honest notice: "AeroLLM deep mode is Apple-Silicon-only today; on CUDA enable AirLLM (ARAIL_INSTALL_AIRLLM=1) and set AIRLLM_MODEL" |
| F6 | maximus deep weights missing | `AeroLLMBackend.__init__` RuntimeError (dir not found) | Caught by deep_policy → fast fallback; setup_env warns with `huggingface-cli download` command up-front |
| F7 | 8 GB M1, user tries maximus | RAM read < 16 GB in capture_tier | Honest path: "maximus needs 16 GB+; stay on minimalist (1B runs fine on 8 GB) or use a cloud Compute Source in hybrid mode" |
| F8 | AirLLM fallback streams slowly (layer-streaming) | `backend="airllm"` on ModelResponse | Chat surface labels the response "served via AirLLM fallback (slower)"; honest, not hidden |
| F9 | Llama disclosure drift (name changed, "Built with Llama" removed) | `tests/test_llama_disclosure.py` fails in CI | Stop-ship; CI blocks merge |
| F10 | 1B/7B conflation: someone sets MODEL_NAME=llama-ai-eng on AeroLLM, or AEROLLM_MODEL to the 1B | Backend mismatch (AeroLLM dir lookup fails) / wrong-size model served | Keep Ollama default (1B) and AeroLLM default (7B) in separate env vars: MODEL_NAME vs AEROLLM_MODEL. Test asserts they differ |
| F11 | maximus deep model degrades reasoning (regression of the whole tier) | QA 5-prompt reasoning set: deep must beat minimalist ≥4/5 | If <4/5, the deep persona/quant is wrong — block ship per VISION disconfirming evidence |

## Test strategy

- **Unit:**
  - `_resolve_kv_budget`: env pct parsing (valid/invalid/out-of-range), floor
    clamping, psutil-missing → None, total=0 → None. (F4)
  - `_resilient_chat_default`: prefers `llama-ai-eng`, falls back through
    `ai-eng:latest` → `ai-engineer:latest` → regex → qwen2.5:7b → first. (F10)
  - `prefer_deep`: false on minimalist, false when `aerollm_api` not importable,
    true on maximus+importable foreground. (F5, F6)
  - `tier.get_current_tier` / `is_maximus`: legacy min/max mapping. (existing)
  - **NEW `test_llama_disclosure.py`**: Modelfile.default SYSTEM contains "Built
    with Llama"; default model id starts with `llama-`; `licenses/` has both
    Llama files; README + models_catalog.yaml mention "Built with Llama";
    NOTICE references the Llama 3.2 Community License + AUP. (F9)
  - **NEW `test_model_separation.py`**: minimalist default (MODEL_NAME /
    `llama-ai-eng`) is an Ollama 1B; maximus deep (AEROLLM_MODEL /
    `Qwen2.5-7B-Instruct-4bit`) is distinct; the two ids never collide. (F10)
- **Integration:**
  - Clean-machine setup smoke (`ARAIL_NONINTERACTIVE=1 ARAIL_TIER=minimalist`):
    assert `ollama show llama-ai-eng` succeeds and a one-token chat completes via
    `OllamaNativeBackend`. (F1, F2)
  - Upgrade smoke: `./arailctl upgrade maximus` writes `LAB_TIER=maximus`,
    pip-installs the maximus extra, and (arm64) probes AeroLLM build; assert the
    honest notice prints on CUDA. (F5)
  - Deep fallback: with maximus tier but no weights, assert
    `complete_preferring_deep(foreground=True)` returns the fast answer, never
    raises. (F6)
- **Regression:**
  - The `ollama_default_enabled` change (F1) must NOT re-break the documented
    "Apple Silicon prefers MLX" behavior for the *deep* path — assert AeroLLM is
    still the maximus deep backend on arm64 while Ollama serves the 1B default.
  - Legacy tier names still fold (`min`→`minimalist`, `max`/`med`→`maximus`).
- **Performance** (QA executes on a 16 GB M-series, airgapped):
  - Minimalist TTFT < 2 s; full short reply < 8 s. (win condition)
  - Setup clean-machine to first token < 10 min on 50 Mbps. (win condition)
  - Maximus 7B-4bit: no OOM; KV source != "floor" on a 16 GB box at idle.
- **Quality / Security:**
  - QA 10-prompt smoke set: minimalist ≥ 8/10 coherent. (F11, trust gate)
  - QA 5 reasoning prompts: maximus beats minimalist ≥ 4/5. (F11)
  - Airgapped guard: confirm no egress when `LAB_MODE=airgapped` during the
    whole minimalist path (Ollama is localhost; the pull is the only network
    call and happens at setup, not runtime).

## Tech debt

**Added:**
- The `ollama_default_enabled()` reconciliation (F1) introduces a branch where
  Ollama is installed on Apple Silicon despite the "MLX-preferred" comment —
  needs a clear comment so a future reader doesn't "fix" it back. File as
  follow-up: unify the runtime-selection logic so the 1B-on-Ollama vs
  7B-on-MLX split is expressed in one place, not two.
- AirLLM fallback on CUDA is documented, not built — the honest notice is a
  stopgap. Tracked as the AeroLLM-CUDA-backend follow-up (already displaced per
  VISION).

**Repaid:**
- The Llama disclosure becomes machine-verified (was prose-only across README /
  NOTICE / catalog) — removes a latent stop-ship drift.
- The 1B/7B conflation risk gets a regression test, closing an easy footgun.

**Net:** Slightly negative (debt repaid > added) — the disclosure test and
model-separation test are durable; the one new branch is well-contained.

## Recommended implementation order

The builder reads this once and builds top-to-bottom. Touch these files in this
order:

1. **`scripts/setup.sh`** — Reconcile F1: make Ollama install fire whenever the
   minimalist persona-wrap default will run (gate on tier/default, not ACCEL).
   Keep the existing idempotency (`ollama show llama-ai-eng`) and the non-fatal
   failure path with the exact manual recovery command (F2).
2. **`models/ai-eng/Modelfile.default`** — Verify (do not change unless drift):
   id source `llama3.2:1b`, SYSTEM ends with "Built with Llama". This is the
   disclosure anchor.
3. **`tests/test_llama_disclosure.py`** (NEW) — Encode the disclosure contract
   (F9): name starts `llama-`, "Built with Llama" in Modelfile + README +
   catalog, NOTICE + `licenses/` carry license + AUP.
4. **`tests/test_model_separation.py`** (NEW) — Assert minimalist (Ollama 1B)
   and maximus deep (AeroLLM 7B) ids/backends never collide (F10).
5. **`scripts/upgrade.sh`** — Add the honest AeroLLM-vs-AirLLM notice (F5/F8):
   on `upgrade maximus`, after pip install, detect arm64 vs CUDA and print
   either "AeroLLM deep ready (run ./arailctl deep rebuild + download weights)"
   or the CUDA AirLLM-fallback notice. Do NOT auto-download the 4 GB weights;
   print the `huggingface-cli download` command (mirror setup_env:1319).
6. **`src/arail/portal/app.py`** — In the Chat "Box B" / deep surface, label the
   served backend honestly: when `backend="airllm"`, show "via AirLLM fallback
   (slower)"; when deep is unavailable on this host, show the F5 notice instead
   of an empty box. (`_resolve_chat_deep_default` already gates the default-open
   state correctly — extend the rendered label, don't change the gate.)
7. **`capture_tier()` in `scripts/setup.sh`** — Add the 8 GB honest path (F7):
   if RAM < 16 GB and user picks maximus, warn that maximus needs 16 GB+ and 1B
   minimalist runs fine on 8 GB.
8. **`docs/` + portal copy** — Add the tier-selection paragraph (below) to the
   docs and the portal's tier/upgrade surface.

### Tier-selection copy (ship in docs + portal)

> **Which tier?** Start on **minimalist** — it's the everyday lab. Its
> `llama-ai-eng` model (built with Llama-3.2-1B, ~0.9 GB) is fast, runs offline
> on 16 GB, and handles chat, quick code, lookups, and most Buddy back-and-forth
> without breaking a sweat. Flip to **maximus** (`./arailctl upgrade maximus`)
> when you hit a *reasoning wall the small model can't climb*: a multi-step
> refactor that has to hold several files in its head, a research-plan critique
> where you need the model to find the flaw rather than agree with you,
> architecture decisions with real tradeoffs, or thorough code review. The
> signal that minimalist isn't enough is concrete: it loops, hand-waves the hard
> step, or confidently gives a shallow answer to a question that needed depth.
> Maximus runs Qwen2.5-7B locally via AeroLLM on Apple Silicon (no cloud, no
> code leaves your machine). Don't default to maximus "just in case" — it's
> heavier, and on most days the 1B is the right tool. Use the heavy model when
> the problem is actually heavy.
