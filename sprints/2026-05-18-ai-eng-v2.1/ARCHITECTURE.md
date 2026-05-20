# Architecture: ai-eng v2.1 default model + AeroLLM maximus 72B lift

**Date:** 2026-05-18
**Spec:** [VISION.md](./VISION.md) (commit 64b9279)
**Source plan:** `/Users/netsushi/.claude/plans/pure-forging-pizza.md`
**Sprint:** 2026-05-18-ai-eng-v2.1 on `qukaizen/arail-ai-eng-v2.1`

---

## 1. Restatement

QuKaiZen has published the v2.1 LoRA adapter that ARAIL's setup.sh has been
silently probing for since v1.0.0. This sprint turns that adapter into a
shipped Ollama tag (`qukaizen/ai-eng:3b`) by (a) merging two candidate
variants — Candidate A (`mlx_lm.fuse` into the 4-bit MLX base the adapter
was trained on) and Candidate B (`peft.merge_and_unload` into a bf16 HF
base, the format the user explicitly asked for despite the base mismatch);
(b) running a deterministic bench to choose between them or abort; (c)
publishing the winner to HF (two repos) and Ollama under explicit
user-gated authority; (d) wiring `pyproject.toml`, `setup.sh`, the catalog,
and the Modelfiles so a clean install no longer fires the yellow fallback
warning. In the same sprint we lift `aerollm_maximus` from the 7B
placeholder to `mlx-community/Qwen2.5-72B-Instruct-4bit` (top of AeroLLM's
proven 19/19 envelope; family-consistent with the 3B default). The
operator scripts that drive the build/bench are reusable for v2.2+ adapter
revs; the publish step is a one-shot but its authority chain is
codified so future revs can re-use the same gates.

## 2. Assumptions

Listed because each is a single point of failure if wrong.

1. **`mlx_lm.fuse` produces a directory that `mlx_lm.load` and
   `mlx_lm.convert` can consume**, including a `config.json` matching
   Qwen2.5-3B-Instruct architecture. (If not, Candidate A's GGUF path
   breaks at conversion.)
2. **The LoRA `adapters.safetensors` is in mlx_lm layout** (`adapter_config.json`
   with `peft_type: LORA` keys is *not* guaranteed). For Candidate B we
   may need a format-translation step: load mlx weights, re-key into
   PEFT `lora_A.weight`/`lora_B.weight` names, write a fresh PEFT-format
   adapter directory, then `PeftModel.from_pretrained`. Builder must
   verify the adapter layout before assuming `peft.merge_and_unload`
   works directly.
3. **`llama.cpp/convert_hf_to_gguf.py` supports Qwen2.5-3B architecture**
   at the version the build script pins. Pin the llama.cpp commit;
   don't pull `main`.
4. **`huggingface_hub` is logged in (`~/.cache/huggingface/token` exists)**
   with read access to `qukaizen/qkz-opus4.7-aieng-3b-v2.1-adapter`
   and (for Phase 2) write access to the `qukaizen` org. The build
   script must `huggingface-cli whoami` and refuse to proceed if the
   token is missing or read-only at publish time.
5. **`ollama` is installed and the user has run `ollama login`** before
   Phase 2. Phase 1 only needs local `ollama create`, not `push`.
6. **The dev box has ≥ 30 GB free disk** for build artifacts (adapter ~10 MB,
   mlx-fused ~2 GB, bf16-merged ~6.2 GB, intermediate HF conversion ~6 GB,
   GGUF outputs ~2–6 GB, base-model HF snapshot ~6.2 GB for Candidate B).
7. **The dev box has ≥ 16 GB free RAM at the moment of bf16 merge** and
   ≥ 8 GB free at GGUF conversion. The portal must not be running during
   build (memory note). The build script verifies free RAM before each
   heavy step and aborts gracefully if below threshold.
8. **72B model is registered, not loaded, on the dev box during this
   sprint.** Registration is a `.env` value + catalog entry; actual
   inference is a separate verification step gated on RAM headroom.
9. **Re-running `./arailctl setup` is a no-op** when `ai-eng` already
   exists in Ollama (setup.sh:752 short-circuit). We rely on this for
   idempotency.
10. **HF and Ollama registries serve the same content within a
    propagation window of minutes**, not hours. If propagation lags,
    the Phase-3 wire-in `./arailctl setup` test may legitimately fail
    on the first try; the fallback path must say so.

## 3. Data flow

### 3.1 Build pipeline (Phase 1, all local)

```
                    qukaizen/qkz-opus4.7-aieng-3b-v2.1-adapter (HF)
                              |
                  huggingface-cli download
                              v
                    build/adapter/  (adapters.safetensors + adapter_config.json)
                              |
              +---------------+---------------+
              | (A)                           | (B)
              v                               v
     mlx-community/Qwen2.5-3B-Instruct-4bit   Qwen/Qwen2.5-3B-Instruct (bf16)
              |                               |
       mlx_lm.fuse                     [format-xlate adapter to PEFT
              |                        layout if needed]
              v                               |
     build/mlx-fused/                         v
     (4-bit safetensors)              peft.PeftModel.from_pretrained
              |                                + merge_and_unload
              |                               |
              |                               v
              |                       build/bf16-merged/
              |                       (bf16 safetensors)
              +---------------+---------------+
                              |
                              v
                      scripts/bench_ai_eng.py
                       (deterministic, seed=42)
                              |
            +-----------------+-----------------+
            v                                   v
   build/BENCH-v2.1.md                  exit code => winner
   (committed to repo as                 0 = ship B
   models/ai-eng/BENCH-v2.1.md)          1 = ship A
                                         2 = abort both
                              |
                              v
                      [winner only]
                              |
        if A:  mlx_lm.convert --quantize false -> HF safetensors
               -> llama.cpp/convert_hf_to_gguf.py --outtype f16
        if B:  llama.cpp/convert_hf_to_gguf.py --outtype bf16
                              |
                              v
              build/ai-eng-3b-v2.1.{f16|bf16}.gguf
                       + SHA256SUMS
                              |
                              v
              build/ai-eng-3b-v2.1.Modelfile
              (FROM build/...gguf, SYSTEM verbatim
               from models/ai-eng/Modelfile.production,
               PARAMETER temperature 0.7, num_ctx 8192)
                              |
                              v
              ollama create qukaizen/ai-eng:3b -f build/...Modelfile
                              |
                              v
              smoke: ollama run qukaizen/ai-eng:3b "Explain LoRA in 3 sentences."
                     (must return non-empty in < 30 s)
```

**Checksum opportunities** (every one of these gets a SHA256 in
`build/SHA256SUMS` for later forensic comparison):
- `build/adapter/adapters.safetensors`
- `build/mlx-fused/*.safetensors`
- `build/bf16-merged/*.safetensors`
- final GGUF

### 3.2 Publish pipeline (Phase 2, side effects — user-gated)

```
       [BENCH-v2.1.md reviewed by human; explicit "publish now"]
                              |
                              v
  +----+-------------------+--------------------+
  |                        |                    |
  v                        v                    v
HF push #1:              HF push #2:        Ollama push:
qukaizen/                qukaizen/          ollama push
qkz-opus4.7-             qkz-opus4.7-       qukaizen/ai-eng:3b
aieng-3b-v2.1            aieng-3b-v2.1-gguf
(safetensors             (GGUF, single
+ README.md              file + README)
+ LICENSE)
  |                        |                    |
  +------------+-----------+--------------------+
               v
       record-of-push: build/PUBLISHED.json
       (timestamps, SHAs, registry URLs)
               v
       commit to repo: models/ai-eng/PUBLISHED-v2.1.json
```

**Side-effect boundary:** every action above the `record-of-push` line is
irreversible. The build script's publish entry point (`scripts/build_ai_eng.sh publish`)
re-prompts the user with the exact list of registry destinations and
SHA256s before invoking each push.

### 3.3 Runtime fallback flow (post-publish, what a clean install sees)

```
./arailctl setup
   |
   v
setup.sh ai-eng install block (lines 730–797)
   |
   v
ollama show ai-eng?  --yes--> done (idempotent)
   |
   no
   v
ollama pull qukaizen/ai-eng:3b  (timeout 900s)
   |
   +-- success ---> Modelfile.production -> ollama create ai-eng -> done
   |
   +-- failure: classify exit
        |
        +-- network unreachable / DNS / timeout:
        |       "ai-eng:3b pull timed out — network unreachable. Falling
        |        back to qwen2.5:7b preview base. Re-run ./arailctl setup
        |        when connectivity is restored."
        |
        +-- 404 / not found:
        |       "ai-eng:3b not found on registry — this is unexpected for
        |        v1.0.0+. The registry tag may have been moved; check
        |        https://ollama.com/qukaizen/ai-eng. Falling back to
        |        qwen2.5:7b preview base."
        |
        +-- 403 / auth:
        |       "ai-eng:3b pull rejected — registry auth issue (run
        |        'ollama login' if you have a registry account; this tag
        |        should be public, so this may be a transient registry
        |        issue). Falling back to qwen2.5:7b preview base."
        |
        +-- corrupt / checksum mismatch / partial pull:
                "ai-eng:3b pull completed but checksum invalid — likely a
                 corrupt download. Removing partial blob and falling back
                 to qwen2.5:7b preview base. Re-run ./arailctl setup to retry."
                (Action: ollama rm qukaizen/ai-eng:3b 2>/dev/null before fallback)
```

The four messages above each address the warmup-overlay-invisible MEMORY
rule: never go silent, name the cause, name the next action.

## 4. Interface contracts

### 4.1 `scripts/build_ai_eng.sh`

**Subcommands:**
- `build` (default) — execute Phase 1 end-to-end (download → both candidates
  → bench → convert → local ollama create)
- `bench-only` — assume `build/mlx-fused/` and `build/bf16-merged/` exist;
  re-run the bench
- `convert <a|b>` — convert the named candidate to GGUF
- `publish` — Phase 2; requires explicit `--yes-i-have-read-bench`
  flag *and* an interactive y/N prompt that echoes the registry destinations
- `clean` — remove `build/` (but never `models/ai-eng/BENCH-v2.1.md`)
- `dry-run` — print every command without executing (used by tests)

**Flags / env vars:**
- `--adapter-repo` (default `qukaizen/qkz-opus4.7-aieng-3b-v2.1-adapter`)
- `--bf16-base` (default `Qwen/Qwen2.5-3B-Instruct`)
- `--mlx-base` (default `mlx-community/Qwen2.5-3B-Instruct-4bit`)
- `--bench-prompts` (default `models/ai-eng/bench-prompts.v2.1.yaml`)
- `--llama-cpp-rev` (pinned commit, default e.g. `b3500`)
- `--min-free-ram-gb` (default 16; aborts before bf16 merge if below)
- `--min-free-disk-gb` (default 30)
- `ARAIL_BUILD_DIR` (default `./build/`)
- `HF_TOKEN` / `HUGGING_FACE_HUB_TOKEN` (passed through)

**Exit codes:**
- 0 — success; ready to publish
- 10 — both candidates failed bench gate (sprint shelves per VISION §disconfirming)
- 11 — Candidate B regressed >3pp; Candidate A shipped (informational, not failure)
- 20 — OOM-pre-check tripped (free RAM below threshold)
- 21 — disk-pre-check tripped
- 30 — HF download failed (network/auth)
- 40 — adapter format unknown (couldn't translate to either fuse path)
- 50 — GGUF conversion failed
- 60 — ollama create failed
- 70 — publish refused (no `--yes-i-have-read-bench` or interactive declined)

**Idempotency:** every step writes a sentinel file (`build/.step-<name>.done`)
on completion. Re-running `build` skips any step whose sentinel exists
unless `--force` is passed. `clean` removes sentinels.

**OOM safety:** before any of (`mlx_lm.fuse`, `peft.merge_and_unload`,
`mlx_lm.convert`, `convert_hf_to_gguf.py`, `ollama create`), the script
runs `vm_stat` / `sysctl hw.memsize` to compute free RAM and aborts with
exit 20 if below `--min-free-ram-gb`. The script also refuses to run if
`pgrep -f 'arail.portal'` finds a running portal process; user must stop
the portal first.

### 4.2 `scripts/bench_ai_eng.py`

**Inputs:**
- `--candidate-a-path build/mlx-fused/`
- `--candidate-b-path build/bf16-merged/`
- `--baseline-path` (HF id or local path; default `Qwen/Qwen2.5-3B-Instruct`)
- `--prompts-file models/ai-eng/bench-prompts.v2.1.yaml`
- `--mmlu-sample-size 50` (fixed-seed sample from cais/mmlu)
- `--seed 42`
- `--max-tokens 512`
- `--temperature 0.0` (greedy for reproducibility)
- `--out build/BENCH-v2.1.md`

**Prompt taxonomy** (12 prompts, in `models/ai-eng/bench-prompts.v2.1.yaml`):
- 4 AI-engineering reasoning prompts (LoRA, RoPE, KV cache, quantization tradeoff)
- 3 code-generation prompts (Python; expected output regex-checkable)
- 2 honesty/"don't know" prompts (deliberately obscure)
- 2 multi-turn context prompts
- 1 ambiguity-handling prompt

**Methodology:**
- Same seed, same temperature 0.0, same max-tokens, same prompt set across all three
  models (A, B, baseline) and against `qwen2.5:7b`-with-persona via Ollama
  for the 5-prompt side-by-side AI-eng quality gate.
- MMLU sample: 50 questions drawn with `random.Random(42).sample()` from a
  fixed subset list committed in `models/ai-eng/mmlu-sample-v2.1.json` (so
  the sample is byte-stable across re-runs — not "random per run").
- Perplexity check: compute on a 1000-token fixed code+prose corpus
  committed at `models/ai-eng/perplexity-corpus.txt`. Both candidates and
  baseline must be within a 1.5× window of each other; if not, the bench
  flags it as a quality cliff in the report.
- Generation-coherence: each prompt's output is captured verbatim in the
  report; a human eyeballs them post-run. Bench script does not attempt
  to auto-grade coherence — that's a human gate.

**Gate logic (exit code):**
- exit 2 ("abort both"): both candidates fail MMLU within 3pp of baseline
  OR perplexity cliff vs baseline (>1.5× window) OR Candidate A loses to
  `qwen2.5:7b`-persona on ≥3 of 5 AI-eng prompts
- exit 1 ("ship A"): Candidate B regresses >3pp vs Candidate A on MMLU
  OR Candidate B perplexity > 1.2× Candidate A's
- exit 0 ("ship B"): A and B within 3pp on MMLU AND B beats `qwen2.5:7b`-persona
  on ≥3 of 5 AI-eng prompts

**Confidence interval note:** with n=50 MMLU questions and a binomial
proportion, the 95% CI half-width on a 50% accuracy point is ±13.9pp; on
70% it's ±12.7pp. The "3pp gate" therefore is *not* statistically
distinguishable at n=50 — it functions as a "vibe gate" to catch only
large regressions. We document this caveat in the BENCH-v2.1.md output
explicitly so future readers don't over-trust the number. **A larger
MMLU sample (n≥200) is filed as tech debt for v2.2.**

**Output schema (BENCH-v2.1.md):**
```markdown
# ai-eng v2.1 bench
**Date:** YYYY-MM-DD  **Host:** <hostname> (<chip>, <RAM> GB)
**Adapter SHA:** <sha>  **Seed:** 42

## Summary
- Winner: <A | B | abort>
- Gate confidence: low (n=50 MMLU; tech-debt ticket TD-v2.2-bench-n)

## Numbers
| Model | MMLU(50) | Perplexity | AI-eng head-to-head (out of 5) | Latency p50 (ms) |
|---|---|---|---|---|
| Qwen2.5-3B-Instruct (baseline) | … | … | n/a | … |
| Candidate A (MLX 4-bit fused) | … | … | … | … |
| Candidate B (bf16 merged)     | … | … | … | … |
| qwen2.5:7b + persona (incumbent) | … | … | reference | … |

## Per-prompt outputs (verbatim)
…

## Decision rationale
…
```

### 4.3 Build artifact contract

After a successful `build`, `build/` looks like:
```
build/
  .step-download.done
  .step-candidate-a.done
  .step-candidate-b.done
  .step-bench.done
  .step-convert.done
  .step-ollama-create.done
  SHA256SUMS
  adapter/
  mlx-fused/                  # Candidate A weights
  bf16-merged/                # Candidate B weights
  ai-eng-3b-v2.1.<fmt>.gguf   # winner only
  ai-eng-3b-v2.1.Modelfile
  BENCH-v2.1.md               # also copied to models/ai-eng/BENCH-v2.1.md
```

**What survives a `clean`:** nothing under `build/`. **What is committed:**
`models/ai-eng/BENCH-v2.1.md`, `models/ai-eng/bench-prompts.v2.1.yaml`,
`models/ai-eng/mmlu-sample-v2.1.json`, `models/ai-eng/perplexity-corpus.txt`.
The GGUF is *not* committed (large binary; published via HF + Ollama).

### 4.4 Ollama Modelfile contract

```
FROM ./ai-eng-3b-v2.1.<fmt>.gguf
SYSTEM """<verbatim copy from models/ai-eng/Modelfile.production line 3, optionally suffixed with " (v2.1)" if D4 approved>"""
PARAMETER temperature 0.7
PARAMETER num_ctx 8192
```

`FROM` resolves relative to the Modelfile's directory; `ollama create`
must be invoked with `cwd=build/` or the path must be absolute. **The
SYSTEM string is read by the build script via `awk '/^SYSTEM /' models/ai-eng/Modelfile.production`
and copied byte-identical**; the build script verifies a SHA256 match
before `ollama create`, exiting 60 if drifted.

### 4.5 HF model card schema (Phase 2)

Required fields on both `qukaizen/qkz-opus4.7-aieng-3b-v2.1` and
`-gguf` repo READMEs:
- `license:` (D1; default Apache-2.0)
- `base_model: Qwen/Qwen2.5-3B-Instruct` (with note that the LoRA was
  trained against the 4-bit MLX projection of this base)
- `library_name:` (`transformers` for the safetensors repo, `gguf` for the GGUF repo)
- `tags: [qukaizen, ai-engineering, lora-merged, qwen2.5]`
- **Training intent paragraph** (D1; one paragraph from QuKaiZen Project
  Nucleus owner — without this, Phase 2 is BLOCKed)
- **Bench numbers** (copy from BENCH-v2.1.md table)
- **Usage snippet** (Ollama `ollama pull qukaizen/ai-eng:3b` for GGUF repo;
  `AutoModelForCausalLM.from_pretrained` for safetensors repo)
- **Provenance:** "Merged from adapter `qukaizen/qkz-opus4.7-aieng-3b-v2.1-adapter`
  on YYYY-MM-DD; adapter SHA `<sha>`; merge method `<A or B>`."

## 5. Failure modes

| # | Failure | Detection | Recovery |
|---|---|---|---|
| F1 | Adapter format isn't mlx_lm (no `adapter_config.json` with mlx keys) | `build_ai_eng.py` validates expected keys post-download | Exit 40; report which keys missing. Manual remediation needed. |
| F2 | `mlx_lm.fuse` fails (architecture mismatch) | non-zero return + stderr | Exit 50; capture stderr to `build/error-candidate-a.log`; sprint can still proceed with Candidate B alone (degraded — single-candidate ship) |
| F3 | `peft.merge_and_unload` fails because adapter is mlx-format not PEFT-format | Try block catches `KeyError` on `lora_A.weight` | Format-translate to PEFT layout then retry once; if still fails, exit 50; Candidate A still possible. |
| F4 | bf16 merge OOMs during `merge_and_unload` (needs ~12 GB transient) | Pre-check `vm_stat` before merge; also catch process kill via wait status | Exit 20; suggest closing portal/browser. **Kill switch:** trap SIGTERM, write checkpoint sentinel so re-run skips completed work. |
| F5 | Candidate B base-mismatch lossy: bf16 merge regresses >3pp vs Candidate A | `bench_ai_eng.py` exit 1 | Ship Candidate A; document in BENCH-v2.1.md; informational not failure. |
| F6 | Both candidates regress vs baseline Qwen2.5-3B-Instruct (>3pp drop OR perplexity cliff) | `bench_ai_eng.py` exit 2 | **Sprint shelves.** Per VISION §disconfirming. Builder writes BUILD_LOG.md noting shelve; does NOT proceed to Phase 2. Escalate to QuKaiZen for retrain. |
| F7 | GGUF conversion fails (Qwen2.5 architecture unsupported at pinned llama.cpp rev) | non-zero from convert script | Exit 50; pin a different llama.cpp commit and retry. Document in BUILD_LOG. |
| F8 | `ollama create` fails (Modelfile syntax, GGUF too large for context) | non-zero from ollama | Exit 60; capture stderr; manual debug. |
| F9 | SYSTEM-prompt SHA drifts (someone edited Modelfile.production mid-build) | build script's SHA verify step | Exit 60; abort. Re-read source-of-truth. |
| F10 | `huggingface-cli whoami` is anonymous or token lacks `qukaizen` write at publish | `publish` subcommand probes before push | Exit 30; instruct user to `huggingface-cli login` with a write token. |
| F11 | Publish push partially succeeds (HF #1 ok, HF #2 fails) | per-push exit captured | Record partial state in `build/PUBLISHED.json`; idempotent re-run skips completed pushes; manual cleanup is `huggingface-cli repo delete` if rollback wanted. |
| F12 | `ollama push` fails (registry 5xx) | non-zero from ollama | Exit 70; user retries; HF pushes already done are safe to leave (they are the source of truth). |
| F13 | Setup-on-clean-machine: ai-eng pull 5xx after publish | setup.sh ai-eng block catches `ollama pull` non-zero | Show classified message per §3.3; fall back to Modelfile.preview path; user re-runs setup later. |
| F14 | Setup-on-clean-machine: ai-eng pull corrupt (timeout mid-stream, partial blob) | non-zero AND blob exists in `~/.ollama/models/` | `ollama rm qukaizen/ai-eng:3b` then fall back; message names "corrupt download" explicitly. |
| F15 | 72B model registration on dev box without 96 GB RAM tries to load | `arailctl benchmark_models` (registration is metadata-only, but a smoke inference would OOM) | Registration is metadata only (catalog + .env). No load. **Smoke inference is a separate, gated step in Phase 4 step 3; skipped on dev box per SPRINT notes.** Documented in BUILD_LOG. |
| F16 | Idempotency: re-run setup picks the *fallback* path because the new tag pull failed first time | setup.sh:752 only checks `ollama show ai-eng`; doesn't check if it's the production base | Add a guard: if `ai-eng` exists but its underlying base is `qwen2.5:7b`, info-log "previous run used preview fallback; re-pulling production tag" and re-execute pull. (Tech debt or in-sprint? — see §7.) Decision: **in-sprint**, small change. |
| F17 | Credential leak via build script logging HF token in error output | All commands that consume `HF_TOKEN` redirect token through env, never argv; build script's error capture greps out `hf_*` tokens before writing logs | Tested by a unit test that sets `HF_TOKEN=hf_FAKE_LEAK_TOKEN` and asserts the string never appears in any file under `build/`. |
| F18 | `peft` accidentally writes adapter back with the base model's HF token embedded | `peft.merge_and_unload` saves bf16 weights only; verify no `token` field in saved `config.json` | Post-save check: grep saved config for any `hf_` prefix. |
| F19 | License contamination: adapter card doesn't specify a license; merged model gets pushed without one | D1 gate: publish subcommand refuses to run if `--license` flag absent | Exit 70 with message naming D1. |

## 6. Test strategy

### 6.1 Unit

- `test_bench_harness_deterministic`: run bench on a 2-prompt synthetic
  set with seed=42 twice, assert byte-identical output.
- `test_modelfile_sha`: assert the SYSTEM string extracted from
  `models/ai-eng/Modelfile.production` matches the SHA recorded in
  the build script's constant. (Catches accidental edits.)
- `test_mmlu_sample_stable`: assert `models/ai-eng/mmlu-sample-v2.1.json`
  is the byte-stable seeded sample from the canonical MMLU subset.
- `test_token_redaction`: assert `_sanitize_log_line` strips `hf_*`
  bearer tokens from arbitrary input lines.
- `test_classify_pull_error`: feed the setup.sh error-classifier
  synthetic stderr lines (timeout, 404, 403, checksum) and assert each
  routes to the correct user-facing copy.

### 6.2 Integration

- `--dry-run` mode: every code path in `build_ai_eng.sh` exercised
  without downloads or model loads. Asserts that every `step` writes
  the right sentinel; idempotent re-run is a true no-op.
- `bench-only` re-run on pre-existing `build/mlx-fused/` and
  `build/bf16-merged/` produces a byte-identical `BENCH-v2.1.md`
  (modulo timestamp line, which the test strips).

### 6.3 Smoke

- Post-build: `ollama run qukaizen/ai-eng:3b "hello"` returns non-empty
  within 30 s on the dev box.
- Post-wire: `./arailctl setup` on a fresh `lab/` directory (with
  Ollama state preserved) is a no-op when `ai-eng` already exists
  (setup.sh:752 short-circuit).

### 6.4 Regression

- Re-running `./arailctl setup` after wire-in is a no-op (idempotency,
  setup.sh:751-753).
- `ollama show ai-eng` reports v2.1-stamped SYSTEM (regression vs the
  pre-sprint preview SYSTEM string).
- `pyproject.toml` `[tool.arail.models]` shape unchanged; `airllm_*`,
  `coder_*`, `ai_eng_*` keys all still resolve.
- Legacy `aerollm` alias still points at the minimalist value
  (`Qwen2.5-7B-Instruct-4bit`); no consumer breakage.
- F16 specifically: install on a machine that previously got the
  preview fallback; re-run setup picks up the production tag.

### 6.5 Performance / Security

- Performance is not a primary axis this sprint (we're swapping a 7B
  base for a 3B — latency should improve; we log it but don't gate).
- Security: F17 (token redaction unit test) is the load-bearing check.
  Plus a manual review of `build/PUBLISHED.json` and BUILD_LOG.md for
  any echoed token before the publish commit.

### 6.6 QA brief (for `/qa` per ARAIL CLAUDE.md test allocation)

| Bucket | % | Concrete tests for this sprint |
|---|---|---|
| Setup-on-clean-machine | 30% | (a) fresh `./arailctl setup` on a clean worktree post-publish — zero yellow warnings; (b) simulate registry 404 (block `ollama.com` in `/etc/hosts`) and confirm fallback message matches §3.3 copy verbatim; (c) simulate corrupt pull (kill ollama mid-pull) and confirm `ollama rm` + fallback fires; (d) re-run setup is no-op (idempotency, F16 covered). |
| Buddy quality | 30% | Run the 5-prompt AI-eng head-to-head inside the chat UI (Compute Source = my_machine, model = ai-eng): code gen, LoRA explanation, "don't know" honesty, multi-turn context, ambiguity. Compare side-by-side to qwen2.5:7b-persona. Pass = wins ≥3/5 (matches bench gate). |
| Security | 20% | (a) grep build/ + sprint dir + BUILD_LOG.md for `hf_` token strings — must find zero; (b) verify `lab/data/secrets.env` permission stays `0600` after build; (c) inspect HF model card for accidental training-data leak (e.g., personal email, internal repo names); (d) verify publish subcommand refuses without explicit `--yes-i-have-read-bench`. |
| Happy path | 10% | `./arailctl start` → /chat → ai-eng auto-selected → 1 prompt → response renders. |
| Regression | 10% | (a) `./arailctl benchmark_models` registers 72B as maximus deep candidate; (b) legacy `aerollm` alias resolves; (c) `pyproject.toml` shape unchanged. |

## 7. Tech debt assessment

**Added:**
- 3 new operator scripts in `scripts/` (`build_ai_eng.sh`, `build_ai_eng.py`,
  `bench_ai_eng.py`). Reusable for v2.2+ adapter revs — they accept
  `--adapter-repo` and version-stamped output paths. Not dead code.
- Two new committed corpora: `mmlu-sample-v2.1.json` (~50 KB) and
  `perplexity-corpus.txt` (~5 KB). These are version-stamped; v2.2
  will get its own.
- Bench `n=50` MMLU sample is statistically weak (95% CI ±13–14pp). Filed:
  **TD-v2.2-bench-n** — raise to n≥200 for v2.2 retrain or whenever
  bench needs to discriminate small deltas.
- bf16-merge format-translation glue (if needed for Candidate B's PEFT
  consumption). If shipped, this glue lives in `scripts/build_ai_eng.py`
  and is a candidate for extraction into a shared utility when a third
  adapter rev needs it.
- `Modelfile.preview` semantics shift: it was a "before production weights
  exist" path; now it's "emergency fallback if registry is down". Same
  file, different role. We accept the dual-role for now.

**Repaid:**
- Removes a permanently-pending fallback warning that's been live since v1.0.0.
- Removes a hedging sentence from `models_catalog.yaml` and README.
- Closes the load-bearing "ai-eng:3b not yet published" comment in setup.sh.
- Lifts `aerollm_maximus` from a placeholder (7B == minimalist value)
  to a tier-coherent 72B. The split into `aerollm_minimalist` /
  `aerollm_maximus` parallels the existing `airllm_*` split — this is
  a normalization, not a new edge case. Legacy `aerollm` alias preserved
  for one release per ARAIL convention.

**Net:** Slightly negative debt (cleanup > additions). The reusable build
scripts plus the codified publish-authority chain pay forward for v2.2+.

**Modelfile.preview sunset plan:** keep through v1.1.0 as the documented
fallback for transient registry outages (per §3.3); revisit in a future
retro once we have ≥6 months of registry-uptime data. File: **TD-v1.2-sunset-preview**.

## 8. Phase boundaries — confirm or rebut

The plan's three commits (build / publish / wire) are correct **with one
amendment**: the **wire** commit should be split into two atomic units:

- **Commit 3a: `wire(ai-eng): swap setup.sh + pyproject + catalog to v2.1 production tag`**
  — `pyproject.toml` (ai_eng_* comment update), `setup.sh:766-778` fallback
  copy retune + F16 guard, `models_catalog.yaml` entry update,
  `models/ai-eng/Modelfile.production` (optional v2.1 stamp),
  `models/ai-eng/Modelfile.preview` (demote to emergency fallback copy),
  README hedge trim. **Verifiable in isolation:** clean-machine `./arailctl setup`
  produces zero warnings.
- **Commit 3b: `wire(aerollm): lift maximus secondary to Qwen2.5-72B-Instruct-4bit`**
  — `pyproject.toml` `aerollm_maximus` lift, add `aerollm_minimalist`,
  `scripts/setup.sh:79-81` mirror change. **Verifiable in isolation:**
  `./arailctl upgrade maximus` resolves the 72B value; registration only,
  no smoke load.

**Rationale for the split:** the two changes have *independent failure
modes and independent verification stories*. If the 72B lift triggers an
unexpected resolver issue, we don't want to revert the ai-eng wire-in
with it. They are two separable de-risking units that happen to belong
in one sprint for thematic reasons.

**Final phase structure:**

| Commit | Scope | Gates |
|---|---|---|
| 1 | `build(ai-eng): scripts + bench + local Ollama tag` | Bench exit 0 or 1 (not 2) |
| 2 | `publish(ai-eng): HF + Ollama push under qukaizen/` | D1 license signed off; D3 explicit user yes; D4 prompts reviewed |
| 3a | `wire(ai-eng): setup.sh/pyproject/catalog v2.1 default` | Clean-machine setup zero warnings |
| 3b | `wire(aerollm): maximus secondary 72B lift` | `arailctl upgrade maximus` resolves to 72B value; registration confirmed |

## 9. Recommended implementation order

1. Author `models/ai-eng/bench-prompts.v2.1.yaml`, `mmlu-sample-v2.1.json`,
   `perplexity-corpus.txt` — corpus first, before the scripts that consume
   them. Get user sign-off on prompt list (D4).
2. Implement `scripts/build_ai_eng.py` core: adapter download, format
   detection, Candidate A path (`mlx_lm.fuse`), Candidate B path
   (with PEFT format translation if needed).
3. Implement `scripts/bench_ai_eng.py` with `--dry-run` first; verify
   determinism on a tiny synthetic prompt set.
4. Implement `scripts/build_ai_eng.sh` orchestrator with subcommands,
   sentinels, OOM/disk pre-checks, exit-code matrix.
5. Run `./scripts/build_ai_eng.sh build` on the dev box. **Stop the portal first.**
6. Review `BENCH-v2.1.md` with the user. If exit 2, shelve sprint and write BUILD_LOG.md.
7. **Decide D1 (license) and D2 (Ollama upload format) with the user.**
8. **Get explicit "publish now" from the user (D3).** Run `./scripts/build_ai_eng.sh publish`.
9. Verify HF + Ollama tags resolve from a fresh shell (`ollama pull qukaizen/ai-eng:3b`
   into a throwaway Ollama dir).
10. Commit 3a (ai-eng wire-in). Test: clean worktree `./arailctl setup` → zero warnings.
11. Commit 3b (72B lift). Test: `./arailctl upgrade maximus` → resolves to 72B value.
12. Hand off to `/qa` with TEST_REPORT brief from §6.6.
