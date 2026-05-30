# Architecture: Model-Hosting Strategy Reframe

**Date:** 2026-05-30
**Spec:** [VISION.md](./VISION.md) (sprint 2026-05-30-model-hosting-reframe)
**Branch:** `qukaizen/arail-kv-available-budget` (current); builder should branch `qukaizen/arail-model-hosting-reframe` off `main`.

> **REVISION 2 (2026-05-30):** Supersedes Gate A's "defer the single-pull, wait for
> the ollama.ai `qukaizen/` registry tag" decision. The user verified
> `qukaizen/ai-eng:3b` returns 404 on the Ollama registry and has decided to
> **SELF-HOST** the bottled ai-eng model rather than depend on the ollama.ai
> `qukaizen/` namespace ("package it up however. We can host it on qukaizen.com or
> huggingface or both… Or github"). Sections touched by this revision are marked
> **[REVISED v2]**. Everything else (the `__TODO_DEEP_MODEL__` sentinel, the
> qwen-hiding edit list, the NOTICE attribution file, the frontier-scale honest
> rewrite) is intact from Revision 1.

---

## Restatement

ARAIL today over-promises against its target hardware (36 GB Apple Silicon) in two ways. First, the maximus deep-mode default points at AirLLM-streamed Llama-3.1-70B/405B, which OOMs or crawls on that class of box — the advertised "frontier-scale" tier diverges from the lived experience. Second, the default-assistant install (`ai-eng`) runs a fragile probe-then-fallback ladder against `qukaizen/ai-eng:3b` (an ollama.ai tag that **does not exist** — confirmed 404), and on miss pulls a 5 GB `qwen2.5:7b` and builds an `ai-eng` from a Modelfile — a second auto-download on an OOM-sensitive machine that ships a 7B wearing a "3B" label and advertises the qwen lineage everywhere. **[REVISED v2]** Rather than wait on the ollama.ai `qukaizen/` namespace, ARAIL will **self-host** the bottled ai-eng GGUF (qwen2.5:3b base + QuKaiZen LoRA merged) on HuggingFace (primary, pulled natively via `ollama pull hf.co/...`), mirrored to a GitHub Release asset, optionally on qukaizen.com. This sprint does: (1) repoint the maximus deep slot to a TODO-placeholder 20–30B quick-download model (not an auto-install) and deprecate the 70B/405B AirLLM defaults; (2) rewrite setup.sh to pull the self-hosted ai-eng artifact across a mirror fallback order, verify its digest, and degrade gracefully on total failure; (3) strip the qwen lineage from all user-facing copy while preserving license-required attribution in non-marketing locations, and honestly rewrite the maximus "frontier-scale" promise; (4) ship a `scripts/package_ai_eng.sh` scaffold that documents/automates merge→GGUF→Modelfile→upload (weights/upload steps are manual TODOs — no weights are invented in-repo).

---

## GATE RESULTS (the two hard gates the architect owns)

### Gate A — is a self-hostable ai-eng artifact path viable? **YES (via self-hosting). → SHIP the single-pull collapse against a self-hosted host.** **[REVISED v2]**

Revision 1 verified against the live Ollama registry on 2026-05-30:

```
GET https://registry.ollama.ai/v2/qukaizen/ai-eng/manifests/3b      → 404
GET https://registry.ollama.ai/v2/qukaizen/ai-eng/manifests/latest  → 404
GET https://registry.ollama.ai/v2/library/qwen2.5/manifests/7b      → 200  (control)
```

Revision 1 therefore DEFERRED the single-pull collapse (no published tag to pull).
The user has now removed that dependency: **we self-host.** The clean native path is
Ollama's built-in HuggingFace GGUF support:

```
ollama pull hf.co/<org>/<repo>:<quant>
```

Ollama resolves an `hf.co/...` reference directly against any public HuggingFace
GGUF repo — no ollama.ai namespace, no `ollama create`, no Modelfile build step on
the user's machine. This makes the single-pull win condition achievable **once the
user uploads the GGUF**, without ever depending on the ollama.ai `qukaizen/` org.

**Decision — Part 2 ships the self-hosted single-pull path, with a guarded fallback net:**

The artifact does not exist in-repo yet (no merged weights; upload is a manual TODO).
So the shipped setup logic is: **try the self-hosted pull across a mirror fallback
order; if every self-hosted host 404s/fails (i.e. the GGUF is not uploaded yet, or
the machine is offline), fall back to the existing preview path (qwen2.5:7b +
Modelfile.preview) as the last-resort safety net.** When the user completes the
upload, the self-hosted pull succeeds and the preview net is never reached — Win
Condition #1 ("one pull, zero qwen2.5:7b pulls") is met automatically, with **no code
change and no second sprint** (the deferral from Rev 1 is dissolved).

> **Fate of `Modelfile.preview` / the qwen fallback net — KEEP this sprint, drop later.**
> Rev 1 kept it because the ollama.ai tag 404'd. We still keep it this sprint for the
> same operational reason: until the self-hosted GGUF is uploaded, the preview net is
> the only thing between a cloner and a working lab. It is the documented last-resort
> safety net, not a "surprise" pull. A follow-up ticket (**2b**) deletes Modelfile.preview
> and the fallback ladder once the self-hosted artifact is confirmed live — gated on a
> machine-checkable probe (`scripts/check_ai_eng_artifact.sh`, see Edit list) returning 0.

> Net effect on Win Condition #1: **met-on-upload.** The shipped code path is correct
> and complete; it succeeds the moment the GGUF lands on HuggingFace. Mark WC#1 as
> "met-on-upload" in the sprint ledger; do not claim it green until the artifact probe
> passes.

### Gate B — does a 20–30B deep model still deliver "frontier-scale"? **NO. → rewrite the copy. (resolved below, Part 1 + § Honest framing)** *(unchanged from Rev 1)*

A 20–30B local model is not frontier-scale by 2026 standards. The maximus tier copy is rewritten so a 30B deep model is not a silent downgrade. See § Honest framing rewrite.

---

## Distribution channel decision **[REVISED v2 — NEW SECTION]**

### Recommendation: HuggingFace primary, GitHub Release mirror, qukaizen.com optional tertiary.

| Host | Role | Pull mechanism | Rationale |
|---|---|---|---|
| **HuggingFace** (`hf.co/<org>/<repo>:<quant>`) | **PRIMARY** | `ollama pull hf.co/qukaizen/ai-eng-3b-gguf:Q4_K_M` (Ollama-native) | Cleanest path: Ollama resolves HF GGUF repos directly — no `ollama create`, no Modelfile on the user's box, single command. HF provides CDN, resumable downloads, SHA digests, model cards (the attribution home for the tag), versioning. Free public hosting. This is the strong default. |
| **GitHub Release asset** | **MIRROR** | download `.gguf` to `lab/models/`, then `ollama create ai-eng -f <generated Modelfile>` pointing at the local file | Survives HF outage/ratelimit. Repo-adjacent (same org as the code). GGUF as a release asset is a plain HTTPS download — works behind corp proxies that block HF. Release assets carry a digest in the release body for checksum verification. |
| **qukaizen.com** | **OPTIONAL tertiary** | same as GitHub mirror (HTTPS GGUF download → local create) | Only if the user wants a branded/controlled URL. Adds ops burden (TLS, bandwidth, uptime). Recommend deferring until HF+GitHub prove insufficient. Wire the env hook now; leave the URL a TODO. |

**Placeholder org/repo (clearly marked — user fills in):** `qukaizen/ai-eng-3b-gguf`,
quant tag `Q4_K_M`. Both are `__PLACEHOLDER__`-commented in code; the build must NOT
treat them as confirmed-live.

### Exact pull commands + fallback order setup will run

setup.sh tries, in order, stopping at the first success:

```
# 1. HuggingFace (primary) — Ollama-native, no local Modelfile build
ollama pull "hf.co/${ARAIL_AI_ENG_HF_REPO:-qukaizen/ai-eng-3b-gguf}:${ARAIL_AI_ENG_QUANT:-Q4_K_M}"

# 2. GitHub Release mirror — HTTPS GGUF download → verify digest → local create
curl -fL -o "$GGUF_TMP" "${ARAIL_AI_ENG_GH_URL:-https://github.com/qukaizen/arail/releases/download/ai-eng-3b/ai-eng-3b-Q4_K_M.gguf}"
#   sha256 check against ARAIL_AI_ENG_SHA256 (see Supply-chain below)
ollama create ai-eng -f "$GENERATED_MODELFILE"   # FROM ./<local gguf>

# 3. qukaizen.com mirror (optional; only if ARAIL_AI_ENG_CDN_URL set)
curl -fL -o "$GGUF_TMP" "$ARAIL_AI_ENG_CDN_URL"
#   sha256 check → local create

# 4. LAST-RESORT preview net (existing): pull qwen2.5:7b + Modelfile.preview
#    Reached only if 1–3 all fail (artifact not uploaded yet, or offline).
```

All host URLs/repos/quant/digest are env-overridable (`ARAIL_AI_ENG_HF_REPO`,
`ARAIL_AI_ENG_QUANT`, `ARAIL_AI_ENG_GH_URL`, `ARAIL_AI_ENG_CDN_URL`,
`ARAIL_AI_ENG_SHA256`) and default to values read from `[tool.arail.models]` in
pyproject. Forks rebrand by overriding env or editing pyproject — no code edits.

### Supply-chain / digest verification **[REVISED v2 — NEW]**

ARAIL runs on other people's machines (arail CLAUDE.md security gating). A GGUF
downloaded over HTTPS and fed to `ollama create` is an untrusted-input surface
(arbitrary weights → model behavior). Mitigations, in priority order:

1. **HuggingFace primary path:** Ollama verifies the layer digests in the HF GGUF
   manifest on pull — this is the built-in integrity guarantee and the main reason HF
   is primary. No extra work for path 1.
2. **GitHub / CDN mirror paths:** these are raw `curl` downloads with NO built-in
   integrity check. setup.sh MUST verify `sha256sum` of the downloaded `.gguf` against
   a pinned expected digest (`ARAIL_AI_ENG_SHA256`, default read from
   `[tool.arail.models].ai_eng_sha256`) BEFORE `ollama create`. Mismatch → discard the
   file, `warn`, skip to the next fallback. The expected digest is published by
   `package_ai_eng.sh` (it prints the sha256 of the produced GGUF) and recorded by the
   user in pyproject + the GitHub release body.
3. The expected digest is a `__PLACEHOLDER_SHA256__` sentinel until the user runs the
   packaging script and fills it in. **Until a real digest is pinned, the mirror paths
   (2/3) MUST refuse to `create` from an unverified download** (fail-closed: a
   placeholder digest disables the mirror, it does not bypass the check). The HF path
   (1) and the preview net (4) remain available, so setup still completes — but we never
   silently load an unverified weight blob.

---

## Assumptions **[REVISED v2 — items 2, 8–11 added/changed]**

1. **Ollama is the runtime for ai-eng.** On Apple Silicon, setup skips Ollama by default (MLX is primary) unless `ARAIL_ENABLE_OLLAMA=1`. The ai-eng pull therefore only runs when Ollama is present (existing guard at `setup.sh:739`). This sprint does not change that guard.
2. **The bottled ai-eng = `qwen2.5:3b` base + QuKaiZen LoRA, merged and exported to GGUF, distilled from Opus 4.7 via Nucleus.** The base is confirmed by `scripts/build_ai_eng.py:47` (`DEFAULT_BF16_BASE = "Qwen/Qwen2.5-3B-Instruct"`). The merged GGUF does NOT exist in-repo; `package_ai_eng.sh` is the scaffold the user runs to produce and upload it. **[REVISED v2]**
3. **Qwen2.5-3B ships under the Qwen RESEARCH/Qwen license, not Apache-2.0.** (The builder MUST confirm the exact license of `Qwen/Qwen2.5-3B-Instruct` before BUILD and record the SPDX id in the NOTICE file. Treat it as attribution-required regardless; attribution is cheap, a license violation is not.) The merged-LoRA GGUF is a derivative and inherits the base license obligations — `package_ai_eng.sh` must emit a LICENSE/NOTICE alongside the upload and the HF model card must carry it. **[REVISED v2]**
4. **The 20–30B deep-model ID is a deliberate TODO.** This document does NOT pick a model. The placeholder is `__TODO_DEEP_MODEL__` (sentinel convention below). The build must not resolve it to a real weight.
5. **Deep models are pull-on-demand, never setup auto-installs.** Confirmed by VISION wedge. Part 1 only changes a *default ID*, not the install trigger.
6. **`LAB_MODE=airgapped` is invariant.** No code in this sprint touches cloud-egress gating. The self-hosted pull is a model-fetch (same class as the existing `ollama pull`), gated by the existing Ollama-present guard, not a cloud-provider call. An airgapped clone with no network simply hits the offline branch (graceful skip). **[REVISED v2 — clarified the self-hosted pull is not a cloud-provider egress]**
7. **The reference hardware is a 36 GB Apple Silicon machine.** Latency/footprint bars below are set against it.
8. **`hf.co/<org>/<repo>:<quant>` is resolvable by the installed Ollama version.** HF-GGUF native pull is supported by current Ollama. The builder records the minimum Ollama version in the NOTE; if a user's Ollama is too old, the HF path fails cleanly and the GitHub mirror (raw download + create) covers them. **[REVISED v2 — NEW]**
9. **The chosen quant is `Q4_K_M` (~2 GB for a 3B), a PLACEHOLDER the user confirms.** Q4_K_M is the standard balanced quant for a 3B assistant on 36 GB. The user may change it via `package_ai_eng.sh` arg + `ARAIL_AI_ENG_QUANT`. The architecture does not depend on the exact quant. **[REVISED v2 — NEW]**
10. **The user owns the HF org and GitHub repo and will perform the upload + credential steps manually.** `package_ai_eng.sh` marks `huggingface-cli login` / `gh release upload` / qukaizen.com push as manual TODO steps; the repo never embeds credentials. **[REVISED v2 — NEW]**
11. **A pinned sha256 digest will exist for the mirror paths.** Until it does, mirror paths fail-closed (Supply-chain §). **[REVISED v2 — NEW]**

---

## Data flow **[REVISED v2]**

```
                         ./arailctl setup  (Ollama present)
                                   │
                                   ▼
            ┌──────────────────────────────────────────────────────────┐
            │  install_models()  [setup.sh]                              │
            │                                                            │
            │  1. ai-eng already present?  ──yes──► done                 │
            │  2. legacy ai-engineer:latest? ─yes─► cp alias ► done      │
            │  3. SELF-HOSTED FETCH (fallback order, first success wins):│
            │     ┌────────────────────────────────────────────────┐    │
            │     │ (1) ollama pull hf.co/<repo>:<quant>            │    │
            │     │       success → DONE (digest verified by ollama)│    │
            │     │ (2) curl GitHub release .gguf → sha256 verify   │    │
            │     │       ok → ollama create ai-eng -f <gen MF>→DONE│    │
            │     │       bad/placeholder digest → skip (fail-closed)│   │
            │     │ (3) curl qukaizen.com .gguf → sha256 verify→DONE│    │
            │     │ (4) LAST-RESORT preview net:                    │    │
            │     │       ollama pull qwen2.5:7b                    │    │
            │     │       ollama create ai-eng -f Modelfile.preview │    │
            │     └────────────────────────────────────────────────┘    │
            │     all fail / offline → warn + continue (no crash)        │
            └──────────────────────────────────────────────────────────┘
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

  ── Packaging (developer-side, run by the user, NOT setup) ──────────────
       scripts/package_ai_eng.sh:
         merge LoRA into qwen2.5:3b → export GGUF (Q4_K_M)
           → emit Modelfile + NOTICE → print sha256
           → [manual TODO] huggingface-cli upload / gh release upload / cdn push
```

The new branches: the **self-hosted fetch ladder** (HF → GitHub → CDN → preview net)
with **digest verification on the mirror paths**, the **sentinel-unresolved guard** on
the deep path, and the **packaging scaffold** (offline developer tool, not part of setup).

---

## Interface contracts **[REVISED v2 — install_models() and a new packaging contract]**

### `[tool.arail.models]` (pyproject.toml) — source of truth
- **Promises:** every key resolves to either a real model id OR the documented sentinel `__TODO_DEEP_MODEL__`. `setup.sh`'s embedded Python reader (`setup.sh:117-118`) and `model_router`/`backends` consume these. New keys: `ai_eng_hf_repo`, `ai_eng_quant`, `ai_eng_gh_url`, `ai_eng_cdn_url` (optional/empty), `ai_eng_sha256` (placeholder until packaged), `ai_eng_preview`.
- **Requires:** callers that read `airllm_*` keys tolerate a sentinel value (must not pass it to a downloader). Callers of the mirror url/digest keys tolerate placeholder values (must fail-closed, not download-and-trust).
- **On bad input (sentinel reaches a backend):** the backend surfaces a one-line "deep model not configured" notice and refuses to download. Placeholder digest → mirror path refuses to `create`.

### `install_models()` (setup.sh) **[REVISED v2]**
- **Promises:** on exit, either `ai-eng` exists in Ollama (via self-hosted HF pull, a digest-verified mirror, or the preview net), or a clear `warn` line tells the user the one command to run. Setup never aborts on a pull failure (existing contract, preserved).
- **Requires:** Ollama binary present (guarded). Network for the pull (degrades gracefully if absent). A pinned sha256 for the mirror paths to be usable.
- **On bad input:** HF 404 (not uploaded yet) → next mirror → preview net. Digest mismatch or placeholder digest → skip that mirror (fail-closed), try next. Network down → `warn` + continue, no crash, no partial Ollama state.

### `package_ai_eng.sh` (NEW developer-side scaffold) **[REVISED v2 — NEW]**
- **Promises:** given a base model + a LoRA dir (paths the user supplies), it documents and (where tools exist) automates: merge LoRA → convert to GGUF at a chosen quant → emit a `Modelfile` and a `NOTICE` → print the GGUF's sha256 → print the exact upload commands for HF / GitHub / CDN.
- **Requires:** the user supplies real weights/LoRA (NOT in-repo) and runs `huggingface-cli login` / `gh auth login` themselves. The script never embeds credentials and never invents weights.
- **On missing inputs:** if the base/LoRA paths don't exist, the script prints the documented manual steps and exits nonzero — it does NOT fabricate or download arbitrary weights. Upload steps are explicit `# TODO(manual):` blocks the user uncomments/runs.

### Deep backend default (`backends.py`, `airllm_worker.py`, app.py) — *unchanged from Rev 1*
- **Promises:** `AIRLLM_MODEL` default is the sentinel, not `meta-llama/Llama-3.1-70B`. A maximus operator who has not chosen a deep model gets a notice, not a 70B paging storm.
- **On bad input:** sentinel → notice; unknown model → existing loader error path.

### NOTICE/THIRD_PARTY attribution file (new) — *unchanged from Rev 1, scope widened*
- **Promises:** the qwen base of ai-eng is attributed in a license-compliant, non-marketing location with the correct license name and upstream URL. **[REVISED v2]** Also documents that the self-hosted HF model card and GitHub release MUST carry the same attribution (the GGUF is a redistributed derivative — attribution travels with the artifact, not just the repo).

---

## Part 1 — Maximus deep slot → 20–30B placeholder *(unchanged from Rev 1)*

### Sentinel convention

Use a single, greppable sentinel string everywhere a deep-model default lived:

```
__TODO_DEEP_MODEL__
```

Paired with the canonical comment:

```
# TODO(deep-model): set the 20–30B open deep model id here. See ARCHITECTURE
#   sprint 2026-05-30-model-hosting-reframe § Part 1. Until set, deep mode
#   shows a "configure your deep model" notice — it does NOT download anything.
__TODO_DEEP_MODEL__
```

A repo-wide `grep -rn "__TODO_DEEP_MODEL__"` must return every deep-model decision point and nothing else. CI/QA asserts the sentinel is NOT a resolvable model id.

### Fate of the orphaned keys / AirLLM opt-in path — **DEPRECATE, do not delete.**

- `airllm_minimalist` / `airllm_maximus` / `airllm` (pyproject `[tool.arail.models]`): **repoint values to the sentinel**, keep the keys. Add a deprecation comment: these were the 70B/405B defaults; the weight class is wrong for target hardware; operators who genuinely want layer-streaming set `AIRLLM_MODEL` explicitly.
- `ARAIL_INSTALL_AIRLLM=1` opt-in path (`setup.sh:572-586`, `pyproject` `airllm` extra, `package-sources.airllm`): **KEEP unchanged.** Only the *default model id* AirLLM resolves to changes (now sentinel).
- The 20–30B placeholder is surfaced as a **maximus quick-download in the chat catalog** (a new `tier: flagship` browse row with `install: ""` and a description that says "set the deep model id — see docs"), NOT a setup auto-install.

### Deep-mode latency/footprint bar (per VISION WC#2)

When the operator eventually picks a concrete 20–30B 4-bit model, the smoke bar on the 36 GB reference machine is:
- **Resident footprint ≤ ~20 GB.**
- **Time-to-first-token ≤ 60 s** cold, **≤ 10 s** warm.
- **No OOM across two consecutive deep-mode smoke runs.**

Documentation for the follow-up sprint that picks the model; not a test gate this sprint.

---

## Part 2 — ai-eng single self-hosted pull **[REVISED v2 — was "DEFERRED collapse"; now SHIPS against self-host]**

- **This sprint:** rewrite `install_models()` (`setup.sh:730-808`) to run the **self-hosted fetch ladder** (Distribution channel §): HF-native pull primary, GitHub-release + qukaizen.com mirrors (digest-verified, fail-closed on placeholder digest), preview net last. Production success path = a single `ollama pull hf.co/<repo>:<quant>` with NO local create step. The preview net retains `ollama create ai-eng -f Modelfile.preview`. All `info` narrative lines use neutral wording ("fetching ai-eng", "preview base") — no "qwen2.5:7b" in narrative (Part 3); the literal id may appear in the manual-recovery `warn` and the pyproject `ai_eng_preview` key (operator config).
- **`Modelfile.production`:** KEEP as the internal build recipe. Its `FROM` becomes the self-hosted reference (or stays as the build-time recipe — `package_ai_eng.sh` emits the authoritative Modelfile). Keep its Opus-distilled SYSTEM prompt. **[REVISED v2]**
- **`Modelfile.preview`:** KEEP this sprint (only thing the preview net can build from until the GGUF is uploaded). It MUST retain its `FROM qwen2.5:7b` line. Strip the qwen *narrative* from its SYSTEM prompt. **The `FROM qwen2.5:7b` line is the one surviving qwen reference VISION WC#3 explicitly permits.**
- **`package_ai_eng.sh`** (NEW) — the merge→GGUF→Modelfile→upload scaffold (Interface contracts §). Upload + credential steps are manual `# TODO`.
- **Legacy `ai-engineer`→`ai-eng` alias migration** (`setup.sh:753-766`, `app.py:6001-6032`): KEEP unchanged.
- **2b follow-up (deferred):** delete Modelfile.preview + the preview net once the self-hosted artifact is confirmed live. Gated on `scripts/check_ai_eng_artifact.sh` returning 0.

---

## Part 3 — Hide qwen lineage (per-file classification) *(unchanged from Rev 1)*

Classification key: **(a)** user-facing marketing → STRIP; **(b)** license-required attribution → MUST KEEP (move to NOTICE); **(c)** unavoidable internal base ref → KEEP minimal.

Scope rule from VISION WC#3: this is about **ai-eng's identity only.** Standalone Qwen catalog rows STAY. `catalog/models.toml`, `docs/CERTIFIED_MODELS.md`, `research/`, `scripts/build_ai_eng.py`, benchmark, and test references to qwen are OUT OF SCOPE.

### Files to STRIP (class a — ai-eng identity marketing)

| File:line | Current | Action |
|---|---|---|
| `src/arail/chat/models_catalog.yaml:22-39` (ai-eng entry) | `family: qukaizen`; description mentions "falls back to qwen2.5:7b"; 4-command qwen ladder `install` | Strip the qwen fallback sentence. **[REVISED v2]** Rewrite `install` to `ollama pull hf.co/qukaizen/ai-eng-3b-gguf:Q4_K_M` (self-hosted single pull; placeholder repo). `family: qukaizen` stays. Description: "ARAIL's default local assistant — a 3B Opus-4.7-distilled AI engineering expert from QuKaiZen's Project Nucleus." |
| `pyproject.toml:126-128` (comment) | "probes for the production tag first (qukaizen/ai-eng:3b) and falls back to the preview base (qwen2.5:7b…)" | **[REVISED v2]** Rewrite to: "Setup pulls the self-hosted ai-eng GGUF (HuggingFace primary, GitHub mirror); falls back to a preview base until the GGUF is uploaded." |
| `README.md:64` maximus row "Frontier-scale local inference, full bench." | STRIP/REWRITE — see § Honest framing. |
| `README.md:67` "(Qwen, Gemma, Phi, DeepSeek-R1, etc.)" | KEEP — browse gallery, not ai-eng lineage. |
| `CLAUDE.md:54` "frontier-scale bench"; `CLAUDE.md:62` qwen fallback prose | Rewrite frontier line (§ Honest framing); soften qwen-fallback prose to "a preview base." |
| `CHANGELOG.md` | Add a NEW Unreleased entry describing the reframe **+ self-hosted distribution**. Do NOT rewrite shipped 1.0.0 history. **[REVISED v2]** |
| `docs/INSTALL.md:256` "pulls `qwen2.5:7b` (~5 GB) and uses it as the preview base" | **[REVISED v2]** Rewrite to describe the self-hosted pull (HF primary, GitHub mirror) and the preview base only as the offline/not-yet-uploaded fallback. |
| `docs/RELEASE_v1.0.0.md:59,157` | LEAVE — frozen release artifact. |
| `src/arail/portal/templates/tuning.html:111` "Run frontier-scale models locally" | Rewrite (§ Honest framing). |

### Files that MUST KEEP attribution (class b)

| Location | Why |
|---|---|
| **NEW `NOTICE` file at repo root** | "ai-eng is distilled from / built on Qwen2.5-3B-Instruct (© Alibaba Cloud), licensed under <SPDX id confirmed at build>. Upstream: https://huggingface.co/Qwen/Qwen2.5-3B-Instruct". **[REVISED v2]** ALSO state that the self-hosted HF model card and the GitHub release notes MUST carry this same attribution — the redistributed GGUF derivative carries the base license obligations with it. `package_ai_eng.sh` emits this NOTICE next to the artifact. |
| `LICENSE` (existing MIT) | Add a one-line pointer: "Bundled/derived/redistributed model weights carry their own licenses; see NOTICE." |

### Files that KEEP a minimal internal reference (class c)

| Location | Reference | Why unavoidable |
|---|---|---|
| `models/ai-eng/Modelfile.preview:1` | `FROM qwen2.5:7b` | A Modelfile must name its base. The single permitted qwen reference per WC#3. |
| `pyproject.toml ai_eng_preview` key value | `qwen2.5:7b` | Operator-facing config / the base the preview net pulls. |
| `scripts/build_ai_eng.py`, `build_ai_eng.sh`, `bench_ai_eng.py`, bench artifacts | Qwen2.5-3B base refs | Internal build/bench recipe. Out of scope. |
| `catalog/models.toml`, standalone catalog qwen rows | Qwen family listings | Honest standalone listings. Out of scope. |

---

## Honest framing rewrite (resolves Gate B / tension #2) *(unchanged from Rev 1)*

- **README.md:64 maximus "Good for" cell** → `The full bench. The heaviest model that runs *well* on your machine — with cloud frontier models one click away in the Chat Compute Source.`
- **README.md:64 maximus "What you get" cell** → `**AeroLLM** deep-mode runtime (the heaviest local model that runs well) · Anthropic SDK · LangChain · full cloud SDKs`.
- **CLAUDE.md:54** → `+ Admin · Docs · Notebooks · **AeroLLM** deep-mode runtime · Anthropic SDK · LangChain · full cloud SDKs — the full local bench, cloud frontier one click away`.
- **pyproject.toml `[tool.arail.tiers].maximus.description`** → "…full cloud catalog. Adds AeroLLM deep mode — the heaviest model that runs well locally; cloud frontier models are one click away via Compute Source."
- **tuning.html:111** → `Run the heaviest models your silicon handles well — layer-streamed off NVMe, tuned for the hardware you own. Frontier-scale models are one click away in the cloud.`

> Out of scope (do NOT touch): `builtin_seed.py` "frontier-scale" auto-goal text and `model_specs.py:409` — these describe AeroLLM's throughput target, not maximus marketing.

---

## Per-file edit list (builder: no further decisions needed) **[REVISED v2 — items 2, 3, 7, 8, 9, 13, 14 changed/added]**

1. **`pyproject.toml`**
   - `[tool.arail.models]`: `airllm_minimalist`, `airllm_maximus`, `airllm` → `__TODO_DEEP_MODEL__` each, with the canonical TODO comment block. Keep keys.
   - **[REVISED v2]** Add self-hosted keys: `ai_eng_hf_repo = "qukaizen/ai-eng-3b-gguf"  # __PLACEHOLDER__ — set your HF org/repo`, `ai_eng_quant = "Q4_K_M"  # placeholder`, `ai_eng_gh_url = "https://github.com/qukaizen/arail/releases/download/ai-eng-3b/ai-eng-3b-Q4_K_M.gguf"  # __PLACEHOLDER__`, `ai_eng_cdn_url = ""  # optional qukaizen.com mirror`, `ai_eng_sha256 = "__PLACEHOLDER_SHA256__"  # set from package_ai_eng.sh output`. Keep `ai_eng_preview = "qwen2.5:7b"`. Rewrite the `:126-128` comment (Part 3).
   - `[tool.arail.tiers].maximus.description`: honest-framing rewrite.
   - Leave `aerollm_*`, `coder_*`, `airllm` extra, `package-sources` untouched.

2. **`scripts/setup.sh`** **[REVISED v2]**
   - `:69-71` `AIRLLM_MODEL_ID/_MIN_ID/_MAX_ID` → `__TODO_DEEP_MODEL__` + TODO comment.
   - `:986-989` tier-resolution `case`: replace `Llama-3.1-405B/-70B` literals with `__TODO_DEEP_MODEL__`.
   - `:730-808 install_models()`: rewrite per Part 2 + Distribution channel §. Implement the self-hosted fetch ladder (HF pull → GitHub mirror w/ sha256 verify → optional CDN → preview net), reading hosts/quant/digest from config/env. Mirror paths fail-closed on placeholder/mismatched digest. Neutral wording in `info` lines. Preserve idempotency, the `ai-engineer` alias, `ARAIL_SKIP_OLLAMA`, the offline-skip branch, and the `timeout` guards. Update the `:742-743` manual-recovery `warn` to the new single self-hosted command + the preview fallback command.

3. **`scripts/check_ai_eng_artifact.sh`** (NEW, replaces Rev 1's `check_ai_eng_tag.sh`) — **[REVISED v2]** probe the self-hosted artifact: `curl -fsSL -m 8 -o /dev/null "https://huggingface.co/${repo}/resolve/main/<file>.gguf"` (or HF API manifest) → exit 0 if the GGUF is live; fall through to the GitHub release URL. Used by the 2b follow-up gate and a QA test documenting the deferral of preview-net removal.

4. **`scripts/package_ai_eng.sh`** (NEW developer-side scaffold) — **[REVISED v2]** documents/automates: (a) merge LoRA into qwen2.5:3b base (e.g. via `scripts/build_ai_eng.py` / peft merge — reference existing recipe, don't duplicate), (b) convert to GGUF at `--quant Q4_K_M` (llama.cpp `convert` + `quantize`), (c) emit a `Modelfile` + `NOTICE` next to the GGUF, (d) print `sha256sum` of the GGUF, (e) print exact upload commands as `# TODO(manual):` blocks: `huggingface-cli upload qukaizen/ai-eng-3b-gguf ...`, `gh release create ai-eng-3b ...`, optional CDN push. MUST NOT embed credentials, MUST NOT fabricate or download weights; if base/LoRA paths are missing it prints the manual steps and exits nonzero.

5. **`src/arail/router/backends.py:987-990`** — `AIRLLM_MODEL` default → `__TODO_DEEP_MODEL__`; sentinel-guard. Update `:992` comment. *(unchanged from Rev 1)*

6. **`src/arail/router/airllm_worker.py:54`** — same default swap + guard (OOM-safety backstop). *(unchanged)*

7. **`src/arail/portal/app.py`** — `:5996` `DEEP_BACKENDS["airllm"].default_model` → sentinel. `:6229,:6297,:6566-6572,:6596,:6665,:9207` Llama-3.1-70B literals → sentinel + drop "70B default… 405B" descriptions → "deep model is operator-configured (see NOTICE/docs)". HF-download hint strings (`:6566-6572`) become "set your deep model first" guidance. KEEP `_resilient_chat_default` qwen2.5:7b fallback (`:6030-6031`) — runtime safety net matching the still-present preview net; not marketing. *(unchanged from Rev 1)*

8. **`src/arail/chat/models_catalog.yaml`** — ai-eng entry (`:22-39`): strip qwen fallback sentence; **[REVISED v2]** set `install: ollama pull hf.co/qukaizen/ai-eng-3b-gguf:Q4_K_M` (placeholder repo); fix `description` per Part 3. Add ONE new browse row for the 20–30B deep placeholder (`tier: flagship`, `install: ""`, description → docs/NOTICE; no real model). Leave other rows.

9. **`models/ai-eng/Modelfile.preview`** — keep `FROM qwen2.5:7b`; reduce SYSTEM to neutral persona. **[REVISED v2]** `Modelfile.production` — leave as internal recipe (the authoritative Modelfile is emitted by `package_ai_eng.sh`); no qwen narrative to strip.

10. **`NOTICE`** (NEW, repo root) — Qwen2.5-3B attribution + confirmed SPDX id + upstream URL **+ [REVISED v2] the requirement that the HF model card and GitHub release carry the same attribution.** Builder confirms the exact license before writing.

11. **`LICENSE`** — append one line pointing to NOTICE for bundled/derived/**redistributed** model licenses.

12. **`README.md:64`, `CLAUDE.md:54,62`, `src/arail/portal/templates/tuning.html:111`** — honest-framing rewrites; soften qwen-fallback prose.

13. **`CHANGELOG.md`** — **[REVISED v2]** add an Unreleased entry: deep slot → sentinel; AirLLM 70B/405B defaults deprecated; **ai-eng now self-hosted (HuggingFace primary via `ollama pull hf.co/...`, GitHub Release mirror, digest-verified)**; qwen lineage moved to NOTICE; maximus copy rewrite. Do NOT rewrite 1.0.0 history.

14. **`docs/INSTALL.md:256`** — **[REVISED v2]** rewrite to document the self-hosted pull order (HF → GitHub mirror → preview fallback) and the digest verification, rather than the old qwen-probe narrative.

> Explicitly OUT OF SCOPE (do not edit): `catalog/models.toml`, `docs/CERTIFIED_MODELS.md`, `docs/maximus.plan.md`, `docs/build-and-finetune-plan.md`, `docs/plans/*`, `docs/chat-studio.spec.md`, `docs/DEBUG_QWEN25_7B_CASE_STUDY.md`, `research/**`, `scripts/build_ai_eng.*` (referenced by package_ai_eng.sh, not modified), `scripts/bench_ai_eng.py`, `models/ai-eng/BENCH*`, `model_specs.py`, `builtin_seed.py`, `pkb_seed.py`, `costs.py`, all `tests/**` except those the edits above necessarily break. `docs/RELEASE_v1.0.0.md` and `docs/SMOKE_TEST_v1.0.0.md` are frozen.

---

## Failure modes **[REVISED v2 — host-unreachable, wrong-quant, partial-download/checksum rows added]**

| Failure | Detection | Recovery |
|---|---|---|
| Self-hosted GGUF not uploaded yet (HF + GitHub both 404) | `ollama pull hf.co/...` non-zero; `curl -fL` 404 on mirror | Fall through the ladder to the preview net (qwen2.5:7b + Modelfile.preview). Setup never aborts. **This is the shipped path until the GGUF is uploaded.** |
| **Host unreachable / HF or GitHub down (not 404 — timeout/5xx/DNS)** | `ollama pull` / `curl` timeout or non-2xx (existing `timeout`/`-m`) | Try next mirror in order; if all hosts unreachable → preview net; if that also fails (offline) → `warn` + continue, print manual command. No crash. **[REVISED v2]** |
| **Partial / corrupted download (mirror paths)** | `sha256sum` of downloaded `.gguf` ≠ pinned `ai_eng_sha256` | Discard the file, `warn`, skip to next fallback. NEVER `ollama create` from an unverified blob (supply-chain). **[REVISED v2]** |
| **Pinned digest still a placeholder (`__PLACEHOLDER_SHA256__`)** | digest equals the placeholder sentinel | Mirror paths fail-closed (skip without downloading-and-trusting). HF native path (ollama-verified) and preview net remain. Setup still completes. **[REVISED v2]** |
| **Wrong/unavailable quant tag (`:Q4_K_M` not in the HF repo)** | `ollama pull hf.co/repo:<quant>` 404/manifest error | Treated as host-miss → next mirror → preview net. QA asserts the quant default is the documented placeholder, not silently a real-but-wrong tag. **[REVISED v2]** |
| Installed Ollama too old for `hf.co/...` native pull | HF pull errors with unsupported-reference | GitHub mirror (raw download + local create) covers it; NOTE records the min Ollama version. **[REVISED v2]** |
| Network down / airgapped clone during setup | `ollama pull` / `curl` fails or times out | `warn` + continue; explicit "offline — skipping ai-eng pull" branch so the log is honest. No crash, no partial state. |
| Sentinel `__TODO_DEEP_MODEL__` reaches a backend loader | guard checks `model_name == sentinel` before any load | Clear "deep model not configured" notice; NO download, NO 70B fallback. |
| Operator on 36 GB box clicks deep mode with no model set | sentinel guard | Friendly notice in chat + Admin: "Pick a deep model — see docs." Zero bytes downloaded. |
| Builder accidentally resolves the sentinel/placeholders to real values | QA asserts sentinel present in deep defaults; asserts `ai_eng_sha256`/repo are placeholder-marked OR (if real) accompanied by a real digest | CI/QA BLOCK. |
| Qwen base attribution missing (license risk) | QA asserts `NOTICE` exists, names Qwen2.5-3B + a license id, has upstream URL, **and states the HF-card/GitHub-release attribution requirement**; grep asserts no qwen lineage string in README/CLAUDE/catalog ai-eng description | BLOCK until present. **[REVISED v2]** |
| `package_ai_eng.sh` fabricates or downloads arbitrary weights | review + QA reads the script: no weight URLs, no credential literals, missing-input → exit nonzero | BLOCK. **[REVISED v2]** |
| Modelfile.preview deleted prematurely (would brick the preview net) | QA asserts `models/ai-eng/Modelfile.preview` exists with a `FROM` line | BLOCK (must NOT delete this sprint). |
| Maximus copy still says "frontier-scale" | grep for "frontier-scale"/"Frontier-scale" in README:64, CLAUDE:54, tuning.html:111, pyproject maximus desc | BLOCK. |
| OOM during testing (MEMORY warning) | n/a | Config/copy/shell sprint — QA must NOT spawn concurrent uvicorn + LLM loads. No real weight loads in CI; setup test runs with Ollama mocked / `ARAIL_SKIP_OLLAMA=1`. No real GGUF download in CI (mock curl/ollama). |

Every row maps to a test below.

---

## Test strategy **[REVISED v2 — setup + security rows extended for the self-hosted path]**

QA allocation per arail gating: **30% setup / 30% Buddy / 20% security / 10% happy / 10% regression.**

- **Setup (30%) — headline:**
  - `install_models()` with **HF-pull-success mock**: asserts a single `ollama pull hf.co/<repo>:<quant>`, NO local create, NO mirror download, NO preview pull, exit 0. **[REVISED v2 — this is the new WC#1 path]**
  - **HF-404 → GitHub-mirror-success mock (with valid pinned digest):** asserts curl download, sha256 verified, `ollama create` from local gguf, exit 0. **[REVISED v2]**
  - **mirror digest-mismatch mock:** asserts the file is discarded, no `create`, falls through, exit 0. **[REVISED v2]**
  - **placeholder-digest fail-closed mock:** mirror path skipped without trusting download; preview net reached; exit 0. **[REVISED v2]**
  - **all-hosts-404 mock (artifact not uploaded — current reality):** preview net path runs (qwen2.5:7b + Modelfile.preview), neutral wording (no "qwen2.5:7b" in `info` narrative), exit 0.
  - **offline mock:** all pulls/curls fail → `warn` + continue, exit 0, manual command printed.
  - idempotency: ai-eng present → skip; legacy `ai-engineer:latest` → `ollama cp` alias intact.
  - `scripts/check_ai_eng_artifact.sh` returns nonzero today (documents the 2b deferral; flips when uploaded). **[REVISED v2]**
  - sentinel-not-resolvable across all deep defaults (pyproject, setup.sh, backends.py, airllm_worker.py, app.py).
  - `package_ai_eng.sh` with missing inputs → prints manual steps, exits nonzero, performs no download. **[REVISED v2]**

- **Buddy (30%):** ai-eng persona unchanged behaviorally — Modelfile.production/preview SYSTEM still yields the "ai-eng" identity; assert the preview SYSTEM no longer contains qwen self-description but still defines the persona. No live model load (assert on Modelfile text + catalog/default resolution, per OOM-safety).

- **Security (20%):**
  - NOTICE exists, names Qwen2.5-3B + a license id + upstream URL **+ the HF-card/GitHub-release attribution requirement.** **[REVISED v2]**
  - No qwen lineage string in user-facing ai-eng surfaces (README ai-eng cells, CLAUDE ai-eng prose, catalog ai-eng `description`).
  - The lone permitted qwen ref (`Modelfile.preview` FROM) present and ONLY one outside config/NOTICE.
  - **Supply-chain: mirror paths refuse to `ollama create` from an unverified/placeholder-digest download (fail-closed); assert the sha256 check exists and gates the create.** **[REVISED v2]**
  - **`package_ai_eng.sh` contains no credential literals and no hardcoded weight-download URLs; upload steps are manual TODO.** **[REVISED v2]**
  - Sentinel guard prevents any download path (OOM/SSD-safety).
  - `LAB_MODE=airgapped` regression: cloud gating untouched; the self-hosted model-fetch is not a cloud-provider egress.

- **Happy (10%):** clean-machine sim (Ollama present) → HF pull success → `ai-eng:latest` resolvable → `_resilient_chat_default("ai-eng:latest")` returns it. Maximus tier renders honest copy.

- **Regression (10%):**
  - grep gate: no "frontier-scale"/"Frontier-scale" in the four rewritten surfaces.
  - existing 70B-as-threshold-fixture tests (`test_must_stream_rule`, `test_dispatch_35b_enforcement`, `test_frontier_threshold`) still pass (they assert the streaming-threshold regex, not the default).
  - `Modelfile.preview` still present with FROM line.

**No performance tests this sprint.** **No live LLM loads or real GGUF downloads in CI** (OOM-safety; mock `ollama`/`curl`).

---

## Tech debt **[REVISED v2]**

**Added:**
- `__TODO_DEEP_MODEL__` sentinel is live — maximus deep mode is non-functional until an operator sets a model. *Mitigated:* friendly notice, documented, follow-up ticket. Intentional honesty.
- **Self-hosted artifact placeholders** (`ai_eng_hf_repo`, `ai_eng_gh_url`, `ai_eng_quant`, `ai_eng_sha256`) ship as `__PLACEHOLDER__` values — the self-hosted pull paths are inert until the user runs `package_ai_eng.sh` and uploads. *Mitigated:* fail-closed digest check, preview net keeps setup working, follow-up ticket. **[REVISED v2]**
- The preview net survives this sprint. Follow-up ticket **2b: delete Modelfile.preview + preview net once `check_ai_eng_artifact.sh`==0.** **[REVISED v2]**
- Follow-up ticket: **package and upload the ai-eng GGUF (run package_ai_eng.sh, upload to HF + GitHub, pin the sha256 in pyproject + release notes).** **[REVISED v2]**
- Follow-up ticket: **pick the concrete 20–30B deep model; meet the ≤20 GB / ≤60 s-TTFT / no-OOM bar.**

**Repaid:**
- Removes the 70B/405B over-promise default.
- Removes the silent 7B-wearing-3B-label leak from user-facing copy.
- **Removes the dependency on the unavailable ollama.ai `qukaizen/` namespace — ARAIL now controls its own model distribution.** **[REVISED v2]**
- Centralizes qwen attribution in NOTICE + mandates it on the redistributed artifact (compliance debt repaid).
- Adds digest verification to model fetch (supply-chain debt repaid — relevant since ARAIL runs on others' machines). **[REVISED v2]**
- Replaces a 4-command catalog `install` string with a clean single self-hosted pull.

**Net:** roughly neutral, leaning negative (good). Added debts are deferred-by-gate with home tickets and automatic triggers, not silent rot.

---

## Recommended implementation order **[REVISED v2]**

1. **NOTICE + LICENSE pointer** (unblocks the license gate; do first so the honesty change is compliant before any qwen strip). Include the redistributed-artifact attribution clause.
2. **Sentinel rollout** — pyproject deep keys, setup.sh:69-71/986-989, backends.py, airllm_worker.py, app.py defaults + guards.
3. **pyproject self-hosted keys** (`ai_eng_hf_repo`/`quant`/`gh_url`/`cdn_url`/`sha256`/`preview`) with placeholder markers.
4. **`setup.sh install_models()` rewrite** (self-hosted fetch ladder + digest verify + preview net) and **`scripts/check_ai_eng_artifact.sh`**.
5. **`scripts/package_ai_eng.sh`** scaffold (merge→GGUF→Modelfile→NOTICE→sha256→manual upload TODOs).
6. **Modelfile.preview SYSTEM trim; catalog ai-eng entry (self-hosted install) + new deep placeholder row.**
7. **Copy rewrites** — README, CLAUDE.md, tuning.html, pyproject tier desc, docs/INSTALL.md (self-hosted pull narrative), CHANGELOG Unreleased.
8. **Tests** per strategy; run full suite; confirm threshold-fixture tests unaffected. Mock `ollama`/`curl`; no real downloads.
