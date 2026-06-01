# Consolidation: one ai-eng packaging pipeline

**Date:** 2026-05-31
**Spec:** model-hosting reframe sprint (PR #75) — [ARCHITECTURE.md](./ARCHITECTURE.md)
**Mode:** architect / design
**Scope:** fold `scripts/package_ai_eng.sh`'s unique value into the mature
`scripts/build_ai_eng.{sh,py}` pipeline; retire the scaffold; reconcile the
`publish` distribution model to the self-hosted-GGUF design.

## Restatement

The reframe sprint added a brand-new developer scaffold,
`scripts/package_ai_eng.sh`, to package the bottled ai-eng model: merge a LoRA
into a Qwen2.5-1.5B base, convert to GGUF at a chosen quant, emit a Modelfile +
NOTICE beside the artifact, print the GGUF sha256, and print manual
HF/GitHub-release/CDN upload commands aligned with the placeholders in
`pyproject.toml [tool.arail.models]` and probed by `check_ai_eng_artifact.sh`.
But a mature pipeline already existed: `build_ai_eng.{sh,py}` (subcommands
build / bench-only / convert / publish / clean / dry-run) with OOM and disk
pre-checks, idempotent sentinels, bench gating, defined exit codes, HF-token
sanitisation, and a SYSTEM-SHA-verified Modelfile generator. The two overlap.
The user has decided to consolidate to ONE pipeline: keep `build_ai_eng`, fold
in the scaffold's unique value, and retire `package_ai_eng.sh`. The hard part
is that `build_ai_eng.py`'s `publish` subcommand still encodes the OLD
distribution model (push an `ollama.ai` registry tag `qukaizen/ai-eng:1.5b` plus
two HF repos), which contradicts the reframe's canonical model: a self-hosted
GGUF pulled via `ollama pull hf.co/<repo>:<quant>`, mirrored to a
sha256-verified GitHub Release and optional CDN, with the sha256 pinned into
pyproject and verified at setup time.

## Two critical findings the builder must know

1. **`package_ai_eng.sh`'s delegation to `build_ai_eng.py` is already dead
   code.** It calls
   `python3 build_ai_eng.py --base-dir … --lora-dir … --output-dir … --merge-only`.
   `build_ai_eng.py` has **no** `--base-dir`, `--lora-dir`, `--output-dir`, or
   `--merge-only` flags (confirmed by grep — zero matches). `argparse` rejects
   them, the `||` fallback fires every time, and the inline heredoc peft-merge
   does the real work. So the scaffold never actually shares the mature merge
   path — it duplicates it with an un-guarded, un-sanitised inline merge. This
   is a correctness reason to retire it, not merely a tidiness one.

2. **`build_ai_eng.py publish` encodes the OLD distribution model.** It pushes
   an `ollama.ai` registry tag (`qukaizen/ai-eng:1.5b`) and two HF repos
   (`…-v2.1` safetensors + `…-v2.1-gguf`), and writes those into
   `build/PUBLISHED.json`. The reframe's canonical model has **no ollama.ai
   registry tag** — distribution is `ollama pull hf.co/<repo>:<quant>` against a
   self-hosted HF GGUF repo, GitHub Release mirror, optional CDN. The publish
   subcommand must be reconciled, not just renamed.

---

## 1. Decision: retire mode

`build_ai_eng.{sh,py}` is canonical. `package_ai_eng.sh` is retired.

**Recommended retire mode: (b) replace with a thin deprecation shim.** Delete
the 329-line scaffold body and replace it with a short shim that prints a
deprecation notice and execs `build_ai_eng.sh publish` (passing through any
args), exiting with that command's exit code. Rationale:

- A shim is friendlier if anyone scripted the old name (the reframe sprint and
  setup.sh skip message both reference it; external forks may too).
- It keeps a single discoverable retirement breadcrumb instead of a silent 404.
- The existing security tests (`test_package_script_embeds_no_credentials`,
  `…_passes_bash_syntax`) keep passing trivially against a small shim, and the
  missing-input / weight-download-doc tests get *replaced* (see §5) rather than
  deleted wholesale.

Shim contract (exact target the builder writes):

```bash
#!/usr/bin/env bash
# package_ai_eng.sh — DEPRECATED. Consolidated into build_ai_eng.sh.
# Retained as a thin shim so old call sites keep working. Use:
#   ./scripts/build_ai_eng.sh publish --yes-i-have-read-bench --license Apache-2.0
set -euo pipefail
echo "[package_ai_eng] DEPRECATED: this scaffold was consolidated into build_ai_eng.sh." >&2
echo "[package_ai_eng] Forwarding to: scripts/build_ai_eng.sh publish $*" >&2
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "${SCRIPT_DIR}/build_ai_eng.sh" publish "$@"
```

Note: the shim's only job is the deprecation breadcrumb + forward. It does NOT
re-implement the old `--base-dir/--lora-dir` interface (that interface was dead
code anyway). The real packaging now lives behind `build_ai_eng.sh publish`,
which sources its inputs from `build/` produced by `build_ai_eng.sh build`.

---

## 2. Gap list — unique behavior to ADD to build_ai_eng

Everything `package_ai_eng.sh` did that `build_ai_eng` does NOT yet do. Each
lands in `build_ai_eng.py` (the shell wrapper is unchanged except the publish
log lines). All additions execute inside `_run_publish()` (or helpers it calls)
so they sit behind the existing `--yes-i-have-read-bench` + `--license` +
interactive-yes gates and the HF-auth check.

| # | Unique scaffold behavior | Where it lands in build_ai_eng | Notes |
|---|---|---|---|
| G1 | **Emit NOTICE beside the GGUF.** Copy repo-root `NOTICE` into `build/` next to the produced `*.gguf` (fallback to a minimal inline NOTICE only if repo NOTICE is missing). | New helper `emit_notice_beside_gguf(build_dir, gguf_path)`, called from `_run_publish()` before the gate print. | Prefer copying the repo NOTICE verbatim (it is the authoritative Apache-2.0 attribution); inline fallback mirrors the scaffold's. |
| G2 | **Print the GGUF sha256 for pyproject pinning, with explicit guidance.** Print `sha256: <digest>` and the instruction to set `ai_eng_sha256` in `pyproject.toml [tool.arail.models]` and the GitHub Release body. | Extend the existing `gguf_sha = sha256_file(...)` block in `_run_publish()` to print the pinning guidance, not just the truncated `[:16]`. | The digest is already computed; today it is only printed truncated and stuffed in PUBLISHED.json. Print full digest + the pyproject key name. |
| G3 | **Print HF / GitHub-release / CDN upload commands as manual `# TODO` blocks**, aligned to `check_ai_eng_artifact.sh` env vars and pyproject keys (`ai_eng_hf_repo`, `ai_eng_quant`, `ai_eng_gh_url`, `ai_eng_cdn_url`, `ai_eng_sha256`). | New helper `print_upload_instructions(gguf_path, sha256, license_id, quant)` called from `_run_publish()` after the gate is passed. | Commands are PRINTED, never executed (preserves no-credentials / no-auto-upload safety). Repo names/URLs use the same placeholders as pyproject so copy-paste lines up. |
| G4 | **Derive a quant-tagged GGUF filename** (`ai-eng-1.5b-<QUANT>.gguf`) so the upload commands and `check_ai_eng_artifact.sh`'s `GGUF_FILE="ai-eng-1.5b-${QUANT}.gguf"` agree. | Add `--quant` (default `Q4_K_M`) to `_parse_args()` and the shell wrapper's flag pass-through; use it in G3's printed commands and (optionally) when naming the published artifact. | `build_ai_eng` currently names GGUFs `ai-eng-1.5b-v2.1.{f16,bf16}.gguf` (outtype-tagged, internal). The PUBLISHED/upload name must be the quant-tagged name the setup ladder + check script expect. Keep the internal build name; map to the published name in publish. |
| G5 | **Quantise step (optional).** The scaffold ran `llama-quantize f16 → Q4_K_M`. `build_ai_eng` converts to `f16`/`bf16` only. | If a quantised artifact is in scope, add an optional quantise step in `convert_to_gguf` gated by `--quant` (skip when quant in {f16,bf16}). Otherwise: print the `llama-quantize` command in G3 as a manual TODO. | RECOMMENDATION: defer real quantisation to a printed TODO (G3) for this sprint — it is heavy, hardware-touching, and out of the consolidation's safety-critical path. File as tech debt (§6). The builder must NOT add an un-OOM-guarded quantise call. |

Do NOT lose (must remain intact after edits): OOM/disk pre-checks
(`check_free_ram_gb`, `check_free_disk_gb`, `check_portal_not_running`), bench
gating + exit codes (10/11/20/21/30/40/50/60/70), sentinel idempotency,
HF-token sanitisation (`sanitize_log_line`, `_verify_no_token_in_config`), the
no-credentials / no-invented-weights / fail-nonzero-on-missing-inputs
properties, and the fail-closed sha256→pyproject workflow (the printed digest
is the input to the setup ladder's fail-closed mirror check).

---

## 3. Publish-model reconciliation (the critical question)

### Before (OLD model, currently in `_run_publish`, lines ~858-886)

```
=== PUBLISH GATE ===
Destinations:
  1. HF: qukaizen/qkz-opus4.7-aieng-1.5b-v2.1        (safetensors)
  2. HF: qukaizen/qkz-opus4.7-aieng-1.5b-v2.1-gguf   (GGUF)
  3. Ollama: qukaizen/ai-eng:1.5b                    ← ollama.ai REGISTRY TAG
```
`PUBLISHED.json` records `"ollama": "qukaizen/ai-eng:1.5b"` and two HF repos.
This is the pre-reframe distribution model. The `ollama.ai` registry tag is the
exact thing the reframe abandoned (ARCHITECTURE.md: `qukaizen/ai-eng:3b` ollama
tag confirmed 404; the self-host decision exists to *avoid* the ollama.ai
namespace). `ollama_create`/`ollama_smoke` also default `tag="qukaizen/ai-eng:1.5b"`.

### After (self-hosted model, aligned to the reframe)

The canonical distribution is **a self-hosted GGUF**:

- **Primary:** HF GGUF repo `ai_eng_hf_repo` (default placeholder
  `qukaizen/ai-eng-1.5b-gguf`), pulled at setup via
  `ollama pull hf.co/<repo>:<quant>` (Ollama verifies HF layer digests).
- **Mirror:** GitHub Release asset `ai_eng_gh_url` (sha256-verified HTTPS
  download + local `ollama create`).
- **Optional tertiary:** CDN `ai_eng_cdn_url`.
- **Pin:** `ai_eng_sha256` in `pyproject.toml`, verified fail-closed by the
  setup ladder.

`_run_publish` must therefore:

1. Locate the produced GGUF in `build/`, compute its full sha256 (already done).
2. **G1** Emit NOTICE beside the GGUF.
3. **Drop the ollama.ai registry tag entirely** from the gate text and from
   `PUBLISHED.json`. The local `ollama_create` tag (`qukaizen/ai-eng:1.5b`) used
   during *build/smoke* is fine to keep as a **local-only** tag — it is not a
   push target — but it MUST NOT appear in publish as a distribution
   destination. Recommendation: rename the local create tag to a neutral local
   name (e.g. `ai-eng-build-smoke`) OR leave it but add a comment that it is
   local-only and never pushed. Minimum required change: remove line
   `print("  3. Ollama: qukaizen/ai-eng:1.5b")` and the `"ollama": …` key in
   PUBLISHED.json.
4. **G3** Print the self-hosted upload commands (HF GGUF repo, GitHub Release,
   optional CDN) — manual TODO blocks, aligned to pyproject keys + check script.
5. **G2** Print the full sha256 + pyproject-pinning guidance.
6. Rewrite `PUBLISHED.json` to the self-hosted shape:

```json
{
  "hf_gguf_repo": "qukaizen/ai-eng-1.5b-gguf",
  "gh_release_url": "https://github.com/qukaizen/arail/releases/download/ai-eng-1.5b/ai-eng-1.5b-Q4_K_M.gguf",
  "cdn_url": "",
  "gguf_file": "ai-eng-1.5b-Q4_K_M.gguf",
  "gguf_sha256": "<digest>",
  "quant": "Q4_K_M",
  "license": "Apache-2.0",
  "status": "ready-to-upload"
}
```

The existing two-HF-repo safetensors/GGUF split may stay as an *optional* note
(safetensors repo is a reasonable companion), but the GGUF repo is the
canonical pull target and must be listed first; the ollama.ai registry tag is
removed. Keep the `--yes-i-have-read-bench`, `--license`, interactive-yes, and
HF-auth gates exactly as-is.

---

## 4. Per-file edit list

| File | Change | Why |
|---|---|---|
| `scripts/package_ai_eng.sh` | Replace entire body with the deprecation shim (§1). | Retire scaffold; keep old name working; kill duplicated un-guarded inline merge. |
| `scripts/build_ai_eng.py` | (a) Add `--quant` arg (default `Q4_K_M`) [G4]. (b) Rewrite `_run_publish` per §3: remove ollama.ai registry destination, add `emit_notice_beside_gguf` [G1], full-sha256 + pyproject-pinning print [G2], `print_upload_instructions` [G3], self-hosted `PUBLISHED.json` [§3.6]. (c) Add helpers `emit_notice_beside_gguf`, `print_upload_instructions`. (d) Mark local `ollama_create`/`ollama_smoke` tag as local-only (comment or rename). | Fold scaffold value in; reconcile distribution model; preserve all safety. |
| `scripts/build_ai_eng.sh` | Pass `--quant` through (add to flag parse + `BASE_ARGS`). Update the publish-phase log line `"Phase 2: publish to HF + Ollama"` → `"Phase 2: publish to self-hosted HF GGUF + GitHub Release mirror"`. | Wrapper must expose the new flag; log must not claim an ollama.ai push. |
| `scripts/setup.sh` (line 834) | Change `"until a real digest is pinned (run scripts/package_ai_eng.sh, then"` → `"…(run scripts/build_ai_eng.sh publish, then"`. | Point operators at the canonical pipeline, not the retired scaffold. |
| `scripts/check_ai_eng_artifact.sh` (line 52) | Change `"…until the user runs scripts/package_ai_eng.sh and uploads."` → `"…until the user runs scripts/build_ai_eng.sh publish and uploads."` | Same. |
| `pyproject.toml` (lines 136, 143) | `"fill in after running scripts/package_ai_eng.sh"` → `"…build_ai_eng.sh publish"`; `"published by package_ai_eng.sh."` → `"published by build_ai_eng.sh publish."` | Comment accuracy. |
| `NOTICE` (lines 42-44) | `"scripts/package_ai_eng.sh script emits a copy of this NOTICE… (see package_ai_eng.sh)"` → reference `build_ai_eng.sh publish`. | The publish path now emits the NOTICE. |
| `CHANGELOG.md` (lines 33, 49, 86) | Update the package_ai_eng.sh mentions: note consolidation into build_ai_eng.sh (retired-as-shim). Keep historical accuracy — append a consolidation entry rather than rewriting the shipped PR #75 entry. | Honest history. |
| `sprints/2026-05-30-model-hosting-reframe/ARCHITECTURE.md` | Do NOT rewrite (it is the historical sprint record). The consolidation is documented HERE in CONSOLIDATION.md; add a one-line pointer at the top of ARCHITECTURE.md's deliverable §5 noting the scaffold was consolidated post-sprint into build_ai_eng (see CONSOLIDATION.md). | Preserve sprint artifact integrity; leave a forward pointer. |

References intentionally NOT edited: the sprint's BUILD_LOG.md, TEST_REPORT.md,
REVIEW.md (historical records of what was built — do not rewrite history).

---

## 5. Failure modes + test strategy

All tests stay OOM-safe: dry-run / mock / source-string assertions only. No real
builds, pulls, merges, quantisation, or model loads.

### Failure modes

| Failure | Detection | Recovery |
|---|---|---|
| Retired scaffold silently reappears with real packaging logic | Regression guard test (below) asserts the script is a thin shim that forwards to build_ai_eng.sh and contains no merge/convert/quantise commands | BLOCK in review until reverted to shim |
| Publish still advertises an ollama.ai registry tag | Test asserts `qukaizen/ai-eng:1.5b` does not appear as a publish *destination* and PUBLISHED.json has no `ollama` registry key | Build fails test; reconcile per §3 |
| Upload commands drift from check script / pyproject keys | Test asserts the publish output (dry-run / source) references `ai_eng_hf_repo`-style repo and the `ai-eng-1.5b-${QUANT}.gguf` filename that `check_ai_eng_artifact.sh` derives | Fix command strings |
| NOTICE not emitted beside artifact | Unit test: `emit_notice_beside_gguf` in a tmp build dir writes a NOTICE file | Add helper |
| sha256 not printed full / no pyproject guidance | Unit test on `_run_publish` dry path or `print_upload_instructions` output contains full 64-hex digest + `ai_eng_sha256` | Fix print |
| Safety regression (OOM/disk/sanitise gates removed) | Existing dry-run tests + a guard asserting `check_free_ram_gb`/`sanitize_log_line` still present | BLOCK |
| `--quant` breaks wrapper flag parsing | `bash -n` syntax test + dry-run end-to-end | Fix wrapper |

### Existing tests and required changes

- **`tests/test_model_hosting_reframe_qa.py`** (lines 233-295) — four tests key
  off `package_ai_eng.sh` as a full scaffold:
  - `test_package_script_embeds_no_credentials` — KEEP; passes against shim
    (still must contain no tokens). Drop the `assert "huggingface-cli login"`/
    `"gh auth login"` lines (the shim no longer documents login) OR retarget
    them to `build_ai_eng.py` output. **Retarget to build_ai_eng.py.**
  - `test_package_script_exits_nonzero_on_missing_inputs` — REWRITE. The shim
    forwards to `build_ai_eng.sh publish` with no args → exits 70 (publish
    refused, no `--yes-i-have-read-bench`). Assert nonzero exit + the
    deprecation breadcrumb on stderr. No real packaging runs.
  - `test_package_script_weight_download_is_only_documentation` — REWRITE as a
    guard that the shim contains no `huggingface-cli download`, no merge, no
    convert (it just forwards). Move the "no auto weight download" assertion to
    target `build_ai_eng.py` (which never auto-downloads base weights either).
  - `test_package_script_passes_bash_syntax` — KEEP (shim must pass `bash -n`).
  - Add **new** tests: publish output has no ollama.ai registry destination;
    publish output / `print_upload_instructions` references the quant-tagged
    GGUF filename + `ai_eng_hf_repo`; NOTICE-emit helper writes a file.

- **`tests/test_build_ai_eng_dry_run.py`** — currently covers download/
  candidate/convert/modelfile/ollama-create/sentinel/OOM-disk in dry-run.
  ADD: a `_run_publish` dry-path or helper-level test for G1/G2/G3 (NOTICE
  emitted, full sha256 printed, upload commands present, PUBLISHED.json
  self-hosted shape). Use the existing `build_dir`/`adapter_dir` fixtures; mock
  `huggingface-cli whoami` and `input()` so the gate is exercised without a real
  push. Keep dry-run so no model load happens.

- **`tests/test_modelfile_checksums.py`** — no package_ai_eng reference; no
  change required unless `--quant` changes Modelfile naming (it does not — the
  Modelfile generator is untouched).

- **`tests/setup_ladder/`** — `conftest.py` / `test_setup_ladder.py` exercise the
  setup fetch ladder via the timeout shim with mocked `ollama`/`curl`; they do
  not reference package_ai_eng. The setup.sh skip-message edit (line 783 area)
  and line-834 edit must keep the ladder tests green — re-run them. If any
  asserts on the exact line-834 string, update that assertion.

### Regression guard (new, required)

Add `test_package_ai_eng_is_retired_shim` to
`tests/test_model_hosting_reframe_qa.py`:

```python
def test_package_ai_eng_is_retired_shim():
    s = (REPO_ROOT / "scripts/package_ai_eng.sh").read_text()
    assert "DEPRECATED" in s
    assert "build_ai_eng.sh" in s and "exec" in s
    # The scaffold's real packaging logic must NOT reappear here.
    for forbidden in ("merge_and_unload", "convert_hf_to_gguf",
                      "llama-quantize", "PeftModel"):
        assert forbidden not in s, f"retired scaffold logic reappeared: {forbidden}"
    assert len(s.splitlines()) < 20, "shim should stay thin"
```

This is the "can't silently reappear" guard the spec requires.

---

## 6. Tech-debt note

**Repaid:**
- Removes a duplicated, un-OOM-guarded, un-sanitised inline LoRA merge (the
  scaffold's dead `--merge-only` fallthrough). One merge path, guarded.
- Single source of truth for the distribution model — eliminates the ollama.ai
  vs self-hosted contradiction between publish and setup.

**Added:**
- `--quant` is threaded but real quantisation is deferred to a printed manual
  TODO (G5). The `build_ai_eng` convert path still emits f16/bf16, not the
  Q4_K_M the setup ladder ultimately pulls. **Follow-up ticket:** add an
  OOM-guarded, sentinel-idempotent `llama-quantize` step to `convert_to_gguf`
  (or a dedicated `quantize` subcommand) so the produced artifact filename and
  quant match `ai_eng_quant` end-to-end without a manual step.
- The local build/smoke `ollama create` tag (`qukaizen/ai-eng:1.5b`) is now a
  local-only artifact whose name collides with the old registry tag naming.
  Minor confusion risk; comment added. Optional cleanup: rename to
  `ai-eng-build-smoke`.

**Net:** negative (debt reduced). One residual follow-up (real quantise step).

---

## Recommended implementation order

1. `build_ai_eng.py`: add `--quant`, helpers `emit_notice_beside_gguf` +
   `print_upload_instructions`, rewrite `_run_publish` per §3 (remove ollama.ai
   destination, self-hosted PUBLISHED.json, NOTICE emit, full-sha256 print).
2. `build_ai_eng.sh`: thread `--quant`, fix publish log line.
3. Replace `package_ai_eng.sh` with the shim.
4. Fix the textual references: `setup.sh:834`, `check_ai_eng_artifact.sh:52`,
   `pyproject.toml:136,143`, `NOTICE:42-44`, `CHANGELOG.md`.
5. Update + add tests (§5), including the retirement regression guard. Run the
   whole suite + `setup_ladder` dry/mocked.
6. Add the one-line ARCHITECTURE.md forward pointer.
