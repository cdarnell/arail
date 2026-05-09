#!/usr/bin/env bash
# =============================================================================
# upgrade.sh — switch install tier (min / max) without re-running setup.
#
# Usage:
#   ./arailctl upgrade max
#   ./arailctl upgrade min   (downgrade — does not uninstall packages, just
#                          hides the extra tabs until you upgrade again)
#
# The 'med' tier from the earlier three-tier blueprint is retired. Passing
# it rolls forward to 'max' with a warning.
# =============================================================================
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

GREEN="\033[0;32m"; YELLOW="\033[0;33m"; RED="\033[0;31m"; BOLD="\033[1m"; RESET="\033[0m"
info()  { echo -e "${GREEN}[arail]${RESET} $*"; }
warn()  { echo -e "${YELLOW}[arail]${RESET} $*"; }
die()   { echo -e "${RED}[arail]${RESET} $*" >&2; exit 1; }

RAW="${1:-}"
case "$RAW" in
    min|max) TIER="$RAW" ;;
    med)     warn "Tier 'med' retired — rolling forward to 'max' (it owned a subset of max)."
             TIER="max" ;;
    "")      die "usage: ./arailctl upgrade <min|max> [--with-coder]" ;;
    *)       die "unknown tier '$RAW' — valid: min | max" ;;
esac

# Sprint 2: --with-coder downloads Qwen2.5-Coder-3B to lab/models/ so the
# user can point opencode at it. Only useful with max tier.
WITH_CODER="${ARAIL_WITH_CODER:-0}"
for arg in "$@"; do
    case "$arg" in
        --with-coder) WITH_CODER=1 ;;
        --no-coder)   WITH_CODER=0 ;;
        *) ;;
    esac
done

[[ -d .venv ]] || die "no .venv — run ./arailctl setup first"
# shellcheck disable=SC1091
source .venv/bin/activate

info "Switching install tier to ${BOLD}${TIER}${RESET}…"

# pip is idempotent — already-installed packages are no-ops. For downgrades
# we intentionally do not uninstall; the tabs just hide in the nav and the
# operator can upgrade back later without re-downloading wheels.
# Both tiers now declare airllm, so we always re-run pip install to make
# sure the deep backend is present.
pip install -q -e ".[${TIER}]" || die "pip install failed for tier ${TIER}"

# Persist tier + tier-sized AIRLLM_MODEL default to .env. Reads the
# canonical model names from pyproject.toml so this stays in lockstep
# with [tool.arail.models].
python3 - "$TIER" <<'PY'
import pathlib, sys
try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

tier = sys.argv[1]
data = tomllib.loads(pathlib.Path("pyproject.toml").read_text())
models = data.get("tool", {}).get("arail", {}).get("models", {})
tier_model_key = f"airllm_{tier}"
airllm_model = models.get(tier_model_key) or models.get("airllm", "")

p = pathlib.Path(".env")
lines = p.read_text().splitlines() if p.exists() else []

def upsert(out, key, value):
    seen = False
    new = []
    for line in out:
        if line.lstrip("# ").startswith(f"{key}="):
            new.append(f"{key}={value}")
            seen = True
        else:
            new.append(line)
    if not seen:
        if new and new[-1] != "":
            new.append("")
        new.append(f"{key}={value}")
    return new

lines = upsert(lines, "LAB_TIER", tier)
if airllm_model:
    lines = upsert(lines, "AIRLLM_MODEL", airllm_model)
p.write_text("\n".join(lines) + "\n")
print(f"LAB_TIER={tier}")
if airllm_model:
    print(f"AIRLLM_MODEL={airllm_model}")
PY

info "Tier is now ${BOLD}${TIER}${RESET}. Restart the lab to apply:"
echo ""
echo "    ./arailctl restart"
echo ""

# Download coder model if requested (mirrors setup.sh --with-coder, Sprint 2)
if [[ "$WITH_CODER" == "1" ]]; then
    if [[ "$TIER" != "max" ]]; then
        warn "--with-coder: tier is '$TIER', not 'max'. opencode Workbench is max-only."
        warn "The model will be available when you upgrade to max later."
    fi
    # Detect ACCEL the same way setup.sh does: Apple Silicon → mlx, else cpu.
    ACCEL="cpu"
    if [[ "$(uname -s)" == "Darwin" ]] && python3 -c "import mlx" 2>/dev/null; then
        ACCEL="mlx"
    fi
    # Source setup.sh functions for reuse.
    CODER_MLX_ID="mlx-community/Qwen2.5-Coder-3B-Instruct-4bit"
    CODER_HF_ID="Qwen/Qwen2.5-Coder-3B-Instruct"
    CODER_GGUF_ID="Qwen/Qwen2.5-Coder-3B-Instruct-GGUF"
    MODEL_DIR="lab/models"
    mkdir -p "$MODEL_DIR"
    info "Downloading Qwen2.5-Coder-3B-Instruct (${ACCEL})…"
    if [[ "$ACCEL" == "mlx" ]]; then
        TARGET="${MODEL_DIR}/Qwen2.5-Coder-3B-Instruct-4bit"
        [[ -d "$TARGET" ]] && { info "Already downloaded."; } || \
            python3 -c "from huggingface_hub import snapshot_download; snapshot_download('${CODER_MLX_ID}', local_dir='${TARGET}')" \
                || warn "Coder model download failed — see above. Continuing."
    else
        TARGET="${MODEL_DIR}/Qwen2.5-Coder-3B-Instruct-GGUF"
        [[ -d "$TARGET" ]] && { info "Already downloaded."; } || \
            { if command -v huggingface-cli >/dev/null 2>&1; then
                huggingface-cli download "$CODER_GGUF_ID" --include '*Q4_K_M*' \
                    --local-dir "$TARGET" --local-dir-use-symlinks False || warn "Download failed."
              else
                python3 -c "from huggingface_hub import snapshot_download; snapshot_download('${CODER_GGUF_ID}', local_dir='${TARGET}', allow_patterns=['*Q4_K_M*'])" \
                    || warn "Download failed."
              fi; }
    fi
    info "Coder model ready at ${TARGET}. In the lab: Chat → pick Qwen2.5-Coder-3B → start opencode from Workbench."
fi
