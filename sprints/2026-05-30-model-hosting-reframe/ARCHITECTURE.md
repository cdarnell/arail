# Architecture: Model-Hosting Strategy Reframe

**Date:** 2026-05-30
**Spec:** [VISION.md](./VISION.md) (sprint 2026-05-30-model-hosting-reframe)
**Branch:** `qukaizen/arail-kv-available-budget` (current); builder should branch `qukaizen/arail-model-hosting-reframe` off `main`.

---

## Restatement

ARAIL today over-promises against its target hardware (36 GB Apple Silicon) in two ways. First, the maximus deep-mode default points at AirLLM-streamed Llama-3.1-70B/405B, which OOMs or crawls on that class of box — the advertised "frontier-scale" tier diverges from the lived experience. Second, the default-assistant install (`ai-eng`) runs a fragile probe-then-fallback ladder: it probes `qukaizen/ai-eng:3b`, and on miss pulls a 5 GB `qwen2.5:7b` and builds an `ai-eng` from a Modelfile — a second auto-download on an OOM-sensitive machine that ships a 7B wearing a "3B" label and advertises the qwen lineage everywhere. This sprint does three config/copy changes: (1) repoint the maximus deep slot to a TODO-placeholder 20–30B quick-download model (not an auto-install) and deprecate the 70B/405B AirLLM defaults; (2) collapse the ai-eng install to a single `ollama pull qukaizen/ai-eng:3b` with the LoRA baked into the tag; (3) strip the qwen lineage from all user-facing copy while preserving any license-required attribution in non-marketing locations, and honestly rewrite the maximus "frontier-scale" promise.

---

## GATE RESULTS (the two hard gates the architect owns)

### Gate A — is `qukaizen/ai-eng:3b` published? **NO. → DEFER the single-pull collapse.**

Verified against the live Ollama registry on 2026-05-30:

```
GET https://registry.ollama.ai/v2/qukaizen/ai-eng/manifests/3b      → 404
GET https://registry.ollama.ai/v2/qukaizen/ai-eng/manifests/latest  → 404
GET https://registry.ollama.ai/v2/library/qwen2.5/manifests/7b      → 200  (control)
```

Per VISION § Disconfirming evidence ("If the tag is not live before BUILD, we DEFER the setup-collapse half"), **Part 2 (collapse setup.sh to a single pull) MUST NOT ship the naive `ollama pull qukaizen/ai-eng:3b`-only path.** Doing so would strand every clean-machine cloner with no assistant — a direct violation of the headline win condition ("one auto-install, one model" presupposes the one model exists).

**Decision — Part 2 splits into 2a (ship now) and 2b (gated, defer):**

- **2a (SHIP):** Keep the probe→fallback *capability* but make it honest and quiet. The preview fallback stays as the safety net (because the tag is 404), BUT:
  - the fallback no longer leaks qwen into user-facing strings (Part 3 covers this);
  - the fallback is collapsed from the current 4-command catalog `install` string into a clean, single-responsibility shell path;
  - the Modelfile-create step is preserved ONLY for the preview path (it is the only thing that gives the fallback the ai-eng persona). Once the tag publishes, the production path is a pure single `ollama pull` with no create step.
- **2b (DEFER, file follow-up ticket):** The "pure single `ollama pull`, delete Modelfile.preview, delete the fallback ladder" end-state lands in a follow-up sprint **gated on a re-run of Gate A returning 200.** The builder adds a one-line machine-checkable gate (see Edit list, `scripts/check_ai_eng_tag.sh`) so the next sprint flips automatically.

This preserves the win condition's *intent* (no surprise second 5 GB pull is the goal; but a fallback that exists only because the primary 404s is not a "surprise" — it is the documented safety net) while not shipping a `pull` that bricks setup. The builder MUST NOT delete `Modelfile.preview` this sprint.

> Net effect on Win Condition #1 ("one pull, zero qwen2.5:7b pulls"): **partially deferred.** When the tag publishes, condition #1 is met automatically. Until then, the fallback pull is the only thing standing between a cloner and a working lab. Mark WC#1 as "met-on-publish" in the sprint ledger; do not claim it green this sprint.

### Gate B — does a 20–30B deep model still deliver "frontier-scale"? **NO. → rewrite the copy. (resolved below, Part 1 + § Honest framing)**

A 20–30B local model is not frontier-scale by 2026 standards. The maximus tier copy is rewritten so a 30B deep model is not a silent downgrade. See § Honest framing rewrite. The two tensions the visionary flagged are both resolved in this document before any code is written.

---

## Assumptions

1. **Ollama is the runtime for ai-eng.** On Apple Silicon, setup skips Ollama by default (MLX is primary) unless `ARAIL_ENABLE_OLLAMA=1`. The ai-eng pull therefore only runs when Ollama is present (existing guard at `setup.sh:739`). This sprint does not change that guard.
2. **`qukaizen/ai-eng:3b` is `qwen2.5:3b` base + a LoRA, distilled from Opus 4.7 via Nucleus.** The base is confirmed by `scripts/build_ai_eng.py:47` (`DEFAULT_BF16_BASE = "Qwen/Qwen2.5-3B-Instruct"`). This is the attribution-relevant fact.
3. **Qwen2.5-3B ships under the Qwen RESEARCH/Qwen license, not Apache-2.0.** (Qwen2.5 models ≤3B and the 72B are under the Qwen license; 0.5B–7B-class are Apache-2.0 in some releases — *the builder MUST confirm the exact license of `Qwen/Qwen2.5-3B-Instruct` before BUILD* and record the SPDX id in the NOTICE file. Treat it as attribution-required regardless; attribution is cheap, a license violation is not.)
4. **The 20–30B deep-model ID is a deliberate TODO.** This document does NOT pick a model. The placeholder is `__TODO_DEEP_MODEL__` (sentinel convention below). The build must not resolve it to a real weight.
5. **Deep models are pull-on-demand, never setup auto-installs.** Confirmed by VISION wedge. Part 1 only changes a *default ID*, not the install trigger.
6. **`LAB_MODE=airgapped` is invariant.** No code in this sprint touches cloud-egress gating. The deep-model swap touches local-backend defaults only.
7. **The reference hardware is a 36 GB Apple Silicon machine.** Latency/footprint bars below are set against it.

---

## Data flow

```
                         ./arailctl setup  (Ollama present)
                                   │
                                   ▼
            ┌──────────────────────────────────────────────┐
            │  install_models()  [setup.sh]                  │
            │                                                │
            │  1. ai-eng already present?  ──yes──► done     │
            │  2. legacy ai-engineer:latest? ─yes─► cp alias │
            │  3. ┌── PROBE qukaizen/ai-eng:3b ──┐           │
            │     │  published (200)?            │           │
            │     │   YES → pull, DONE (no create)│  ◄── 2b end-state
            │     │   NO  → fallback path (2a):   │           │
            │     │        pull preview base,     │           │
            │     │        ollama create ai-eng   │           │
            │     │        -f Modelfile.preview   │           │
            │     └──────────────────────────────┘           │
            └──────────────────────────────────────────────┘
                                   │
                          ai-eng:latest in Ollama
                                   │
                                   ▼
                    Chat tab → My Machine → ai-eng (default)

  ── Deep mode (maximus, pull-on-demand, NOT setup) ──────────────────────
       Operator clicks Deep mode  /  sets AEROLLM_MODEL or AIRLLM_MODEL
                                   │
            backend default ID  =  __TODO_DEEP_MODEL__ (sentinel)
                                   │
                 sentinel unresolved? ──► friendly "set your deep model" notice
                                          (NO download, NO crash, NO OOM)
```

The only new branch is the **sentinel-unresolved guard** on the deep path and the **honest fallback** on the ai-eng path. No new network calls beyond what exists.

---

## Interface contracts

### `[tool.arail.models]` (pyproject.toml) — source of truth
- **Promises:** every key resolves to either a real model id OR the documented sentinel `__TODO_DEEP_MODEL__`. `setup.sh`'s embedded Python reader (`setup.sh:117-118`) and `model_router`/`backends` consume these.
- **Requires:** callers that read `airllm_*` keys tolerate a sentinel value (must not pass it to a downloader).
- **On bad input (sentinel reaches a backend):** the backend surfaces a one-line "deep model not configured — set AEROLLM_MODEL/AIRLLM_MODEL or edit [tool.arail.models]" notice and refuses to download. It does NOT crash and does NOT fall back to a 70B pull.

### `install_models()` (setup.sh)
- **Promises:** on exit, either `ai-eng` exists in Ollama, or a clear `warn` line tells the user the one command to run. Setup never aborts on a pull failure (existing contract, preserved).
- **Requires:** Ollama binary present (guarded). Network for the pull (degrades gracefully if absent — see Failure modes).
- **On bad input:** tag 404 → quiet fallback (2a). Network down → `warn` + continue, no crash.

### Deep backend default (`backends.py` AirLLMBackend, `airllm_worker.py`, app.py `DEEP_BACKENDS`/config)
- **Promises:** `AIRLLM_MODEL` default is the sentinel, not `meta-llama/Llama-3.1-70B`. A maximus operator who has not chosen a deep model gets a notice, not a 70B paging storm.
- **Requires:** env override (`AIRLLM_MODEL` / `AEROLLM_MODEL`) still wins when set — operators self-select the ceiling.
- **On bad input:** sentinel → notice; unknown model → existing loader error path (unchanged).

### NOTICE/THIRD_PARTY attribution file (new)
- **Promises:** the qwen base of ai-eng is attributed in a license-compliant, non-marketing location with the correct license name and upstream URL.
- **Requires:** kept in sync if the base ever changes.

---

## Part 1 — Maximus deep slot → 20–30B placeholder

### Sentinel convention (design the placeholder so the build can't pick a model)

Use a single, greppable sentinel string everywhere a deep-model default lived:

```
__TODO_DEEP_MODEL__
```

Every occurrence is paired with a one-line comment in the canonical form:

```
# TODO(deep-model): set the 20–30B open deep model id here. See ARCHITECTURE
#   sprint 2026-05-30-model-hosting-reframe § Part 1. Until set, deep mode
#   shows a "configure your deep model" notice — it does NOT download anything.
__TODO_DEEP_MODEL__
```

A repo-wide `grep -rn "__TODO_DEEP_MODEL__"` must return every deep-model decision point and nothing else. CI/QA asserts the sentinel is NOT a resolvable model id.

### Fate of the orphaned keys / AirLLM opt-in path — **DEPRECATE, do not delete.**

- `airllm_minimalist` / `airllm_maximus` / `airllm` (pyproject `[tool.arail.models]`): **repoint values to the sentinel**, keep the keys (forks and `setup.sh:117-118` read them). Add a deprecation comment: these were the 70B/405B defaults; the weight class is wrong for target hardware; operators who genuinely want layer-streaming set `AIRLLM_MODEL` explicitly.
- `ARAIL_INSTALL_AIRLLM=1` opt-in path (`setup.sh:572-586`, `pyproject` `airllm` extra, `package-sources.airllm`): **KEEP unchanged.** It is an explicit power-user opt-in; removing it is out of scope and would break the documented CUDA/Linux escape hatch. Only the *default model id* AirLLM resolves to changes (now sentinel, so a power user who installs AirLLM but sets no model gets the notice instead of a surprise 70B).
- The 20–30B placeholder is surfaced as a **maximus quick-download in the chat catalog** (a new `tier: flagship` browse row with `install: ""` and a description that says "set the deep model id — see docs"), NOT a setup auto-install. This honors the single-auto-install invariant.

### Deep-mode latency/footprint bar (architect sets the order of magnitude per VISION WC#2)

When the operator eventually picks a concrete 20–30B 4-bit model, the smoke bar on the 36 GB reference machine is:
- **Resident footprint ≤ ~20 GB** (a 30B 4-bit is ~16–18 GB weights + KV headroom; must leave room for the OS + portal so no paging).
- **Time-to-first-token ≤ 60 s** cold, **≤ 10 s** warm.
- **No OOM across two consecutive deep-mode smoke runs.**

This bar is recorded for the follow-up sprint that picks the model; this sprint ships only the sentinel, so the bar is documentation, not a test gate this sprint. If a chosen model fails it twice → escalate to visionary (VISION disconfirming evidence).

---

## Part 2 — ai-eng single published tag (DEFERRED collapse; see Gate A)

- **2a this sprint:** rewrite `install_models()` lines 768-799 so the fallback is honest and single-purpose. Production path = pure `ollama pull qukaizen/ai-eng:3b` (no create). Preview path = pull base + `ollama create ai-eng -f Modelfile.preview`, with the base id read from `[tool.arail.models].ai_eng_preview` (not hardcoded), and NO user-facing qwen wording in the log lines (say "preview base" / "fallback base", not "qwen2.5:7b" in the narrative `info` lines; the literal id may appear in the manual-recovery `warn` and in the pyproject key since that is operator-facing config, not marketing).
- **Modelfile.production:** KEEP as the internal build recipe (VISION says so). It is `FROM qukaizen/ai-eng:3b` — only relevant once the tag publishes; harmless to keep. Strip the qwen wording? It has none. Keep its Opus-distilled SYSTEM prompt.
- **Modelfile.preview:** KEEP this sprint (it is the only thing the 2a fallback can build from while the tag 404s). It MUST retain its `FROM qwen2.5:7b` line (that is the unavoidable internal base reference — a Modelfile cannot exist without a FROM). Strip the qwen *narrative* from its SYSTEM prompt (the "qwen2.5:7b serves as a stand-in" sentence is marketing-ish self-description visible to nobody but is also unnecessary; reduce to the neutral persona text). **The `FROM qwen2.5:7b` line is the one surviving qwen reference VISION WC#3 explicitly permits.**
- **Legacy `ai-engineer`→`ai-eng` alias migration** (`setup.sh:753-766`, `app.py:6001-6032`): KEEP unchanged. It is correct and orthogonal.
- **2b follow-up (deferred):** delete Modelfile.preview, delete the fallback ladder, make setup a pure single pull. Gated on `scripts/check_ai_eng_tag.sh` returning 0.

---

## Part 3 — Hide qwen lineage (per-file classification)

Classification key: **(a)** user-facing marketing → STRIP; **(b)** license-required attribution → MUST KEEP (move to NOTICE); **(c)** unavoidable internal base ref → KEEP minimal.

Scope rule from VISION WC#3: this is about **ai-eng's identity only.** Standalone Qwen catalog rows (qwen3:4b, qwen2.5-coder:7b, the Qwen family browse entries) STAY — they are honest listings of models the user can pull. The `catalog/models.toml`, `docs/CERTIFIED_MODELS.md`, `research/`, `scripts/build_ai_eng.py`, benchmark, and test references to qwen are NOT ai-eng-identity marketing and are OUT OF SCOPE (they are internal build/bench/research artifacts or honest standalone listings).

### Files to STRIP (class a — ai-eng identity marketing)

| File:line | Current | Classification | Action |
|---|---|---|---|
| `src/arail/chat/models_catalog.yaml:22-39` (ai-eng entry) | `family: qukaizen`; description mentions "falls back to qwen2.5:7b"; `install:` is the 4-command qwen ladder | (a) | Strip the qwen fallback sentence from `description`. Rewrite `install` to `ollama pull qukaizen/ai-eng:3b` (browse-row install; the *setup* fallback lives in setup.sh, not the catalog string). `family: qukaizen` stays. Rebrand description: "ARAIL's default local assistant — a 3B Opus-4.7-distilled AI engineering expert from QuKaiZen's Project Nucleus." |
| `pyproject.toml:127-128` (comment) | "falls back to the preview base (qwen2.5:7b + AI Engineer persona via Modelfile)" | (a)/operator-config | Soften to "falls back to a preview base until the 3B weights publish" — the `ai_eng_preview` key value below is the config, the comment need not name qwen. |
| `README.md:64` maximus row "Frontier-scale local inference, full bench." | (a) + Gate B | STRIP/REWRITE — see § Honest framing. |
| `README.md:67` "(Qwen, Gemma, Phi, DeepSeek-R1, etc.)" | (a) but honest standalone listing | KEEP — this is the browse gallery, not ai-eng lineage. |
| `CLAUDE.md:54` "frontier-scale bench"; `CLAUDE.md:62` qwen fallback prose | (a) | Rewrite frontier line (§ Honest framing); soften qwen-fallback prose to "a preview base." |
| `CHANGELOG.md:31-34, 84-85` qwen2.5:7b fallback prose | (a) historical | Add a NEW changelog entry for this sprint (Unreleased section). Do NOT rewrite shipped 1.0.0 history — historical accuracy. New entry describes the reframe and points qwen to NOTICE. |
| `docs/INSTALL.md:256` "pulls `qwen2.5:7b` (~5 GB) and uses it as the preview base" | (a) | Soften to "pulls a preview base (~5 GB)"; keep the operator-facing manual command in a NOTE if needed. |
| `docs/RELEASE_v1.0.0.md:59,157` | (a) historical release doc | LEAVE — frozen release artifact for 1.0.0. Out of scope. |
| `src/arail/portal/templates/tuning.html:111` "Run frontier-scale models locally" | (a) + Gate B | Rewrite to honest framing (see § Honest framing). |

### Files that MUST KEEP attribution (class b)

| Location | Why |
|---|---|
| **NEW `NOTICE` file at repo root** | Holds the license-required attribution: "ai-eng is distilled from / built on Qwen2.5-3B-Instruct (© Alibaba Cloud), licensed under <SPDX id confirmed at build>. Upstream: https://huggingface.co/Qwen/Qwen2.5-3B-Instruct". This is the home for the lineage VISION says must be *attributed but not advertised*. Also attribute it in the Ollama tag's model card when published (out of repo, note in NOTICE). |
| `LICENSE` (existing MIT) | Add a one-line pointer: "Bundled/derived model weights carry their own licenses; see NOTICE." |

This resolves the visionary's tension #1: the line between "not advertised" (strip from catalog/README/Modelfile narrative) and "not attributed" (NEVER — attribution lives in NOTICE + model card). MIT on ARAIL code does not override the base's license; NOTICE makes ARAIL compliant.

### Files that KEEP a minimal internal reference (class c)

| Location | Reference | Why unavoidable |
|---|---|---|
| `models/ai-eng/Modelfile.preview:1` | `FROM qwen2.5:7b` | A Modelfile must name its base. This is the single permitted qwen reference per WC#3. |
| `pyproject.toml ai_eng_preview` key value | `qwen2.5:7b` | Operator-facing config / the actual base the fallback pulls. Config, not marketing. |
| `scripts/build_ai_eng.py`, `build_ai_eng.sh`, `bench_ai_eng.py`, `BENCH-v2.1.md`, `bench-prompts.v2.1.yaml` | Qwen2.5-3B base refs | Internal build/bench recipe — not user-facing. Out of scope. |
| `catalog/models.toml`, standalone catalog qwen rows | Qwen family listings | Honest standalone model listings, not ai-eng identity. Out of scope. |

---

## Honest framing rewrite (resolves Gate B / tension #2)

The maximus tier must not promise "frontier-scale local inference" while defaulting to a 20–30B deep model. Exact replacement copy:

- **README.md:64 maximus "Good for" cell** →
  `The full bench. The heaviest model that runs *well* on your machine — with cloud frontier models one click away in the Chat Compute Source.`
- **README.md:64 maximus "What you get" cell** keep AeroLLM mention but drop "frontier-scale streaming" → `**AeroLLM** deep-mode runtime (the heaviest local model that runs well) · Anthropic SDK · LangChain · full cloud SDKs`.
- **CLAUDE.md:54** → `+ Admin · Docs · Notebooks · **AeroLLM** deep-mode runtime · Anthropic SDK · LangChain · full cloud SDKs — the full local bench, cloud frontier one click away`.
- **pyproject.toml `[tool.arail.tiers].maximus.description`** → replace "full cloud catalog. Adds AeroLLM as the deep-mode runtime…" tail with "…full cloud catalog. Adds AeroLLM deep mode — the heaviest model that runs well locally; cloud frontier models are one click away via Compute Source."
- **tuning.html:111** → `Run the heaviest models your silicon handles well — layer-streamed off NVMe, tuned for the hardware you own. Frontier-scale models are one click away in the cloud.`

This keeps the maximus promise truthful: local = heaviest-that-runs-well; frontier = cloud via the existing Compute Source pivot (which aligns with the product's pluggable-provider thesis in MEMORY).

> Out of scope (do NOT touch this sprint): `src/arail/agents/builtin_seed.py` "frontier-scale" auto-goal text and `model_specs.py:409` "frontier-scale and auto-default" — these describe AeroLLM's *aspirational throughput target* and the must-stream threshold logic, not the maximus tier marketing promise. Leaving them avoids scope drift into the autoresearch/dispatch surfaces.

---

## Per-file edit list (builder: no further decisions needed)

1. **`pyproject.toml`**
   - `[tool.arail.models]`: `airllm_minimalist`, `airllm_maximus`, `airllm` → `__TODO_DEEP_MODEL__` each, with the canonical TODO comment block. Keep keys.
   - Soften the `ai_eng_production`/`ai_eng_preview` comment (drop qwen narrative; keep the `ai_eng_preview = "qwen2.5:7b"` value as operator config).
   - `[tool.arail.tiers].maximus.description`: honest-framing rewrite (above).
   - Leave `aerollm_*`, `coder_*`, `airllm` extra, `package-sources` untouched (out of scope; aerollm defaults are a separate concern, already a "proven floor").

2. **`scripts/setup.sh`**
   - `:69-71` `AIRLLM_MODEL_ID/_MIN_ID/_MAX_ID` → `__TODO_DEEP_MODEL__` + TODO comment.
   - `:986-989` tier-resolution `case`: replace `meta-llama/Llama-3.1-405B`/`-70B` literal fallbacks with `__TODO_DEEP_MODEL__`.
   - `:730-808 install_models()`: rewrite the ai-eng block per Part 2a — clean production-pull-no-create path; honest fallback that reads the preview base id from config and uses neutral "preview base" wording in `info` lines; preserve idempotency, the `ai-engineer` alias migration, and `ARAIL_SKIP_OLLAMA`. Update the `:742-743` manual-recovery `warn` to the new single command set.
   - Add network/offline guard around the probe (see Failure modes).

3. **`scripts/check_ai_eng_tag.sh`** (NEW) — one-liner: `curl -fsS -m 8 https://registry.ollama.ai/v2/qukaizen/ai-eng/manifests/3b >/dev/null` → exit 0 if published. Used by the 2b follow-up and by a QA test that documents the deferral.

4. **`src/arail/router/backends.py:987-990`** — `AIRLLM_MODEL` default `meta-llama/Llama-3.1-70B` → `__TODO_DEEP_MODEL__`; add sentinel-guard so a sentinel value yields a clear "deep model not configured" error instead of attempting a load. Update the `:992` comment.

5. **`src/arail/router/airllm_worker.py:54`** — same default swap to sentinel + same guard (this is the subprocess that actually loads; the guard here is the OOM-safety backstop).

6. **`src/arail/portal/app.py`** — `:5996` `DEEP_BACKENDS["airllm"].default_model` → sentinel. `:6229`, `:6297`, `:6566-6572`, `:6596`, `:6665`, `:9207` Llama-3.1-70B literals: swap defaults to sentinel and update the human-readable `description` strings to drop "Llama-3.1-70B default; max tier bumps to 405B" → "deep model is operator-configured (see NOTICE/docs)". The HF-download hint strings (`:6566-6572`) become "set your deep model first" guidance, not a 70B download command. KEEP `_resilient_chat_default` qwen2.5:7b fallback (`:6030-6031`) — it is the runtime safety net matching the still-present preview path; not marketing.

7. **`src/arail/chat/models_catalog.yaml`** — ai-eng entry (`:22-39`): strip qwen fallback sentence, fix `install` and `description` per Part 3. Add ONE new browse row for the 20–30B deep placeholder (`tier: flagship`, `install: ""`, description points to docs/NOTICE; do NOT name a real model). Leave all other rows.

8. **`models/ai-eng/Modelfile.preview`** — keep `FROM qwen2.5:7b`; reduce SYSTEM prompt to the neutral persona (drop the "qwen2.5:7b serves as a stand-in" sentence). **`Modelfile.production` untouched.**

9. **`NOTICE`** (NEW, repo root) — Qwen2.5-3B attribution + confirmed SPDX license id + upstream URL. (Builder confirms the exact license before writing.)

10. **`LICENSE`** — append one line pointing to NOTICE for bundled/derived model licenses.

11. **`README.md:64`, `CLAUDE.md:54,62`, `src/arail/portal/templates/tuning.html:111`** — honest-framing rewrites (above); soften qwen-fallback prose.

12. **`CHANGELOG.md`** — add an Unreleased entry describing the reframe (deep slot → sentinel, AirLLM 70B/405B defaults deprecated, ai-eng install honesty pass, qwen lineage moved to NOTICE, maximus copy rewrite). Do NOT rewrite 1.0.0 history.

13. **`docs/INSTALL.md:256`** — soften qwen narrative to "a preview base (~5 GB)."

> Explicitly OUT OF SCOPE (do not edit): `catalog/models.toml`, `docs/CERTIFIED_MODELS.md`, `docs/maximus.plan.md`, `docs/build-and-finetune-plan.md`, `docs/plans/*`, `docs/chat-studio.spec.md`, `docs/DEBUG_QWEN25_7B_CASE_STUDY.md`, `research/**`, `scripts/build_ai_eng.*`, `scripts/bench_ai_eng.py`, `models/ai-eng/BENCH*`, `model_specs.py`, `builtin_seed.py`, `pkb_seed.py`, `costs.py`, all `tests/**` except those the edits above necessarily break (update those, see Test strategy). `docs/RELEASE_v1.0.0.md` and `docs/SMOKE_TEST_v1.0.0.md` are frozen release artifacts.

---

## Failure modes

| Failure | Detection | Recovery |
|---|---|---|
| ai-eng tag 404 at setup (current reality, Gate A) | probe returns non-200 | 2a fallback: pull preview base + create from Modelfile.preview. Setup never aborts. **This is the shipped path until tag publishes.** |
| Network down / airgapped clone during setup | `ollama pull` fails / times out (existing `timeout 900`) | `warn` + continue; print the one manual command. No crash, no partial-state. Add explicit "offline — skipping ai-eng pull" branch so the log is honest, not a scary stack of pull errors. |
| Sentinel `__TODO_DEEP_MODEL__` reaches a backend loader | guard checks `model_name == sentinel` before any download/load | Raise a clear "deep model not configured" notice; NO download (OOM-safety), NO 70B fallback. |
| Operator on 36 GB box clicks deep mode with no model set | sentinel guard | Friendly notice in chat + Admin: "Pick a deep model — see docs." Zero bytes downloaded. (Directly fixes the VISION persona-2 pain.) |
| Builder accidentally resolves the sentinel to a real model | QA test asserts sentinel is present in all listed defaults AND is not a valid Ollama/HF id | CI/QA BLOCK. |
| Qwen base attribution missing (license risk) | QA test asserts `NOTICE` exists and names Qwen2.5-3B + a license id; grep asserts no qwen lineage string in README/CLAUDE/catalog ai-eng description | BLOCK until NOTICE present. Resolves tension #1. |
| Modelfile.preview deleted prematurely (would brick fallback) | QA test asserts `models/ai-eng/Modelfile.preview` still exists with a `FROM` line | BLOCK (this sprint must NOT delete it). |
| Maximus copy still says "frontier-scale" | grep test for "frontier-scale"/"Frontier-scale" in README:64, CLAUDE:54, tuning.html:111, pyproject maximus desc | BLOCK; resolves tension #2. |
| Existing tests reference Llama-3.1-70B as the AirLLM default | test run | Update the specific tests whose expectation is now the sentinel (test_aerollm_defaults expects AEROLLM, unaffected; test_dispatch_35b/must_stream use 70B as a *streaming-threshold fixture*, not the default — leave those, they test the regex). Only `app.py`/`backends.py` default-assertion tests, if any, change. |
| OOM during testing (MEMORY warning) | n/a | This sprint is config/copy — QA must NOT spawn concurrent uvicorn workers + LLM loads. Deep-mode smoke is DEFERRED with the model pick. Setup test runs with Ollama mocked / `ARAIL_SKIP_OLLAMA=1`. No real weight loads in CI. |

Every row maps to a test below.

---

## Test strategy

QA allocation per arail gating: **30% setup / 30% Buddy / 20% security / 10% happy / 10% regression.** Setup-on-clean-machine is the headline.

- **Setup (30%) — headline:**
  - `install_models()` with tag-404 mock (matches reality): asserts exactly one fallback path, preview base id read from config, `ollama create -f Modelfile.preview` invoked, neutral wording (no "qwen2.5:7b" in `info` narrative lines), setup exit 0.
  - tag-200 mock (future state): asserts pure single `ollama pull qukaizen/ai-eng:3b`, NO create step, NO base pull.
  - offline mock: pull fails → `warn` + continue, exit 0, manual command printed.
  - idempotency: ai-eng already present → skip; legacy `ai-engineer:latest` → `ollama cp` alias path intact.
  - `scripts/check_ai_eng_tag.sh` returns nonzero today (documents the deferral; flips the 2b sprint).
  - sentinel-not-resolvable assertion across all deep defaults (pyproject, setup.sh, backends.py, airllm_worker.py, app.py).

- **Buddy (30%):** ai-eng persona unchanged behaviorally — Modelfile.production/preview SYSTEM prompt still yields the "ai-eng, AI engineering expert" identity; assert the preview SYSTEM prompt no longer contains the qwen self-description but still defines the persona. (No live model load — assert on Modelfile text + the catalog/default resolution, not generated tokens, per OOM-safety.)

- **Security (20%):**
  - NOTICE exists, names Qwen2.5-3B and a license id, contains upstream URL.
  - No qwen lineage string in user-facing ai-eng surfaces (README ai-eng cells, CLAUDE ai-eng prose, catalog ai-eng `description`).
  - The lone permitted qwen ref (`Modelfile.preview` FROM line) present and is the ONLY one outside config/NOTICE.
  - Sentinel guard prevents any download path — assert no downloader is reachable with a sentinel model id (the OOM/SSD-safety property).
  - `LAB_MODE=airgapped` regression: assert cloud gating untouched (no diff in airgap audit / provider endpoints).

- **Happy (10%):** clean-machine sim (Ollama present, tag 404) → setup → `ai-eng:latest` resolvable → `_resilient_chat_default("ai-eng:latest")` returns it. Maximus tier description renders honest copy.

- **Regression (10%):**
  - grep gate: no "frontier-scale"/"Frontier-scale" in the four rewritten surfaces.
  - existing 70B-as-threshold-fixture tests (`test_must_stream_rule`, `test_dispatch_35b_enforcement`, `test_frontier_threshold`) still pass — they assert the streaming-threshold regex, not the default, and must be unaffected (proves the swap didn't leak into dispatch logic).
  - `Modelfile.preview` still present with FROM line.

**No performance tests this sprint** (config/copy; deep-mode latency bar is documentation for the model-pick follow-up). **No live LLM loads in CI** (OOM-safety).

---

## Tech debt

**Added:**
- `__TODO_DEEP_MODEL__` sentinel is live in shipped config — maximus deep mode is non-functional until an operator sets a model. *Mitigated:* friendly notice, documented, follow-up ticket. This is intentional honesty (no model > wrong model), not accidental debt.
- The 2a fallback ladder survives — the "single clean pull" end-state is deferred. Follow-up ticket: **"2b: collapse ai-eng setup to pure single pull; delete Modelfile.preview; gated on `check_ai_eng_tag.sh`==0."**
- Follow-up ticket: **"Pick the concrete 20–30B deep model; meet the ≤20 GB / ≤60 s-TTFT / no-OOM bar on the 36 GB reference machine."**

**Repaid:**
- Removes the 70B/405B over-promise default — the single biggest honesty/footgun debt on the maximus tier.
- Removes the silent 7B-wearing-3B-label leak from user-facing copy.
- Centralizes qwen attribution in NOTICE (compliance debt repaid).
- Replaces a 4-command catalog `install` string with a clean path.

**Net:** roughly neutral, leaning negative (good). The two added debts are *deferred-by-gate*, each with a home ticket and an automatic trigger, not silent rot.

---

## Recommended implementation order

1. **NOTICE + LICENSE pointer** (unblocks the license gate; do first so the honesty change is compliant before any qwen strip).
2. **Sentinel rollout** — pyproject, setup.sh:69-71/986-989, backends.py, airllm_worker.py, app.py defaults + guards. (Part 1.)
3. **setup.sh install_models() rewrite** (Part 2a) + `check_ai_eng_tag.sh`.
4. **Modelfile.preview SYSTEM trim; catalog ai-eng entry + new deep placeholder row** (Part 3 + Part 1 catalog surface).
5. **Copy rewrites** — README, CLAUDE.md, tuning.html, pyproject tier desc, docs/INSTALL.md, CHANGELOG Unreleased. (Part 3 + Honest framing.)
6. **Tests** per strategy; run full suite; confirm threshold-fixture tests unaffected.
