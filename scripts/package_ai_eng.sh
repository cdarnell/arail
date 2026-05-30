#!/usr/bin/env bash
# package_ai_eng.sh — developer-side scaffold: merge LoRA → GGUF → upload.
#
# PURPOSE
#   Documents and (where tools are present) automates the steps to:
#     (a) merge QuKaiZen's LoRA into the qwen2.5:3b base model
#     (b) convert the merged model to GGUF at a chosen quantisation
#     (c) emit a Modelfile and NOTICE next to the GGUF
#     (d) print the sha256 of the produced GGUF
#     (e) print exact upload commands for HuggingFace / GitHub / CDN
#
#   Upload and credential steps are explicit "# TODO(manual):" blocks — the
#   user uncomments and runs them. This script NEVER embeds credentials and
#   NEVER invents or downloads arbitrary weights.
#
# USAGE
#   scripts/package_ai_eng.sh \
#     --base-dir   /path/to/qwen2.5-3b-instruct  \  # required: merged base weights
#     --lora-dir   /path/to/qukaizen_lora          \  # required: LoRA adapter dir
#     --out-dir    /path/to/output                 \  # default: ./lab/models/ai-eng-pkg
#     --quant      Q4_K_M                          \  # default: Q4_K_M
#     --llama-cpp  /path/to/llama.cpp              \  # default: ~/llama.cpp
#
# If --base-dir or --lora-dir are missing, the script prints the manual steps
# and exits nonzero (it does NOT download base weights on your behalf).
#
# REQUIREMENTS (install before running)
#   pip install peft transformers torch  # for LoRA merge (step 1)
#   git clone https://github.com/ggml-org/llama.cpp ~/llama.cpp  # for GGUF convert (step 2)
#   pip install huggingface-hub  # for huggingface-cli upload (step 4 — manual)
#   gh (GitHub CLI)              # for gh release upload (step 4 — manual)
#
# SECURITY NOTE
#   This script contains no HuggingFace tokens, GitHub tokens, or other
#   credentials. Run `huggingface-cli login` and `gh auth login` yourself
#   before executing the upload TODO steps.
#
# ATTRIBUTION NOTE
#   The produced GGUF is derived from Qwen/Qwen2.5-3B-Instruct (Alibaba Cloud).
#   It is subject to the Qwen Research License Agreement. This script emits a
#   NOTICE file next to the artifact as a reminder. You MUST include that
#   NOTICE in any redistribution (HF model card, GitHub release, CDN, etc.).
#   See the repo-root NOTICE file for the full attribution text.

set -euo pipefail

# ── Argument parsing ───────────────────────────────────────────────────────────
BASE_DIR=""
LORA_DIR=""
OUT_DIR="./lab/models/ai-eng-pkg"
QUANT="Q4_K_M"
LLAMA_CPP_DIR="${HOME}/llama.cpp"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --base-dir)  BASE_DIR="$2"; shift 2 ;;
        --lora-dir)  LORA_DIR="$2"; shift 2 ;;
        --out-dir)   OUT_DIR="$2";  shift 2 ;;
        --quant)     QUANT="$2";    shift 2 ;;
        --llama-cpp) LLAMA_CPP_DIR="$2"; shift 2 ;;
        *)
            echo "Unknown argument: $1" >&2
            echo "Usage: $0 --base-dir <path> --lora-dir <path> [--out-dir <path>] [--quant Q4_K_M] [--llama-cpp <path>]" >&2
            exit 1
            ;;
    esac
done

# ── Validate required inputs ─────────────────────────────────────────────────
MISSING=0

if [[ -z "$BASE_DIR" ]]; then
    echo "ERROR: --base-dir is required (path to the qwen2.5:3b base model weights)." >&2
    MISSING=1
elif [[ ! -d "$BASE_DIR" ]]; then
    echo "ERROR: --base-dir does not exist: ${BASE_DIR}" >&2
    MISSING=1
fi

if [[ -z "$LORA_DIR" ]]; then
    echo "ERROR: --lora-dir is required (path to the QuKaiZen LoRA adapter)." >&2
    MISSING=1
elif [[ ! -d "$LORA_DIR" ]]; then
    echo "ERROR: --lora-dir does not exist: ${LORA_DIR}" >&2
    MISSING=1
fi

if [[ "$MISSING" -eq 1 ]]; then
    cat >&2 <<'MANUAL'

Manual steps to produce the ai-eng GGUF:

  1. Obtain the base model weights:
       huggingface-cli download Qwen/Qwen2.5-3B-Instruct \
         --local-dir ~/ai-eng-base/qwen2.5-3b-instruct

  2. Obtain the QuKaiZen LoRA (internal; produced by Nucleus pipeline):
       # The LoRA lives in the Nucleus repo or a shared drive.
       # Contact the QuKaiZen team for the adapter checkpoint.

  3. Run this script with the real paths:
       scripts/package_ai_eng.sh \
         --base-dir ~/ai-eng-base/qwen2.5-3b-instruct \
         --lora-dir /path/to/qukaizen_lora

  4. Follow the # TODO(manual) upload steps printed by the script.

MANUAL
    exit 1
fi

mkdir -p "$OUT_DIR"
MERGED_DIR="${OUT_DIR}/merged"
GGUF_FILE="${OUT_DIR}/ai-eng-3b-${QUANT}.gguf"
NOTICE_FILE="${OUT_DIR}/NOTICE"
MODELFILE="${OUT_DIR}/Modelfile"

echo "=== ai-eng packaging scaffold ==="
echo "  Base model:  ${BASE_DIR}"
echo "  LoRA:        ${LORA_DIR}"
echo "  Output dir:  ${OUT_DIR}"
echo "  Quant:       ${QUANT}"
echo ""

# ── Step 1: Merge LoRA into base model ───────────────────────────────────────
echo "[1/4] Merging LoRA adapter into base model → ${MERGED_DIR}"
echo "      (uses scripts/build_ai_eng.py merge step, or peft merge directly)"
echo ""

if command -v python3 &>/dev/null; then
    # Prefer the repo's own merge script if it accepts a --merge-only flag.
    MERGE_SCRIPT="$(dirname "$0")/build_ai_eng.py"
    if [[ -f "$MERGE_SCRIPT" ]]; then
        python3 "$MERGE_SCRIPT" \
            --base-dir "$BASE_DIR" \
            --lora-dir "$LORA_DIR" \
            --output-dir "$MERGED_DIR" \
            --merge-only \
            || {
                echo "build_ai_eng.py merge step failed. Falling back to inline peft merge." >&2
                python3 - <<PYEOF
import sys
try:
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer
    import torch
except ImportError as e:
    print(f"Missing dependency: {e}")
    print("Install: pip install peft transformers torch")
    sys.exit(1)
print("Loading base model...")
model = AutoModelForCausalLM.from_pretrained("${BASE_DIR}", torch_dtype=torch.bfloat16)
tok   = AutoTokenizer.from_pretrained("${BASE_DIR}")
print("Applying LoRA adapter...")
model = PeftModel.from_pretrained(model, "${LORA_DIR}")
print("Merging weights...")
model = model.merge_and_unload()
print(f"Saving merged model to ${MERGED_DIR}...")
model.save_pretrained("${MERGED_DIR}")
tok.save_pretrained("${MERGED_DIR}")
print("Merge complete.")
PYEOF
            }
    else
        python3 - <<PYEOF
import sys
try:
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer
    import torch
except ImportError as e:
    print(f"Missing dependency: {e}")
    print("Install: pip install peft transformers torch")
    sys.exit(1)
print("Loading base model...")
model = AutoModelForCausalLM.from_pretrained("${BASE_DIR}", torch_dtype=torch.bfloat16)
tok   = AutoTokenizer.from_pretrained("${BASE_DIR}")
print("Applying LoRA adapter...")
model = PeftModel.from_pretrained(model, "${LORA_DIR}")
print("Merging weights...")
model = model.merge_and_unload()
print(f"Saving merged model to ${MERGED_DIR}...")
model.save_pretrained("${MERGED_DIR}")
tok.save_pretrained("${MERGED_DIR}")
print("Merge complete.")
PYEOF
    fi
else
    echo "ERROR: python3 not found. Install Python 3.10+ and try again." >&2
    exit 1
fi

# ── Step 2: Convert merged model to GGUF and quantise ────────────────────────
echo ""
echo "[2/4] Converting merged model to GGUF (${QUANT}) → ${GGUF_FILE}"

CONVERT_PY="${LLAMA_CPP_DIR}/convert_hf_to_gguf.py"
QUANTIZE_BIN="${LLAMA_CPP_DIR}/llama-quantize"

if [[ ! -f "$CONVERT_PY" ]]; then
    cat >&2 <<LCPP_ERR
ERROR: llama.cpp convert script not found at: ${CONVERT_PY}

Install llama.cpp:
  git clone https://github.com/ggml-org/llama.cpp ${LLAMA_CPP_DIR}
  cd ${LLAMA_CPP_DIR} && cmake -B build && cmake --build build --config Release -j
  # The quantize binary will be at: ${LLAMA_CPP_DIR}/build/bin/llama-quantize

Then re-run this script with --llama-cpp ${LLAMA_CPP_DIR}
LCPP_ERR
    exit 1
fi

GGUF_F16="${OUT_DIR}/ai-eng-3b-f16.gguf"
python3 "$CONVERT_PY" "$MERGED_DIR" --outfile "$GGUF_F16" --outtype f16

if [[ ! -f "$QUANTIZE_BIN" ]]; then
    # Try the build subdir
    QUANTIZE_BIN="${LLAMA_CPP_DIR}/build/bin/llama-quantize"
fi
if [[ ! -f "$QUANTIZE_BIN" ]]; then
    echo "ERROR: llama-quantize binary not found. Build llama.cpp first (see above)." >&2
    exit 1
fi

"$QUANTIZE_BIN" "$GGUF_F16" "$GGUF_FILE" "$QUANT"
rm -f "$GGUF_F16"
echo "GGUF ready: ${GGUF_FILE}"

# ── Step 3: Emit Modelfile + NOTICE ──────────────────────────────────────────
echo ""
echo "[3/4] Emitting Modelfile and NOTICE next to the GGUF"

cat > "$MODELFILE" <<MFEOF
FROM $(basename "$GGUF_FILE")

SYSTEM """You are ai-eng, ARAIL's default local assistant — a 3B Opus-4.7-derived AI engineering expert from QuKaiZen's Project Nucleus. You reason carefully, write production-grade code, and explain tradeoffs clearly. When you don't know something, say so."""

PARAMETER temperature 0.7
PARAMETER num_ctx 8192
MFEOF

echo "Modelfile written: ${MODELFILE}"

# Copy the repo-root NOTICE into the output dir so it travels with the artifact.
REPO_NOTICE="$(dirname "$0")/../NOTICE"
if [[ -f "$REPO_NOTICE" ]]; then
    cp "$REPO_NOTICE" "$NOTICE_FILE"
    echo "NOTICE written:    ${NOTICE_FILE}"
else
    cat > "$NOTICE_FILE" <<'NOTICEEOF'
NOTICE: ai-eng is derived from Qwen/Qwen2.5-3B-Instruct (Alibaba Cloud),
licensed under the Qwen Research License Agreement. See the repo-root NOTICE
file and https://huggingface.co/Qwen/Qwen2.5-3B-Instruct/blob/main/LICENSE
for the full license text. This NOTICE MUST be included in any redistribution
of the ai-eng GGUF artifact (HuggingFace model card, GitHub release, CDN).
NOTICEEOF
    echo "NOTICE written (minimal fallback): ${NOTICE_FILE}"
fi

# ── Step 4: Print sha256 + upload commands ───────────────────────────────────
echo ""
echo "[4/4] sha256 of the packaged GGUF:"
SHA256="$(sha256sum "$GGUF_FILE" | awk '{print $1}')"
echo ""
echo "  sha256: ${SHA256}"
echo ""
echo "  Next step: record this sha256 in pyproject.toml [tool.arail.models].ai_eng_sha256"
echo "  and in the GitHub Release body so downloaders can verify the artifact."
echo ""

cat <<UPLOAD_INSTRUCTIONS
══════════════════════════════════════════════════════════════════════════════
UPLOAD STEPS (manual — uncomment and run after logging in)
══════════════════════════════════════════════════════════════════════════════

# 1. Update pyproject.toml with the real sha256 and repo values:
#      ai_eng_sha256  = "${SHA256}"
#      ai_eng_hf_repo = "qukaizen/ai-eng-3b-gguf"    # set your real HF org/repo
#      ai_eng_gh_url  = "https://github.com/qukaizen/arail/releases/download/ai-eng-3b/ai-eng-3b-${QUANT}.gguf"

# 2. HuggingFace upload (primary — enables the clean single-pull path):
#
#    huggingface-cli login   # run once; stores token in ~/.cache/huggingface/
#
#    huggingface-cli upload qukaizen/ai-eng-3b-gguf \
#      ${GGUF_FILE} \
#      --repo-type model \
#      --commit-message "Add ai-eng-3b ${QUANT} GGUF (sha256: ${SHA256})"
#
#    # Also upload the Modelfile and NOTICE:
#    huggingface-cli upload qukaizen/ai-eng-3b-gguf \
#      ${MODELFILE} \
#      --repo-type model
#    huggingface-cli upload qukaizen/ai-eng-3b-gguf \
#      ${NOTICE_FILE} \
#      --repo-type model

# 3. GitHub Release mirror (fallback for HF outage / corp proxies):
#
#    gh auth login   # run once
#
#    gh release create ai-eng-3b \
#      --repo qukaizen/arail \
#      --title "ai-eng 3B GGUF (${QUANT})" \
#      --notes "sha256: ${SHA256}
#
# ai-eng is derived from Qwen/Qwen2.5-3B-Instruct (Alibaba Cloud).
# Licensed under the Qwen Research License. See NOTICE in this release."
#
#    gh release upload ai-eng-3b \
#      ${GGUF_FILE} \
#      --repo qukaizen/arail

# 4. qukaizen.com CDN (optional tertiary — set ARAIL_AI_ENG_CDN_URL in .env):
#    # Upload via your hosting provider; set the URL in pyproject.toml ai_eng_cdn_url.

# 5. After uploading, verify the artifact is live:
#    scripts/check_ai_eng_artifact.sh

# 6. Commit the updated pyproject.toml with the real sha256 + repo values.

══════════════════════════════════════════════════════════════════════════════
UPLOAD_INSTRUCTIONS

echo ""
echo "Package complete. Files in ${OUT_DIR}:"
ls -lh "$OUT_DIR"
