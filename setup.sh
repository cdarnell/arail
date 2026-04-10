#!/usr/bin/env bash
# =============================================================================
# OGLab — Setup Script
# Detects your platform, installs dependencies, downloads a starter model.
# =============================================================================
set -euo pipefail

BOLD="\033[1m"
GREEN="\033[0;32m"
YELLOW="\033[0;33m"
RED="\033[0;31m"
RESET="\033[0m"

info()  { echo -e "${GREEN}[oglab]${RESET} $*"; }
warn()  { echo -e "${YELLOW}[oglab]${RESET} $*"; }
error() { echo -e "${RED}[oglab]${RESET} $*"; exit 1; }

# -----------------------------------------------------------------------------
# Detect OS / platform
# -----------------------------------------------------------------------------
detect_platform() {
    local os kernel
    os="$(uname -s)"
    kernel="$(uname -r)"

    case "$os" in
        Darwin)
            PLATFORM="macos"
            # Check for Apple Silicon
            if [[ "$(uname -m)" == "arm64" ]]; then
                ACCEL="mlx"
            else
                ACCEL="cpu"
            fi
            ;;
        Linux)
            # Check if running inside WSL
            if grep -qiE '(microsoft|wsl)' /proc/version 2>/dev/null; then
                PLATFORM="wsl"
            # Check for Gentoo
            elif [[ -f /etc/gentoo-release ]]; then
                PLATFORM="gentoo"
            else
                PLATFORM="linux"
            fi

            # GPU detection
            if command -v nvidia-smi &>/dev/null && nvidia-smi &>/dev/null; then
                ACCEL="cuda"
            else
                ACCEL="cpu"
            fi
            ;;
        *)
            error "Unsupported OS: $os  (Linux, macOS, or WSL required)"
            ;;
    esac

    info "Platform: ${BOLD}${PLATFORM}${RESET}  |  Accelerator: ${BOLD}${ACCEL}${RESET}"
}

# -----------------------------------------------------------------------------
# Python environment
# -----------------------------------------------------------------------------
ensure_python() {
    if ! command -v python3 &>/dev/null; then
        case "$PLATFORM" in
            gentoo)  error "Install Python: emerge -av dev-lang/python" ;;
            macos)   error "Install Python: brew install python@3.11" ;;
            *)       error "Install Python 3.10+ and re-run." ;;
        esac
    fi

    local pyver
    pyver="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
    info "Python $pyver found"

    if [[ ! -d ".venv" ]]; then
        info "Creating virtual environment…"
        python3 -m venv .venv
    fi
    # shellcheck disable=SC1091
    source .venv/bin/activate
    pip install --upgrade pip -q
}

# -----------------------------------------------------------------------------
# Install core Python deps
# -----------------------------------------------------------------------------
install_core_deps() {
    info "Installing core dependencies…"
    pip install -q -r requirements.txt
}

# -----------------------------------------------------------------------------
# Platform-specific accelerator deps
# -----------------------------------------------------------------------------
install_accel_deps() {
    case "$ACCEL" in
        mlx)
            info "Installing MLX (Apple Silicon)…"
            pip install -q mlx mlx-lm
            ;;
        cuda)
            info "Installing CUDA / vLLM…"
            pip install -q vllm torch
            ;;
        cpu)
            warn "No GPU detected — installing llama-cpp-python for CPU inference."
            pip install -q llama-cpp-python
            ;;
    esac
}

# -----------------------------------------------------------------------------
# Gentoo-specific guidance
# -----------------------------------------------------------------------------
gentoo_notes() {
    if [[ "$PLATFORM" != "gentoo" ]]; then return; fi

    echo ""
    info "${BOLD}Gentoo-specific notes${RESET}"
    echo "  Recommended USE flags for CUDA:"
    echo "    echo 'dev-util/nvidia-cuda-toolkit -profiler' >> /etc/portage/package.use/cuda"
    echo ""
    echo "  Key packages:"
    echo "    emerge -av dev-lang/python dev-python/pip sci-libs/pytorch"
    echo "    emerge -av dev-util/nvidia-cuda-toolkit  # if Nvidia GPU"
    echo ""
    echo "  Kernel: enable CONFIG_DRM, CONFIG_DRM_NOUVEAU or nvidia-drivers."
    echo "  See docs/GENTOO.md for full walkthrough."
    echo ""
}

# -----------------------------------------------------------------------------
# WSL-specific guidance
# -----------------------------------------------------------------------------
wsl_notes() {
    if [[ "$PLATFORM" != "wsl" ]]; then return; fi

    echo ""
    info "${BOLD}WSL notes${RESET}"
    echo "  For Nvidia GPU passthrough, ensure:"
    echo "    1. Windows Nvidia driver >= 525.x installed on the HOST"
    echo "    2. WSL2 (not WSL1): wsl --set-version <distro> 2"
    echo "    3. nvidia-smi works inside WSL"
    echo "  See docs/WSL.md for details."
    echo ""
}

# -----------------------------------------------------------------------------
# .env file
# -----------------------------------------------------------------------------
setup_env() {
    if [[ ! -f .env ]]; then
        cp .env.example .env
        # Patch detected backend
        case "$ACCEL" in
            mlx)  sed -i.bak 's/^MODEL_BACKEND=auto/MODEL_BACKEND=mlx/' .env ;;
            cuda) sed -i.bak 's/^MODEL_BACKEND=auto/MODEL_BACKEND=cuda/' .env ;;
            cpu)  sed -i.bak 's/^MODEL_BACKEND=auto/MODEL_BACKEND=cpu/' .env ;;
        esac
        rm -f .env.bak
        info ".env created with MODEL_BACKEND=${ACCEL}"
    else
        info ".env already exists — skipping."
    fi
}

# -----------------------------------------------------------------------------
# Download starter model (airgapped prep)
# -----------------------------------------------------------------------------
download_model() {
    local model_dir="./models"
    mkdir -p "$model_dir"

    if [[ "$ACCEL" == "mlx" ]]; then
        local model="mlx-community/Mistral-7B-Instruct-v0.3-4bit"
        if [[ -d "${model_dir}/Mistral-7B-Instruct-v0.3-4bit" ]]; then
            info "Model already downloaded."
        else
            info "Downloading MLX model: $model (this takes a few minutes)…"
            python3 -c "from huggingface_hub import snapshot_download; snapshot_download('${model}', local_dir='${model_dir}/Mistral-7B-Instruct-v0.3-4bit')"
        fi
    elif [[ "$ACCEL" == "cuda" ]]; then
        warn "For CUDA, download a model with:"
        echo "  python3 -c \"from huggingface_hub import snapshot_download; snapshot_download('mistralai/Mistral-7B-Instruct-v0.2', local_dir='./models/Mistral-7B')\""
    else
        warn "For CPU, download a GGUF model with:"
        echo "  huggingface-cli download TheBloke/Mistral-7B-Instruct-v0.2-GGUF mistral-7b-instruct-v0.2.Q4_K_M.gguf --local-dir ./models"
    fi
}

# -----------------------------------------------------------------------------
# Verify
# -----------------------------------------------------------------------------
verify() {
    info "Running smoke test…"
    python3 -c "from oglab.router import ModelRouter; print('✅ oglab package imports OK')" 2>/dev/null \
        && info "Setup complete!" \
        || warn "Import test failed — you may need to: pip install -e ."
}

# =============================================================================
# Main
# =============================================================================
main() {
    echo ""
    echo -e "${BOLD}🧪 OGLab — AI Lab Blueprint Setup${RESET}"
    echo "============================================="
    echo ""

    detect_platform
    ensure_python
    install_core_deps
    install_accel_deps
    setup_env
    gentoo_notes
    wsl_notes
    download_model

    echo ""
    verify
    echo ""
    info "Next steps:"
    echo "  source .venv/bin/activate"
    echo "  python3 examples/peanut_farmer/run.py"
    echo ""
}

main "$@"
