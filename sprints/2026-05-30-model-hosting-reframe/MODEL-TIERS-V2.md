# Architecture: Model-Strategy Reframe v2 — Two-Tier Persona-Wrap

**Date:** 2026-05-31
**Spec:** parent-session decision (model strategy moves to an explicit two-tier persona-wrap setup)
**Supersedes (in part):** [ARCHITECTURE.md](./ARCHITECTURE.md) + [CONSOLIDATION.md](./CONSOLIDATION.md) for the **default-model** and **deep-model** selection. Does NOT supersede the self-hosted GGUF ladder *machinery* — that machinery becomes the dormant future-distill lane (see §7).
**Mode:** architect / design

---

## Restatement

The model strategy moves from "one self-hosted-GGUF default (Qwen2.5-1.5B + LoRA) plus an unresolved `__TODO_DEEP_MODEL__` sentinel for deep mode" to an explicit, shippable-today **two-tier persona-wrap** map. Both tiers ship an "AI engineer" persona by default, and both personas are produced the same cheap way: a base model plus an Ollama `Modelfile` `SYSTEM` prompt — **no fine-tune, no distill, no custom artifact hosting required to ship.** The everyday default (minimalist) becomes **Llama-3.2-1B-Instruct + AI-engineer persona** (~0.9 GB at Q4, must run on a 16 GB floor), installed by `ollama pull llama3.2:1b` then `ollama create <name> -f <Modelfile>`. The maximus deep model becomes **Qwen2.5-7B-Instruct + AI-engineer persona**, which already exists and is verified live as `ai-engineer:latest` (qwen2 arch, 7.6B, Q4_K_M, 4.7 GB, Apache-2.0, persona via System prompt) — this **resolves the `__TODO_DEEP_MODEL__` sentinel** for maximus. The landmine: the new default base is Llama-3.2-1B-Instruct under the **Llama 3.2 Community License**, which imposes obligations Apache-2.0 did not — the distributed model name must **begin with "Llama"**, "**Built with Llama**" must be displayed, and the license + Acceptable Use Policy must travel with the artifact. This **reverses the prior "hide the base lineage" rule for the 1B default only**; the Qwen2.5-7B deep model stays Apache-2.0 and keeps its existing attribution posture. The self-hosted GGUF ladder (HF/GitHub/CDN fetch, `build_ai_eng.*`, `check_ai_eng_artifact.sh`, the `ai_eng_*` pyproject keys) is **not deleted** — it goes dormant as the future upgrade path for a real Nucleus distill.

---

## 1. Assumptions and the two-tier model map

### Assumptions (state explicitly; builder must honor)

1. **Persona-wrap, not fine-tune.** Both default personas = base model + Ollama `Modelfile` `SYSTEM` prompt. This is the same technique as today's live `ai-engineer:latest`. No weights are merged, distilled, quantized, or hosted by this sprint. This is THE shippable-today path and the explicit precedence resolver (§2).
2. **16 GB RAM floor for minimalist.** Llama-3.2-1B at Q4 (~0.9 GB weights, ~1.5–2 GB resident with KV cache at 8K ctx) leaves ample headroom on a 16 GB machine alongside the portal + browser. The deep 7B (~4.7 GB resident) is a maximus-only, not-on-the-16GB-floor concern.
3. **`ai-engineer:latest` is the existing maximus deep persona, verified.** `ollama show ai-engineer:latest` on 2026-05-31 returned: architecture `qwen2`, parameters `7.6B`, quantization `Q4_K_M`, size 4.7 GB, license Apache-2.0, persona delivered via the Modelfile `SYSTEM` prompt. We adopt it as-is; we do not re-pull or re-create it where it already exists.
4. **Ollama is the runtime for both personas.** On Apple Silicon, setup skips Ollama by default (MLX primary) unless `ARAIL_ENABLE_OLLAMA=1` (existing guard, `setup.sh:733`). The persona installs only run when Ollama is present. This sprint does not change that guard. (Implication: the AeroLLM/MLX deep path and the Ollama deep persona are two distinct surfaces — see §3.)
5. **`LAB_MODE=airgapped` is invariant.** No cloud-egress gating changes. `ollama pull llama3.2:1b` and `ollama pull qwen2.5:7b` are model-fetches (same class as the existing pull), gated by the existing Ollama-present guard — NOT cloud-provider calls. An airgapped clone with no network hits the graceful offline branch.
6. **The reference hardware is 36 GB Apple Silicon; the floor is 16 GB.** The 1B default is sized to the floor; the 7B deep to the reference box.
7. **The Llama 3.2 Community License obligations as verified (see §4) are accurate.** The builder MUST confirm the canonical license text once more against the bundled copy before committing (cheap insurance; a license violation is not).
8. **AirLLM stays opt-in and untouched** (`ARAIL_INSTALL_AIRLLM=1`). Only the *default model id* it resolves to is affected (it remains the sentinel for the layer-streaming lane — see §3).
9. **`llama3.2:1b` exists on the Ollama public library.** Confirmed convention: `ollama pull llama3.2:1b` resolves the Meta Llama-3.2-1B-Instruct Q4_K_M tag from the Ollama library. Builder confirms the exact tag/size before committing the catalog `install` string.

### Two-tier model map

| Tier | Default model (auto-install) | Base | Size (Q4) | License | Persona delivery | Install mechanism |
|---|---|---|---|---|---|---|
| **minimalist** (everyday default; the ONLY auto-install) | **Llama-ai-eng** (AI engineer) | Llama-3.2-1B-Instruct | ~0.9 GB | **Llama 3.2 Community License** | Modelfile `SYSTEM` prompt | `ollama pull llama3.2:1b` → `ollama create llama-ai-eng -f models/ai-eng/Modelfile.default` |
| **maximus** (deep model; offered, not silent-auto on first boot — see §3 trigger) | **ai-engineer** (AI engineer, 7B) | Qwen2.5-7B-Instruct (existing `ai-engineer:latest`) | 4.7 GB | Apache-2.0 | Modelfile `SYSTEM` prompt (already applied) | reuse existing `ai-engineer:latest` if present; else `ollama pull qwen2.5:7b` → `ollama create ai-engineer -f models/ai-eng/Modelfile.deep` |

> **The 1B is the only model installed on a clean minimalist setup.** The 7B deep persona is a maximus-tier model. The exact maximus install trigger (setup-time on `maximus` tier vs. pull-on-demand) is resolved in §3.

---

## 2. Default path design (minimalist: Llama-3.2-1B + persona)

### The Modelfile (new: `models/ai-eng/Modelfile.default`)

```
FROM llama3.2:1b

SYSTEM """You are an AI engineering assistant — a careful, production-minded
software and ML engineer. You reason step by step, write clean idiomatic code,
explain tradeoffs plainly, and say so when you do not know something.

Built with Llama."""

PARAMETER temperature 0.7
PARAMETER num_ctx 8192
```

- `FROM llama3.2:1b` — the Meta Llama-3.2-1B-Instruct Q4_K_M tag from the Ollama library.
- The `SYSTEM` prompt carries the persona AND the "Built with Llama" string (one of the three required disclosures — see §4; the system prompt is a convenient always-present surface but is NOT the sole compliance location — README/catalog/NOTICE also carry it).
- `num_ctx 8192` matches the existing preview/deep Modelfiles; safe on the 16 GB floor for a 1B.

### The Ollama model/tag name (Llama-naming compliance)

The Llama 3.2 license requires distributed model names to **begin with "Llama"**. Resolution:

- **Ollama local model name = `llama-ai-eng`** (begins with "Llama" — compliant). This is what `ollama create` produces and what the chat default resolves to.
- The **internal/display "ai-eng" identity is retained as a sub-string** ("Llama-ai-eng" / "Llama AI Engineer" in display copy) so the product's "AI engineer" branding survives while the name leads with "Llama".
- **Back-compat:** the existing chat default and resilient resolver look for `ai-eng:latest` / `ai-engineer:latest`. We do NOT rename those lookups out from under existing installs. Instead: `ollama create llama-ai-eng` becomes the new default-create name, and the chat default candidate list is **`["llama-ai-eng", "ai-eng:latest", "ai-engineer:latest"]`** (first present wins). New installs get `llama-ai-eng`; existing installs keep working. (`_resilient_chat_default`, `app.py:6004`, extends its candidate set; no breaking rename.)

> **Naming rationale, recorded:** the Meta clause is "include 'Llama' at the **beginning** of any such model name." `llama-ai-eng` satisfies "beginning with Llama" literally. We do not need to call it `Llama-3.2-1B`; a derivative name that *starts* with "Llama" is compliant.

### Precedence — simple-pull vs. the self-hosted ladder (THE decision)

**Resolved precedence: the simple persona-wrap pull is the PRIMARY and ONLY default path this sprint. The self-hosted GGUF ladder is fully dormant — gated off, not racing.**

Concretely, in `install_models()`:

1. The default install becomes a **two-step persona-wrap**: `ollama pull llama3.2:1b` → `ollama create llama-ai-eng -f models/ai-eng/Modelfile.default`. This replaces the self-hosted fetch ladder (the HF-pull-primary → GitHub-mirror → CDN → preview-net cascade) **as the default code path**.
2. The self-hosted ladder is **not invoked by default.** It is moved behind an explicit opt-in flag: `ARAIL_AI_ENG_SELFHOSTED=1` (off by default). When set, it runs the existing ladder (HF/GitHub/CDN/preview) — this is the future-distill lane for when a real Nucleus GGUF is uploaded. **There is exactly one "primary" path: the simple pull.** No two competing primaries.
3. The old preview-net (`Modelfile.preview` + `qwen2.5:1.5b` fallback) is **retired from the default path** — it existed only because the self-hosted artifact wasn't uploaded. With the persona-wrap default, there is no missing artifact to fall back from; the base (`llama3.2:1b`) is a public Ollama tag that the simple pull fetches directly. `Modelfile.preview` is KEPT on disk (dormant, used only by the opt-in self-hosted lane's last-resort net) — do not delete it this sprint (see failure modes: premature-delete guard).

> **Why this precedence and not "ladder primary, simple fallback":** the simple pull has zero external dependencies (no uploaded artifact, no pinned digest, no placeholder repo), works today, and is the user's stated shippable-today path. The ladder's entire reason for being primary in v1 was the now-abandoned bet on a self-hosted distill existing at ship. That bet is deferred, so the ladder is demoted to opt-in. One primary, cleanly.

---

## 3. Deep-model resolution (maximus: Qwen2.5-7B persona)

The `__TODO_DEEP_MODEL__` sentinel exists in TWO distinct deep surfaces. They must be treated differently:

### Surface A — the Ollama "AI engineer 7B" deep persona (the NEW resolution)

This is the existing `ai-engineer:latest` (Qwen2.5-7B + persona). It resolves the *user-facing* "deep AI engineer" offering on maximus.

- **Install (maximus only):** if `ai-engineer:latest` already exists in Ollama → adopt it (no re-pull; this matches the live verified model). Else, on a `maximus` setup with Ollama present: `ollama pull qwen2.5:7b` → `ollama create ai-engineer -f models/ai-eng/Modelfile.deep`.
- **Install trigger:** **offered, not forced on the 16 GB floor.** Because the 7B is 4.7 GB and the minimalist floor is 16 GB, the deep persona installs on `maximus` setup **only when `ARAIL_INSTALL_DEEP_PERSONA=1` OR the machine reports ≥ a RAM threshold** (builder: gate on the existing tier capture + a `psutil`/`sysctl` RAM check; default to *offering a one-line command*, not a silent 4.7 GB pull, to honor the OOM-sensitivity memory note). The clean default is: print the exact `ollama pull qwen2.5:7b && ollama create ai-engineer …` command on maximus setup; auto-run only behind the explicit flag. This avoids a surprise multi-GB pull on a constrained maximus box.
- **Catalog:** the `models_catalog.yaml` deep row (currently `__TODO_DEEP_MODEL__`) is **replaced** with a concrete `ai-engineer` row: `name: AI Engineer (deep, 7B)`, `family: qukaizen`, `size_gb: 4.7`, `install: "ollama pull qwen2.5:7b  # then: ollama create ai-engineer -f models/ai-eng/Modelfile.deep"`, `tier: flagship`. Apache-2.0 (Qwen) — keep the existing attribution posture; the qwen lineage stays in NOTICE/config, not marketing copy (the 7B is NOT under Llama-naming rules).

### Surface B — the AirLLM/AeroLLM layer-streaming / frontier deep backend (sentinel STAYS)

This is the `backends.py:990` / `airllm_worker.py:57` / `app.py` `AIRLLM_MODEL` default and the `airllm_*` pyproject keys. This is the **layer-streamed frontier lane** (20–30B+), a different surface from the Ollama 7B persona.

- **Keep the `__TODO_DEEP_MODEL__` sentinel here.** A 20–30B+ frontier model is still operator-configured and still must not auto-load on a 16/36 GB box. The sentinel guard (notice, no download, no OOM) stays exactly as-is. OOM-safety and airgapped rules preserved. AirLLM opt-in untouched.
- **AeroLLM backend** (`backends.py:1473,1513`): default already `Qwen2.5-7B-Instruct-4bit` (MLX). Leave as-is — it is the MLX deep runtime and is already the 7B floor the user wants. No change required; it is consistent with the maximus-7B decision.

> **The reframe resolves the sentinel for the *user-facing deep persona* (Surface A, via the Ollama Qwen2.5-7B `ai-engineer`), and leaves the sentinel intact for the *frontier layer-streaming lane* (Surface B, AirLLM).** These are not the same deep model; conflating them would re-introduce the 70B OOM footgun. Builder: do NOT point `AIRLLM_MODEL` at the 7B.

---

## 4. Llama-license compliance plan

### What I verified against the canonical Llama 3.2 Community License text

The Llama 3.2 Community License (Meta) §1.b imposes, for anyone who distributes/makes available the Llama Materials OR a derivative OR a product using them:

1. **Provide a copy of the agreement** (the Llama 3.2 Community License Agreement text) with the distribution.
2. **Display "Built with Llama"** on a related website, user interface, blog post, about page, or product documentation.
3. **Model-naming:** if you use the Llama Materials to **create, train, fine-tune, or otherwise improve an AI model that you distribute or make available, you must include "Llama" at the beginning of any such model name.**
4. **Attribution notice:** retain the notice: *"Llama 3.2 is licensed under the Llama 3.2 Community License, Copyright © Meta Platforms, Inc. All Rights Reserved."* in a "Notice" text file distributed with the materials.
5. **Comply with the Llama 3.2 Acceptable Use Policy** (and include/reference it).
6. **700M MAU clause** — a commercial-scale license trigger; not applicable to ARAIL forks at typical scale, but note it in NOTICE so forkers are aware.

The builder MUST re-confirm items 1–5 against the bundled canonical text before committing (I confirmed the substance of these obligations; the exact required notice string in item 4 is load-bearing and must be copied verbatim).

> **Persona-wrap is a derivative for license purposes.** A Modelfile `SYSTEM`-prompt wrap over `llama3.2:1b` that we name and ship as a distinct model (`llama-ai-eng`) is "an AI model … you distribute or make available" → the naming + Built-with-Llama + AUP + agreement-copy obligations all apply. We do NOT escape them by virtue of not fine-tuning.

### NOTICE rewrite (covers BOTH bases)

Rewrite `NOTICE` to a two-section structure:

- **Section 1 — Default model (minimalist): Llama-3.2-1B-Instruct.**
  - Base: `meta-llama/Llama-3.2-1B-Instruct`, © Meta Platforms, Inc.
  - License: **Llama 3.2 Community License** (NOT Apache-2.0). Include the verbatim required notice string (item 4 above). Link the canonical license + the Llama 3.2 Acceptable Use Policy. Bundle a copy of the license text (e.g. `licenses/LLAMA-3.2-COMMUNITY-LICENSE.txt`) and the AUP, satisfying item 1 + 5.
  - State the naming compliance: the distributed model is named `llama-ai-eng` (begins with "Llama").
  - State that "Built with Llama" is displayed (README, chat persona system prompt, catalog).
  - Redistribution clause: any redistributed `llama-ai-eng` artifact (if a fork ever hosts one) must carry the license, AUP, "Built with Llama", and the Llama-prefixed name.
- **Section 2 — Maximus deep model: Qwen2.5-7B-Instruct.**
  - Base: `Qwen/Qwen2.5-7B-Instruct`, © Alibaba Cloud. License: Apache-2.0 (verified live: `ai-engineer:latest` reports Apache-2.0). Keep the existing Apache-2.0 attribution clauses (a–d) — these are already correct in today's NOTICE, just retargeted from 1.5B to 7B.
- **Section 3 — Dormant future-distill lane.** Note that the self-hosted GGUF lane (`build_ai_eng.*`) targets a future Nucleus distill; its base/license will be re-confirmed when that artifact exists.

### "Built with Llama" + display-name reconciliation

| Surface | Today | After |
|---|---|---|
| Ollama model name (created) | `ai-eng` / `ai-engineer` | `llama-ai-eng` (default 1B); `ai-engineer` (deep 7B — Apache, no Llama rule) |
| Chat default resolver candidates | `ai-eng:latest`, `ai-engineer:latest` | `llama-ai-eng`, `ai-eng:latest`, `ai-engineer:latest` (back-compat) |
| README / catalog / tier copy (1B) | "1.5B Opus-4.7-derived AI engineering expert" | "Llama AI Engineer — an AI engineering assistant **built with Llama** (Llama-3.2-1B-Instruct)" |
| Persona system prompt (1B) | persona only | persona + "Built with Llama" line |
| NOTICE | Qwen 1.5B Apache | Llama-3.2-1B Community License (default) + Qwen-7B Apache (deep) |

> **This REVERSES "hide the base" for the 1B default ONLY.** The Llama base must be **disclosed and attributed** (the opposite of the qwen-hiding rule that governed the 1.5B/3B design). The 7B deep model keeps the existing posture (Apache attribution lives in NOTICE/config, not marketing) — it is NOT under Llama-naming rules. Update `CLAUDE.md`'s "hide the base" convention to carve out this Llama exception explicitly.

---

## 5. Branding + per-file edit list

Branding rules: default = **"Llama AI Engineer" / "1B"** (was "1.5B"); deep = **"AI Engineer (deep, 7B)" / "7B"**; both are "AI engineer" personas by default.

| # | File | Change | Why |
|---|---|---|---|
| 1 | `NOTICE` | Rewrite to two-section structure (§4): Section 1 Llama-3.2-1B Community License (verbatim notice string, AUP reference, "Built with Llama", `llama-ai-eng` naming); Section 2 Qwen2.5-7B Apache-2.0; Section 3 dormant distill note. | License compliance for both bases; reverses hide-the-base for the 1B. |
| 2 | `licenses/LLAMA-3.2-COMMUNITY-LICENSE.txt` (new) + `licenses/LLAMA-3.2-ACCEPTABLE-USE-POLICY.txt` (new) | Bundle the canonical license + AUP text. | Items 1 + 5 of the Llama obligations require shipping a copy. |
| 3 | `LICENSE` | Extend the bundled/derived-weights pointer line to name BOTH the Llama 3.2 Community License and Apache-2.0; point at `NOTICE` and `licenses/`. | Forkers see the dual-license reality. |
| 4 | `models/ai-eng/Modelfile.default` (new) | `FROM llama3.2:1b` + AI-engineer `SYSTEM` (incl. "Built with Llama") + temp/num_ctx (§2). | The default persona-wrap. |
| 5 | `models/ai-eng/Modelfile.deep` (new) | `FROM qwen2.5:7b` + AI-engineer `SYSTEM` (the existing `ai-engineer:latest` persona text). | The maximus deep persona-wrap recipe (reproducible). |
| 6 | `models/ai-eng/Modelfile.preview` | KEEP on disk (dormant; used only by opt-in self-hosted lane). No edit required, but add a one-line comment noting it is the dormant self-hosted-lane fallback. | Premature-delete is a failure mode; ladder is dormant, not deleted. |
| 7 | `models/ai-eng/Modelfile.production` | KEEP (dormant; build_ai_eng publish recipe). No edit. | Future-distill lane. |
| 8 | `scripts/setup.sh` `install_models()` (~764–931) | Replace the default fetch-ladder body with the persona-wrap default: idempotency check (`llama-ai-eng` OR legacy `ai-eng`/`ai-engineer` present → skip); legacy `ai-engineer:latest`→adopt as deep (do NOT alias to the 1B default); `ollama pull llama3.2:1b` → `ollama create llama-ai-eng -f Modelfile.default`; offline/airgapped graceful skip with the exact manual command; gate the entire self-hosted ladder behind `ARAIL_AI_ENG_SELFHOSTED=1`. Add the maximus deep-persona OFFER (print command; auto-run only on `ARAIL_INSTALL_DEEP_PERSONA=1` + RAM check). Preserve `ARAIL_SKIP_OLLAMA`, the Apple-Silicon Ollama guard, timeouts. | The §2 precedence + §3 Surface A install. |
| 9 | `scripts/setup.sh:74-76, 1113-1114` | LEAVE `AIRLLM_MODEL_ID*` = `__TODO_DEEP_MODEL__`. | Surface B sentinel stays (frontier layer-streaming lane). |
| 10 | `pyproject.toml [tool.arail.models]` | Add `default_base = "llama3.2:1b"`, `default_model_name = "llama-ai-eng"`, `default_license = "Llama-3.2-Community-License"`. Add `deep_persona_base = "qwen2.5:7b"`, `deep_persona_name = "ai-engineer"`, `deep_persona_license = "Apache-2.0"`. KEEP `ai_eng_*` self-hosted keys (dormant lane) but add a comment: "DORMANT — future Nucleus-distill lane; gated behind ARAIL_AI_ENG_SELFHOSTED=1. The shipping default is `default_base` above." Update the `1.5B-parameter` prose in the `[tool.arail.models]` and `[tool.arail.tiers].minimalist` comments → "Llama AI Engineer (built with Llama-3.2-1B-Instruct)". Leave `aerollm_*` (7B) untouched. | Config-as-code source of truth; dormant ladder labeled. |
| 11 | `src/arail/chat/models_catalog.yaml` | Default row (`ai-eng:latest`): rename to `llama-ai-eng`, `name: Llama AI Engineer`, `family: llama`, `size_gb: 0.9`, description "AI engineering assistant — **built with Llama** (Llama-3.2-1B-Instruct)", `install: "ollama pull llama3.2:1b  # then: ollama create llama-ai-eng -f models/ai-eng/Modelfile.default"`. Replace the `__TODO_DEEP_MODEL__` row with the concrete deep 7B `ai-engineer` row (§3 Surface A). Update/keep the `qwen2.5:1.5b` preview row as a dormant-lane note OR remove from gallery (builder choice; keep if it appears in tests). Add a `llama3.2:1b` base browse row (family llama). | User-facing default + deep catalog; Llama attribution in copy. |
| 12 | `src/arail/portal/app.py` | Extend `_resilient_chat_default` candidate set to `["llama-ai-eng", "ai-eng:latest", "ai-engineer:latest"]`; update the `MODEL_NAME` default fallback (`:6482`) from `ai-eng:latest` to `llama-ai-eng` (keeping the resolver back-compat). LEAVE the Surface-B sentinel guards (`:5999, :6232-6240, :6608, :9219`) intact. | New default name resolves; existing installs still work; frontier sentinel untouched. |
| 13 | `src/arail/router/backends.py`, `airllm_worker.py` | NO change — Surface-B sentinel + AeroLLM-7B default stay. | Frontier lane + MLX 7B unchanged. |
| 14 | `README.md` | Tier table: minimalist model line → "Llama AI Engineer — an AI engineering assistant built with Llama (Llama-3.2-1B-Instruct, ~0.9 GB, runs on 16 GB)". Maximus: add the deep 7B `ai-engineer` (Qwen2.5-7B) line. Add a visible "Built with Llama" acknowledgment (satisfies obligation item 2). Replace any "1.5B" with "1B". | User-facing branding + Llama "Built with Llama" display. |
| 15 | `CLAUDE.md` | Update the tier table (1.5B→1B Llama AI Engineer; deep 7B). **Amend the "hide the base" convention** to add: "EXCEPTION: the default model is built on Llama-3.2-1B-Instruct under the Llama 3.2 Community License, which REQUIRES disclosure — the name begins with 'Llama' (`llama-ai-eng`), 'Built with Llama' is displayed, and NOTICE bundles the license + AUP. The hide-the-base rule applies only to the Apache-2.0 deep/qwen lineage." | Orientation doc must reflect the reversed rule, or a future session re-hides Llama and breaks the license. |
| 16 | `docs/INSTALL.md` | Rewrite the install narrative: default is `ollama pull llama3.2:1b` + `ollama create llama-ai-eng`; deep 7B is the maximus offer; the self-hosted ladder is the dormant `ARAIL_AI_ENG_SELFHOSTED=1` lane. "1.5B"→"1B". | Accurate setup docs. |
| 17 | `CHANGELOG.md` | New Unreleased entry: two-tier persona-wrap reframe; default → Llama-3.2-1B (`llama-ai-eng`, Built with Llama, Community License); deep → Qwen2.5-7B `ai-engineer` (resolves the user-facing deep sentinel); self-hosted GGUF ladder demoted to dormant opt-in lane; NOTICE dual-base rewrite. Do NOT rewrite shipped 1.0.0 history. | Honest history. |
| 18 | `scripts/build_ai_eng.py` / `build_ai_eng.sh` | Change the future-distill **base defaults** from Qwen2.5-1.5B to **Llama-3.2-1B-Instruct** (so the dormant lane, when revived, builds on the same base as the default). Update `DEFAULT_BF16_BASE`/`DEFAULT_MLX_BASE`/`DEFAULT_ADAPTER_REPO`/Modelfile-name/publish strings. KEEP the pipeline dormant (not invoked by default setup). Update the `--license` guidance to flag the Llama Community License for a Llama-based distill. | Dormant lane targets the right base; consistency. |
| 19 | `scripts/check_ai_eng_artifact.sh` | KEEP (dormant-lane probe). Update its `HF_REPO`/`GGUF_FILE` defaults only if the dormant lane's naming changes; otherwise no-op. | Dormant lane consistency. |
| 20 | `src/arail/portal/templates/tuning.html` | "1.5B"→"1B" / Llama AI Engineer where it names the default; keep the honest-framing deep copy. | Branding consistency. |

> **Out of scope (do NOT edit):** `research/**`, `catalog/models.toml` standalone rows, frozen `docs/RELEASE_v1.0.0.md` / `docs/SMOKE_TEST_v1.0.0.md` (except a one-line "superseded by MODEL-TIERS-V2" pointer if needed), the sprint's historical `ARCHITECTURE.md`/`BUILD_LOG.md`/`CONSOLIDATION.md` (append-only). The Surface-B AirLLM/AeroLLM frontier defaults.

---

## 6. Failure modes + test strategy

### Failure modes

| Failure | Detection | Recovery |
|---|---|---|
| `ollama pull llama3.2:1b` fails offline / airgapped | `ollama pull` non-zero / timeout (existing `_arail_timeout`) | `warn` + continue (no crash, no partial state); print exact manual command. Same graceful-skip branch as today. |
| `ollama create llama-ai-eng` fails after a successful pull | `ollama create` non-zero | `warn` + print the manual create command; setup continues (base is at least pulled). |
| OOM on the 16 GB floor | n/a at install (no model loaded by setup); at runtime the 1B is ~1.5–2 GB resident | The 1B is sized to the floor by design (assumption 2). Regression guard asserts the default base is the 16GB-safe 1B, not a heavier model. CI never loads a real model (OOM-safe). |
| Legacy `ai-engineer:latest` (7B) mistaken for the 1B default | setup adopts `ai-engineer:latest` as the DEEP persona, NOT as the 1B default | `install_models()` must NOT `ollama cp ai-engineer:latest → llama-ai-eng` (that would make the "1B default" secretly a 7B — the exact v1 footgun). The legacy 7B maps to the deep slot; the 1B default is always created from `Modelfile.default`. Guard test asserts no such alias. |
| Deep 7B not present on minimalist | chat deep request with no deep model | Friendly "deep model is a maximus offering — run `ollama pull qwen2.5:7b && ollama create ai-engineer …` or upgrade" notice; zero auto-download. |
| Surprise 4.7 GB pull on a constrained maximus box | deep persona auto-install gated | Default = OFFER the command; auto-run only on `ARAIL_INSTALL_DEEP_PERSONA=1` + RAM check (§3). No silent multi-GB pull. |
| Llama-name non-compliance (model name doesn't begin with "Llama") | grep guard: the created default model name + catalog `id`/`name` begin with "Llama"/"llama" | BLOCK. The created name is `llama-ai-eng`. |
| "Built with Llama" / license / AUP missing | guard: NOTICE contains the verbatim Llama notice string + AUP reference; README contains "Built with Llama"; `licenses/LLAMA-3.2-*` files exist | BLOCK until present. |
| Frontier sentinel (Surface B) accidentally resolved to the 7B | guard: `AIRLLM_MODEL` default + `airllm_*` keys still `__TODO_DEEP_MODEL__` | BLOCK (re-introduces OOM footgun otherwise). |
| Self-hosted ladder accidentally runs by default | guard: ladder is behind `ARAIL_AI_ENG_SELFHOSTED=1`; default path mock asserts only `llama3.2:1b` pull + `llama-ai-eng` create, no HF/curl | BLOCK. |
| `Modelfile.preview/production` deleted prematurely | guard: files still exist | BLOCK (dormant lane must survive). |

Every row maps to a test below.

### Test strategy (arail gating: 30% setup / 30% Buddy / 20% security / 10% happy / 10% regression). **All OOM-safe: mock `ollama`/`curl`, no real pulls, no model loads.**

- **Setup (30%):**
  - default-path mock: asserts exactly `ollama pull llama3.2:1b` then `ollama create llama-ai-eng -f .../Modelfile.default`; NO HF pull, NO curl, NO preview-net, exit 0.
  - idempotency: `llama-ai-eng` present → skip; legacy `ai-eng`/`ai-engineer` present → resolver still finds a default (no re-pull).
  - **legacy-7B-not-aliased-to-1B guard:** `ai-engineer:latest` present must NOT become `llama-ai-eng` (no `ollama cp` to the default name).
  - offline/airgapped mock: pull fails → `warn` + continue, exit 0, manual command printed.
  - maximus deep OFFER mock: prints the `qwen2.5:7b` + create command; auto-runs only with `ARAIL_INSTALL_DEEP_PERSONA=1`.
  - self-hosted ladder gated: without `ARAIL_AI_ENG_SELFHOSTED=1`, no HF/curl invoked.
  - **Update the existing setup-ladder tests** (`tests/setup_ladder/`) to the new default path; the old HF-primary/preview-net assertions move under the opt-in `ARAIL_AI_ENG_SELFHOSTED=1` gate.
- **Buddy (30%):** persona unchanged behaviorally — assert `Modelfile.default` `SYSTEM` defines the AI-engineer persona AND contains "Built with Llama"; assert `Modelfile.deep` defines the 7B persona. No live load (Modelfile text + catalog/default resolution only).
- **Security (20%):**
  - **Update the qwen-hiding guard test** (`tests/test_model_hosting_reframe_qa.py`): it must now (a) ALLOW Llama attribution in user-facing copy (the reverse of hiding), (b) REQUIRE the Llama notice string + AUP + "Built with Llama" + `llama-`-prefixed name, (c) keep the 7B/qwen lineage out of *marketing* copy (qwen stays in NOTICE/config — Apache, no naming rule). Update the NOTICE assertions: dual-base (Llama-3.2-1B Community License + Qwen2.5-7B Apache-2.0).
  - `licenses/LLAMA-3.2-COMMUNITY-LICENSE.txt` + AUP files exist and are non-empty.
  - Surface-B sentinel guard: `AIRLLM_MODEL` default + `airllm_*` keys still the sentinel.
  - `LAB_MODE=airgapped` regression: model-fetch is not a cloud-provider egress; gating untouched.
  - No credential literals introduced; build_ai_eng base-default change embeds no weights.
- **Happy (10%):** clean-machine sim (Ollama present) → `llama3.2:1b` pull + `llama-ai-eng` create → `_resilient_chat_default` resolves `llama-ai-eng`. Maximus renders the deep 7B offer.
- **Regression (10%):**
  - **Regression guard (required):** default base is the 16GB-safe `llama3.2:1b` (1B), NOT a heavier model; AND Llama attribution ("Built with Llama" + Community License notice) is present.
  - existing threshold-fixture tests (`test_must_stream_rule`, etc.) unaffected.
  - `Modelfile.preview/production` still present (dormant-lane survival).

No performance tests this sprint. No live LLM loads / real downloads in CI.

---

## 7. Tech debt + what becomes dormant

**Added:**
- The self-hosted GGUF ladder (`build_ai_eng.*`, `check_ai_eng_artifact.sh`, `ai_eng_*` keys, `Modelfile.preview/production`, the HF/GitHub/CDN fetch logic) is now **dead-by-default code behind `ARAIL_AI_ENG_SELFHOSTED=1`.** *Mitigated:* clearly labeled "DORMANT — future Nucleus-distill lane" in pyproject + setup comments; re-based to the Llama-3.2-1B base so it stays consistent; one follow-up ticket. Not silent rot — it has a documented home and an opt-in switch.
- The maximus deep persona install is an OFFER-by-default (manual command unless flagged). Minor friction; mitigated by the printed one-liner and the OOM-safety rationale.
- New `llama-ai-eng` name + the back-compat resolver candidate list is a small ongoing complexity (three names resolve to "the default"). *Mitigated:* the resolver already exists; we extend its candidate set. Follow-up: drop `ai-eng`/`ai-engineer` legacy candidates one release after migration.

**Repaid:**
- Removes the entire "met-on-upload" deferral debt: the default no longer depends on an unuploaded artifact, a pinned placeholder digest, or a fail-closed mirror cascade. It works today with zero external dependencies.
- Removes the preview-net-as-default-fallback complexity from the hot path.
- Resolves the user-facing deep-model sentinel with a real, verified, Apache-2.0 7B persona — the maximus deep offering is no longer a TODO.
- Brings the repo into Llama 3.2 Community License compliance (naming, attribution, AUP) — a license-correctness debt that did not exist before but must be paid the moment a Llama base ships.

**Net:** strongly negative (debt reduced). The largest v1 debts (unuploaded-artifact dependency, placeholder digest, preview-net cascade, unresolved deep sentinel) are repaid; the residual is a clearly-labeled dormant lane and a small back-compat naming window, both with home tickets.

## Recommended implementation order

1. **NOTICE + `licenses/` bundle + LICENSE pointer** (compliance first — before any Llama base ships in code).
2. **Modelfiles** (`Modelfile.default` new, `Modelfile.deep` new; comment the dormant `.preview`/`.production`).
3. **pyproject keys** (default_*, deep_persona_*, dormant-label the `ai_eng_*` keys).
4. **`setup.sh install_models()` rewrite** (persona-wrap default; ladder behind `ARAIL_AI_ENG_SELFHOSTED=1`; deep OFFER; preserve guards). Leave Surface-B sentinel.
5. **Catalog + app.py resolver** (default row → `llama-ai-eng`; deep 7B row; resolver candidate list; keep Surface-B sentinel guards).
6. **build_ai_eng.* base re-base to Llama-3.2-1B** (dormant lane consistency).
7. **Copy** (README incl. "Built with Llama", CLAUDE.md hide-the-base exception, docs/INSTALL, tuning.html, CHANGELOG).
8. **Tests** per strategy; update qwen-hiding guard + setup-ladder tests; add the 16GB-safe-default + Llama-attribution regression guards. Mock everything; no real pulls/loads.
