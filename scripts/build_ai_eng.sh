#!/usr/bin/env bash
# build_ai_eng.sh — operator-driven build pipeline for ai-eng v2.1
#
# Usage:
#   ./scripts/build_ai_eng.sh [subcommand] [flags]
#
# Subcommands:
#   build       (default) Full Phase 1: download → candidates → bench → convert → ollama create
#   bench-only  Re-run bench assuming build/mlx-fused/ and build/bf16-merged/ exist
#   convert     Convert a specific candidate to GGUF (requires --candidate a|b)
#   publish     Phase 2: HF + Ollama push (requires --yes-i-have-read-bench; INTERACTIVE)
#   clean       Remove build/ (preserves models/ai-eng/BENCH-v2.1.md)
#   dry-run     Exercise every code path without downloading or loading models
#
# Exit codes (see ARCHITECTURE.md §4.1):
#   0   success / ready to publish
#   10  both candidates failed bench gate (sprint shelves)
#   11  Candidate B regressed >3pp; Candidate A shipped (informational)
#   20  OOM pre-check tripped (free RAM below threshold)
#   21  disk pre-check tripped
#   30  HF download failed
#   40  adapter format unknown
#   50  GGUF conversion failed
#   60  ollama create failed / SYSTEM SHA drifted
#   70  publish refused (no --yes-i-have-read-bench or interactive declined)
#
# Environment variables:
#   ARAIL_BUILD_DIR            default: ./build
#   HF_TOKEN or HUGGING_FACE_HUB_TOKEN   HF auth (never echoed/logged)
#
# OOM safety: free RAM is probed (via psutil in build_ai_eng.py) before
# each heavy step. This script also refuses if the ARAIL portal is running.
# Default threshold: 16 GB free RAM; 30 GB free disk.
#
# Idempotency: sentinel files in build/.step-<name>.done gate each step.
# Pass --force to re-run all steps.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# ── Defaults ──────────────────────────────────────────────────────────────────
SUBCOMMAND="${1:-build}"
shift || true

ADAPTER_REPO="qukaizen/qkz-opus4.7-aieng-3b-v2.1-adapter"
BF16_BASE="Qwen/Qwen2.5-3B-Instruct"
MLX_BASE="mlx-community/Qwen2.5-3B-Instruct-4bit"
BENCH_PROMPTS="models/ai-eng/bench-prompts.v2.1.yaml"
LLAMA_CPP_REV="b3500"
MIN_FREE_RAM_GB="16"
MIN_FREE_DISK_GB="30"
BUILD_DIR="${ARAIL_BUILD_DIR:-./build}"
MODELFILE_PRODUCTION="models/ai-eng/Modelfile.production"
CANDIDATE=""
FORCE=""
YES_BENCH=""
LICENSE_FLAG=""
DRY_RUN=""

# ── Parse flags ───────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --adapter-repo)        ADAPTER_REPO="$2";        shift 2 ;;
    --bf16-base)           BF16_BASE="$2";           shift 2 ;;
    --mlx-base)            MLX_BASE="$2";            shift 2 ;;
    --bench-prompts)       BENCH_PROMPTS="$2";       shift 2 ;;
    --llama-cpp-rev)       LLAMA_CPP_REV="$2";       shift 2 ;;
    --min-free-ram-gb)     MIN_FREE_RAM_GB="$2";     shift 2 ;;
    --min-free-disk-gb)    MIN_FREE_DISK_GB="$2";    shift 2 ;;
    --build-dir)           BUILD_DIR="$2";           shift 2 ;;
    --candidate)           CANDIDATE="$2";           shift 2 ;;
    --force)               FORCE="--force";          shift   ;;
    --yes-i-have-read-bench) YES_BENCH="--yes-i-have-read-bench"; shift ;;
    --license)             LICENSE_FLAG="--license $2"; shift 2 ;;
    *)
      echo "ERROR: Unknown flag: $1" >&2
      echo "Run './scripts/build_ai_eng.sh --help' for usage." >&2
      exit 1
      ;;
  esac
done

# ── Helpers ───────────────────────────────────────────────────────────────────
log_info()  { echo "[build_ai_eng] INFO : $*"; }
log_warn()  { echo "[build_ai_eng] WARN : $*" >&2; }
log_error() { echo "[build_ai_eng] ERROR: $*" >&2; }

require_python() {
  if ! command -v python3 &>/dev/null; then
    log_error "python3 not found. Install Python 3.10+ and try again."
    exit 1
  fi
}

require_ollama() {
  if ! command -v ollama &>/dev/null; then
    log_warn "ollama not found — ollama create / push steps will fail."
    log_warn "Install ollama from https://ollama.com and re-run."
  fi
}

check_portal_not_running() {
  if pgrep -f "arail.portal" &>/dev/null; then
    log_error "ARAIL portal is running. Stop it before building to avoid OOM:"
    log_error "  pkill -f 'arail.portal'  OR  ./arailctl stop"
    exit 20
  fi
}

# Sanitise: never echo HF_TOKEN in any log line
sanitise_env_for_log() {
  # Called before printing any env-sensitive command
  :
}

# ── Subcommand dispatch ───────────────────────────────────────────────────────
cd "$REPO_ROOT"
require_python

PYTHON_HELPER="scripts/build_ai_eng.py"
BENCH_HELPER="scripts/bench_ai_eng.py"

BASE_ARGS=(
  "--adapter-repo" "$ADAPTER_REPO"
  "--bf16-base"    "$BF16_BASE"
  "--mlx-base"     "$MLX_BASE"
  "--bench-prompts" "$BENCH_PROMPTS"
  "--llama-cpp-rev" "$LLAMA_CPP_REV"
  "--min-free-ram-gb" "$MIN_FREE_RAM_GB"
  "--min-free-disk-gb" "$MIN_FREE_DISK_GB"
  "--build-dir"    "$BUILD_DIR"
  "--modelfile-production" "$MODELFILE_PRODUCTION"
)
[[ -n "$FORCE" ]] && BASE_ARGS+=("$FORCE")

case "$SUBCOMMAND" in

  build)
    log_info "Phase 1: full build pipeline"
    check_portal_not_running
    python3 "$PYTHON_HELPER" build "${BASE_ARGS[@]}"
    BENCH_EXIT=$?
    if [[ $BENCH_EXIT -eq 10 ]]; then
      log_error "Both candidates failed bench gate. Sprint shelved per ARCHITECTURE F6."
      log_info  "Review build/BENCH-v2.1.md for details."
      exit 10
    fi
    if [[ $BENCH_EXIT -eq 11 ]]; then
      log_warn "Candidate B regressed; Candidate A shipped (informational, exit 11)."
      exit 11
    fi
    log_info "Build complete. Review build/BENCH-v2.1.md."
    log_info "Next: ./scripts/build_ai_eng.sh publish --yes-i-have-read-bench --license Apache-2.0"
    exit "$BENCH_EXIT"
    ;;

  bench-only)
    log_info "Re-running bench only (assuming build/mlx-fused/ and build/bf16-merged/ exist)"
    python3 "$BENCH_HELPER" \
      "--candidate-a-path" "${BUILD_DIR}/mlx-fused" \
      "--candidate-b-path" "${BUILD_DIR}/bf16-merged" \
      "--prompts-file"     "$BENCH_PROMPTS" \
      "--out"              "${BUILD_DIR}/BENCH-v2.1.md"
    BENCH_EXIT=$?
    # Copy to models/ai-eng/ for commit
    if [[ $BENCH_EXIT -ne 2 ]]; then
      cp "${BUILD_DIR}/BENCH-v2.1.md" "models/ai-eng/BENCH-v2.1.md"
      log_info "Copied BENCH-v2.1.md to models/ai-eng/BENCH-v2.1.md"
    fi
    exit "$BENCH_EXIT"
    ;;

  convert)
    if [[ -z "$CANDIDATE" ]]; then
      log_error "'convert' requires --candidate a|b"
      exit 1
    fi
    log_info "Converting Candidate $CANDIDATE to GGUF"
    python3 "$PYTHON_HELPER" convert "${BASE_ARGS[@]}" --candidate "$CANDIDATE"
    ;;

  publish)
    log_info "Phase 2: publish to HF + Ollama"
    PUBLISH_ARGS=("${BASE_ARGS[@]}")
    [[ -n "$YES_BENCH" ]] && PUBLISH_ARGS+=("$YES_BENCH")
    # shellcheck disable=SC2086
    [[ -n "$LICENSE_FLAG" ]] && PUBLISH_ARGS+=($LICENSE_FLAG)
    python3 "$PYTHON_HELPER" publish "${PUBLISH_ARGS[@]}"
    PUBLISH_EXIT=$?
    if [[ $PUBLISH_EXIT -eq 70 ]]; then
      log_error "Publish refused. Pass --yes-i-have-read-bench and --license <id> after reviewing BENCH-v2.1.md."
    elif [[ $PUBLISH_EXIT -eq 30 ]]; then
      log_error "HF auth failure. Run: huggingface-cli login"
    fi
    exit "$PUBLISH_EXIT"
    ;;

  clean)
    log_info "Cleaning build/"
    # Preserve models/ai-eng/BENCH-v2.1.md (it's in repo, not in build/)
    python3 "$PYTHON_HELPER" clean "${BASE_ARGS[@]}"
    log_info "build/ cleaned. models/ai-eng/BENCH-v2.1.md preserved."
    ;;

  dry-run)
    log_info "Dry-run mode: exercising every code path without downloads or model loads"
    python3 "$PYTHON_HELPER" dry-run "${BASE_ARGS[@]}"
    DRY_EXIT=$?
    log_info "Dry-run complete (exit $DRY_EXIT)."
    # Also exercise bench --dry-run
    python3 "$BENCH_HELPER" --dry-run \
      "--out" "${BUILD_DIR}/BENCH-v2.1.md-dry"
    log_info "Bench dry-run complete."
    exit "$DRY_EXIT"
    ;;

  --help|-h|help)
    head -60 "$0" | grep '^#' | sed 's/^# \?//'
    exit 0
    ;;

  *)
    log_error "Unknown subcommand: $SUBCOMMAND"
    log_error "Valid subcommands: build bench-only convert publish clean dry-run"
    exit 1
    ;;
esac
