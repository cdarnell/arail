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

MODEL_MLX_ID="mlx-community/Qwen3-8B-4bit"
MODEL_HF_ID="Qwen/Qwen3-8B"
MODEL_GGUF_ID="Qwen/Qwen3-8B-GGUF"
AIRLLM_MODEL_ID="Qwen/Qwen3-8B"
IDE_DEFAULT_PASSWORD='REDACTED'

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
    pip install -q -e ".[dev]"
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

        case "$ACCEL" in
            mlx)  sed -i.bak "s|^MODEL_NAME=.*|MODEL_NAME=${MODEL_MLX_ID}|" .env ;;
            cuda) sed -i.bak "s|^MODEL_NAME=.*|MODEL_NAME=${MODEL_HF_ID}|" .env ;;
            cpu)  sed -i.bak "s|^MODEL_NAME=.*|MODEL_NAME=${MODEL_GGUF_ID}|" .env ;;
        esac

        sed -i.bak "s|^AIRLLM_MODEL=.*|AIRLLM_MODEL=${AIRLLM_MODEL_ID}|" .env

        # LAB_PKM defaults to ./lab/pkm via oglab/config.py; no need to set here.
        :

        rm -f .env.bak
        info ".env created with MODEL_BACKEND=${ACCEL}"
    else
        info ".env already exists — skipping."
    fi
}

# -----------------------------------------------------------------------------
# Runtime config files
# -----------------------------------------------------------------------------
setup_runtime_files() {
    if [[ ! -f lab.conf ]]; then
        cat > lab.conf << CONF
# OGLab runtime config — generated by setup.sh
PORTAL_PORT=8080
TERMINAL_PORT=7681
NOTEBOOK_PORT=8888
IDE_PORT=8443
IDE_PASSWORD=${IDE_DEFAULT_PASSWORD}
BIND_ADDR=127.0.0.1
CONF
        info "lab.conf written"
    else
        info "lab.conf already exists — skipping."
    fi

    local cs_dir="${HOME}/.config/code-server"
    mkdir -p "$cs_dir"
    cat > "${cs_dir}/config.yaml" << YAML
bind-addr: 127.0.0.1:8443
auth: password
password: ${IDE_DEFAULT_PASSWORD}
cert: false
YAML
    info "code-server config written"

    mkdir -p lab/data/goals lab/data/goals/history lab/data/consent lab/data/experiments lab/models
}

# -----------------------------------------------------------------------------
# Personal knowledge management scaffold
# -----------------------------------------------------------------------------
setup_pkm() {
    local pkm_root="lab/pkm"
    mkdir -p "$pkm_root"/{inbox,sources/{papers,articles,datasets},agents/{research,experiments,synthesis,recommendations},notes/scratch,compiled/{reports,summaries,exports},inference/{prompts,completions,chains}}
    [[ -f "$pkm_root/sources/bookmarks.md" ]] || cat > "$pkm_root/sources/bookmarks.md" << 'BOOKMARKS'
# Bookmarks
# Save URLs with a one-line description. One per line.
# Format: URL — description
BOOKMARKS
    [[ -f "$pkm_root/notes/journal.md" ]] || cat > "$pkm_root/notes/journal.md" << JOURNAL
# Lab Journal

A running log of what happened, what you learned, and what you're thinking.
Newest entries at the top.

---

## $(date +%Y-%m-%d)

Lab initialized with setup.sh.
JOURNAL
    [[ -f "$pkm_root/notes/ideas.md" ]] || cat > "$pkm_root/notes/ideas.md" << 'IDEAS'
# Ideas

Quick captures. Hunches. What-ifs. No pressure — just write.

- 
IDEAS
    info "PKM ready at $pkm_root"
}

# -----------------------------------------------------------------------------
# Start script
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
# Download starter model (airgapped prep)
# -----------------------------------------------------------------------------
download_model() {
    if [[ "${OGLAB_SKIP_MODEL_DOWNLOAD:-0}" == "1" ]]; then
        warn "Skipping model download because OGLAB_SKIP_MODEL_DOWNLOAD=1"
        return
    fi

    local model_dir="lab/models"
    mkdir -p "$model_dir"

    if [[ "$ACCEL" == "mlx" ]]; then
        local model="$MODEL_MLX_ID"
        if [[ -d "${model_dir}/Qwen3-8B-4bit" ]]; then
            info "Model already downloaded."
        else
            info "Downloading MLX model: $model (this takes a few minutes)…"
            python3 -c "from huggingface_hub import snapshot_download; snapshot_download('${model}', local_dir='${model_dir}/Qwen3-8B-4bit')"
        fi
    elif [[ "$ACCEL" == "cuda" ]]; then
        warn "For CUDA, download a model with:"
        echo "  python3 -c \"from huggingface_hub import snapshot_download; snapshot_download('${MODEL_HF_ID}', local_dir='lab/models/Qwen3-8B')\""
    else
        warn "For CPU, download a GGUF model with:"
        echo "  huggingface-cli download ${MODEL_GGUF_ID} --include 'Q4_K_M*' --local-dir lab/models/Qwen3-8B-GGUF --local-dir-use-symlinks False"
    fi
}

# -----------------------------------------------------------------------------
# Verify
# -----------------------------------------------------------------------------
verify() {
    info "Running smoke tests…"
    python3 -c "from oglab.router import ModelRouter; import oglab.portal.app; from oglab.pkm import scaffold; scaffold(); print('OK')" >/dev/null 2>&1 \
        && info "Setup complete!" \
        || warn "Smoke test failed — inspect the environment and re-run: pip install -e ."
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
    setup_runtime_files
    setup_pkm
    gentoo_notes
    wsl_notes
    download_model

    echo ""
    verify
    echo ""
    info "Next step:  ./oglab start"
    echo ""
}

main "$@"
