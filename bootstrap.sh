#!/usr/bin/env bash
# =============================================================================
# OGLab — Full Lab Bootstrap
#
# One command gets you: Python venv, AI model backends, portal UI,
# terminal (ttyd), notebook (Jupyter), IDE (code-server), and all
# default agents — pre-configured and ready to run.
#
# Usage:
#   git clone https://github.com/cdarnell/minimalist-blueprint.git oglab
#   cd oglab
#   ./bootstrap.sh
# =============================================================================
set -euo pipefail

# ── Colors / helpers ─────────────────────────────────────────────────────
BOLD="\033[1m"
DIM="\033[2m"
GREEN="\033[0;32m"
CYAN="\033[0;36m"
YELLOW="\033[0;33m"
RED="\033[0;31m"
RESET="\033[0m"

info()  { echo -e "${GREEN}[oglab]${RESET} $*"; }
step()  { echo -e "\n${CYAN}━━━ ${BOLD}$*${RESET}"; }
warn()  { echo -e "${YELLOW}[oglab]${RESET} $*"; }
error() { echo -e "${RED}[oglab]${RESET} $*"; exit 1; }

ask() {
    # ask "prompt" "default"  →  writes to REPLY
    local prompt="$1" default="${2:-}"
    if [[ -n "$default" ]]; then
        read -rp "$(echo -e "${GREEN}?${RESET} ${prompt} ${DIM}[${default}]${RESET}: ")" REPLY
        REPLY="${REPLY:-$default}"
    else
        read -rp "$(echo -e "${GREEN}?${RESET} ${prompt}: ")" REPLY
    fi
}

# ── Banner ───────────────────────────────────────────────────────────────
banner() {
    echo ""
    echo -e "${GREEN}"
    cat << 'EOF'
   ╔═══════════════════════════════════════════╗
   ║          ⟨ O G L a b ⟩                   ║
   ║     AI Lab Bootstrap — v1.0               ║
   ║     Local-first. Airgapped. Yours.        ║
   ╚═══════════════════════════════════════════╝
EOF
    echo -e "${RESET}"
}

# ── 1. Hardware Detection ────────────────────────────────────────────────
detect_hardware() {
    step "1/8  Detecting hardware"

    OS="$(uname -s)"
    ARCH="$(uname -m)"

    # CPU count
    case "$OS" in
        Darwin) CPUS="$(sysctl -n hw.ncpu)" ;;
        Linux)  CPUS="$(nproc)" ;;
        *)      CPUS=4 ;;
    esac

    # Total memory (MB)
    case "$OS" in
        Darwin) TOTAL_MEM_MB=$(( $(sysctl -n hw.memsize) / 1024 / 1024 )) ;;
        Linux)  TOTAL_MEM_MB=$(( $(grep MemTotal /proc/meminfo | awk '{print $2}') / 1024 )) ;;
        *)      TOTAL_MEM_MB=8192 ;;
    esac
    TOTAL_MEM_GB=$(( TOTAL_MEM_MB / 1024 ))

    # Disk free (GB) in current directory
    case "$OS" in
        Darwin) DISK_FREE_GB=$(df -g . | awk 'NR==2 {print $4}') ;;
        Linux)  DISK_FREE_GB=$(df --output=avail -BG . | awk 'NR==2 {gsub(/G/,""); print $1}') ;;
        *)      DISK_FREE_GB=50 ;;
    esac

    # Platform
    case "$OS" in
        Darwin)
            PLATFORM="macos"
            [[ "$ARCH" == "arm64" ]] && ACCEL="mlx" || ACCEL="cpu"
            ;;
        Linux)
            if grep -qiE '(microsoft|wsl)' /proc/version 2>/dev/null; then
                PLATFORM="wsl"
            elif [[ -f /etc/gentoo-release ]]; then
                PLATFORM="gentoo"
            else
                PLATFORM="linux"
            fi
            if command -v nvidia-smi &>/dev/null && nvidia-smi &>/dev/null; then
                ACCEL="cuda"
                GPU_NAME="$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1)"
                GPU_MEM="$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits 2>/dev/null | head -1)"
            else
                ACCEL="cpu"
            fi
            ;;
        *)
            error "Unsupported OS: $OS"
            ;;
    esac

    echo ""
    info "Platform:    ${BOLD}${PLATFORM}${RESET} (${ARCH})"
    info "CPUs:        ${BOLD}${CPUS}${RESET}"
    info "Memory:      ${BOLD}${TOTAL_MEM_GB} GB${RESET}"
    info "Disk free:   ${BOLD}${DISK_FREE_GB} GB${RESET}"
    info "Accelerator: ${BOLD}${ACCEL}${RESET}"
    [[ -n "${GPU_NAME:-}" ]] && info "GPU:         ${BOLD}${GPU_NAME}${RESET} (${GPU_MEM} MB VRAM)"
}

# ── 2. Resource Allocation ───────────────────────────────────────────────
ask_resources() {
    step "2/8  Resource allocation"

    echo ""
    echo -e "  Your machine has ${BOLD}${CPUS} CPUs${RESET}, ${BOLD}${TOTAL_MEM_GB} GB RAM${RESET}, ${BOLD}${DISK_FREE_GB} GB disk free${RESET}."
    echo -e "  How much should the lab use?"
    echo ""

    # CPUs — default to all-but-two (leave headroom for OS), minimum 2
    local default_cpus=$(( CPUS > 4 ? CPUS - 2 : CPUS ))
    ask "CPUs for the lab" "$default_cpus"
    LAB_CPUS="$REPLY"

    # Memory — default to 75% of total
    local default_mem=$(( TOTAL_MEM_GB * 3 / 4 ))
    (( default_mem < 2 )) && default_mem=2
    ask "Memory for the lab (GB)" "$default_mem"
    LAB_MEM_GB="$REPLY"

    # Model size preference
    echo ""
    echo -e "  Model size (larger = smarter, needs more RAM/VRAM):"
    echo -e "    ${BOLD}small${RESET}   — 1-3B params, ~2 GB  (fast, low quality)"
    echo -e "    ${BOLD}medium${RESET}  — 7-8B params, ~4 GB  (good balance)"
    echo -e "    ${BOLD}large${RESET}   — 13-14B params, ~8 GB (best quality)"
    echo ""
    ask "Model size" "medium"
    MODEL_SIZE="$REPLY"

    info "Allocation: ${LAB_CPUS} CPUs, ${LAB_MEM_GB} GB RAM, model=${MODEL_SIZE}"
}

# ── 3. System Packages ──────────────────────────────────────────────────
install_system_deps() {
    step "3/8  System packages"

    case "$PLATFORM" in
        gentoo)
            info "Gentoo detected — installing via emerge"
            local pkgs=(
                dev-lang/python
                dev-python/pip
                dev-vcs/git
                net-misc/curl
                app-misc/tmux
                app-misc/jq
                sys-process/htop
                # Build tools for compiling Python C extensions
                sys-devel/gcc
                sys-devel/make
                dev-build/cmake
                dev-libs/openssl
                sys-libs/zlib
                dev-libs/libffi
            )
            info "Packages: ${pkgs[*]}"
            sudo emerge -av --noreplace "${pkgs[@]}" || warn "Some packages may already be installed"

            if [[ "$ACCEL" == "cuda" ]]; then
                info "Installing Nvidia CUDA toolkit…"
                sudo emerge -av --noreplace dev-util/nvidia-cuda-toolkit x11-drivers/nvidia-drivers
            fi
            ;;

        macos)
            info "macOS detected — checking Homebrew"
            if ! command -v brew &>/dev/null; then
                warn "Homebrew not found. Install it: https://brew.sh"
                warn "Skipping system packages."
                return
            fi
            brew install python@3.11 git curl tmux jq htop cmake 2>/dev/null || true
            ;;

        wsl|linux)
            info "Linux detected — installing via apt"
            if command -v apt-get &>/dev/null; then
                sudo apt-get update -qq
                sudo apt-get install -y -qq \
                    python3 python3-venv python3-pip python3-dev \
                    git curl tmux jq htop \
                    build-essential cmake libssl-dev zlib1g-dev libffi-dev
                if [[ "$ACCEL" == "cuda" ]]; then
                    info "CUDA detected — ensure nvidia-driver + cuda-toolkit from Nvidia repos"
                fi
            else
                warn "No apt — install Python 3.10+, git, curl, cmake manually."
            fi
            ;;
    esac
}

# ── 4. Python Environment ───────────────────────────────────────────────
setup_python() {
    step "4/8  Python environment"

    if ! command -v python3 &>/dev/null; then
        error "Python 3 not found. Install it and re-run."
    fi

    local pyver
    pyver="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
    info "Python ${pyver}"

    if [[ ! -d ".venv" ]]; then
        info "Creating virtual environment…"
        python3 -m venv .venv
    fi
    # shellcheck disable=SC1091
    source .venv/bin/activate
    pip install --upgrade pip setuptools wheel -q

    info "Installing core lab packages…"
    pip install -q -r requirements.txt

    # Accelerator deps
    case "$ACCEL" in
        mlx)
            info "Installing MLX (Apple Silicon)…"
            pip install -q mlx mlx-lm
            ;;
        cuda)
            info "Installing CUDA / vLLM / PyTorch…"
            pip install -q vllm torch
            ;;
        cpu)
            info "Installing llama-cpp-python (CPU inference)…"
            pip install -q llama-cpp-python
            ;;
    esac

    # Always install the requests library (used by openai_compat backend)
    pip install -q requests
}

# ── 5. Lab Services ─────────────────────────────────────────────────────
install_services() {
    step "5/8  Lab services"

    # --- Portal (FastAPI) ---
    info "Portal dependencies…"
    pip install -q fastapi uvicorn jinja2

    # --- Jupyter Notebook ---
    info "Jupyter Lab…"
    pip install -q jupyterlab

    # --- ttyd (terminal in browser) ---
    if ! command -v ttyd &>/dev/null; then
        info "Installing ttyd (browser terminal)…"
        case "$PLATFORM" in
            macos)    brew install ttyd 2>/dev/null || warn "ttyd install failed — install manually: brew install ttyd" ;;
            gentoo)   sudo emerge -av --noreplace net-misc/ttyd 2>/dev/null || warn "ttyd: emerge net-misc/ttyd" ;;
            wsl|linux)
                if command -v apt-get &>/dev/null; then
                    sudo apt-get install -y -qq ttyd 2>/dev/null || warn "ttyd not in apt — see https://github.com/tsl0922/ttyd"
                fi
                ;;
        esac
    else
        info "ttyd already installed"
    fi

    # --- code-server (VS Code in browser — free, open source) ---
    if ! command -v code-server &>/dev/null; then
        info "Installing code-server (browser IDE)…"
        case "$PLATFORM" in
            macos)
                brew install code-server 2>/dev/null || {
                    warn "Falling back to npm install"
                    npm install -g code-server 2>/dev/null || warn "code-server install failed — install manually"
                }
                ;;
            gentoo)
                # code-server is not in portage, use the official install script
                curl -fsSL https://code-server.dev/install.sh | sh 2>/dev/null || warn "code-server install failed"
                ;;
            wsl|linux)
                curl -fsSL https://code-server.dev/install.sh | sh 2>/dev/null || warn "code-server install failed"
                ;;
        esac
    else
        info "code-server already installed"
    fi
}

# ── 6. Download Model ───────────────────────────────────────────────────
download_model() {
    step "6/8  AI model"

    local model_dir="./models"
    mkdir -p "$model_dir"

    # Determine model by size preference and accelerator
    case "${ACCEL}:${MODEL_SIZE}" in
        mlx:small)   MODEL_ID="mlx-community/Qwen2.5-1.5B-Instruct-4bit" ; MODEL_DIR_NAME="Qwen2.5-1.5B-Instruct-4bit" ;;
        mlx:medium)  MODEL_ID="mlx-community/Mistral-7B-Instruct-v0.3-4bit" ; MODEL_DIR_NAME="Mistral-7B-Instruct-v0.3-4bit" ;;
        mlx:large)   MODEL_ID="mlx-community/Mixtral-8x7B-Instruct-v0.1-4bit" ; MODEL_DIR_NAME="Mixtral-8x7B-Instruct-v0.1-4bit" ;;
        cuda:small)  MODEL_ID="Qwen/Qwen2.5-1.5B-Instruct" ; MODEL_DIR_NAME="Qwen2.5-1.5B-Instruct" ;;
        cuda:medium) MODEL_ID="mistralai/Mistral-7B-Instruct-v0.2" ; MODEL_DIR_NAME="Mistral-7B-Instruct-v0.2" ;;
        cuda:large)  MODEL_ID="mistralai/Mixtral-8x7B-Instruct-v0.1" ; MODEL_DIR_NAME="Mixtral-8x7B-Instruct-v0.1" ;;
        cpu:small)   MODEL_ID="TheBloke/Qwen-1_8B-Chat-GGUF" ; MODEL_DIR_NAME="Qwen-1.8B-Chat-GGUF" ;;
        cpu:medium)  MODEL_ID="TheBloke/Mistral-7B-Instruct-v0.2-GGUF" ; MODEL_DIR_NAME="Mistral-7B-Instruct-v0.2-GGUF" ;;
        cpu:large)   MODEL_ID="TheBloke/Mixtral-8x7B-Instruct-v0.1-GGUF" ; MODEL_DIR_NAME="Mixtral-8x7B-Instruct-v0.1-GGUF" ;;
        *)           MODEL_ID="mlx-community/Mistral-7B-Instruct-v0.3-4bit" ; MODEL_DIR_NAME="Mistral-7B-Instruct-v0.3-4bit" ;;
    esac

    if [[ -d "${model_dir}/${MODEL_DIR_NAME}" ]]; then
        info "Model already downloaded: ${MODEL_DIR_NAME}"
    else
        ask "Download model ${MODEL_ID}? (requires internet)" "y"
        if [[ "$REPLY" =~ ^[Yy] ]]; then
            info "Downloading ${MODEL_ID}…"
            pip install -q huggingface-hub
            python3 -c "
from huggingface_hub import snapshot_download
snapshot_download('${MODEL_ID}', local_dir='${model_dir}/${MODEL_DIR_NAME}')
" || warn "Download failed — you can download manually later."
        else
            info "Skipping model download. You can download later or use an external API."
        fi
    fi
}

# ── 7. Write Configuration ──────────────────────────────────────────────
write_config() {
    step "7/8  Configuration"

    # .env
    if [[ ! -f .env ]]; then
        cp .env.example .env

        # Backend
        case "$ACCEL" in
            mlx)  sed -i.bak 's/^MODEL_BACKEND=auto/MODEL_BACKEND=mlx/' .env ;;
            cuda) sed -i.bak 's/^MODEL_BACKEND=auto/MODEL_BACKEND=cuda/' .env ;;
            cpu)  sed -i.bak 's/^MODEL_BACKEND=auto/MODEL_BACKEND=cpu/' .env ;;
        esac

        # Model name
        if [[ -n "${MODEL_ID:-}" ]]; then
            sed -i.bak "s|^MODEL_NAME=.*|MODEL_NAME=${MODEL_ID}|" .env
        fi

        rm -f .env.bak
        info ".env created (backend=${ACCEL}, model=${MODEL_ID:-auto})"
    else
        info ".env already exists — keeping current config"
    fi

    # lab.conf — resource allocation for services
    cat > lab.conf << CONF
# OGLab resource allocation — generated by bootstrap.sh
# Edit and re-run ./start.sh to apply changes.

LAB_CPUS=${LAB_CPUS}
LAB_MEM_GB=${LAB_MEM_GB}
MODEL_SIZE=${MODEL_SIZE}

# Service ports
PORTAL_PORT=8080
TERMINAL_PORT=7681
NOTEBOOK_PORT=8888
IDE_PORT=8443

# code-server password (change this!)
IDE_PASSWORD=oglab

# Bind address (0.0.0.0 = all interfaces, 127.0.0.1 = local only)
BIND_ADDR=127.0.0.1
CONF
    info "lab.conf written (edit to change ports or resource limits)"

    # code-server config
    local cs_dir="${HOME}/.config/code-server"
    mkdir -p "$cs_dir"
    cat > "${cs_dir}/config.yaml" << YAML
bind-addr: 127.0.0.1:8443
auth: password
password: oglab
cert: false
YAML
    info "code-server config written (password: oglab — change it!)"

    # Create data directories
    mkdir -p data/goals data/goals/history data/consent data/experiments plugins models
}

# ── 8. Generate start.sh ────────────────────────────────────────────────
write_start_script() {
    step "8/8  Start script"

    cat > start.sh << 'STARTSCRIPT'
#!/usr/bin/env bash
# =============================================================================
# OGLab — Start all lab services
# =============================================================================
set -euo pipefail

GREEN="\033[0;32m"
CYAN="\033[0;36m"
BOLD="\033[1m"
RESET="\033[0m"

info() { echo -e "${GREEN}[oglab]${RESET} $*"; }

# Load config
source lab.conf 2>/dev/null || true
BIND="${BIND_ADDR:-127.0.0.1}"

# Activate venv
source .venv/bin/activate

echo ""
echo -e "${CYAN}${BOLD}⟨OGLab⟩ Starting lab services…${RESET}"
echo ""

# --- Portal (FastAPI) ---
info "Portal        → http://${BIND}:${PORTAL_PORT:-8080}"
uvicorn portal.app:app \
    --host "$BIND" --port "${PORTAL_PORT:-8080}" \
    --log-level warning &
PIDS+=($!)

# --- Terminal (ttyd) ---
if command -v ttyd &>/dev/null; then
    info "Terminal      → http://${BIND}:${TERMINAL_PORT:-7681}"
    ttyd -W -p "${TERMINAL_PORT:-7681}" -i "$BIND" zsh &
    PIDS+=($!)
else
    info "Terminal      → (ttyd not installed — skipping)"
fi

# --- Jupyter Lab ---
info "Notebook      → http://${BIND}:${NOTEBOOK_PORT:-8888}"
jupyter lab \
    --no-browser \
    --ip="$BIND" \
    --port="${NOTEBOOK_PORT:-8888}" \
    --NotebookApp.token="" \
    --NotebookApp.password="" \
    --quiet &
PIDS+=($!)

# --- code-server (IDE) ---
if command -v code-server &>/dev/null; then
    info "IDE           → http://${BIND}:${IDE_PORT:-8443}"
    code-server \
        --bind-addr "${BIND}:${IDE_PORT:-8443}" \
        --auth password \
        --disable-telemetry \
        . &
    PIDS+=($!)
else
    info "IDE           → (code-server not installed — skipping)"
fi

echo ""
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo -e "  ${BOLD}All services running.${RESET}  Press Ctrl+C to stop."
echo ""
echo -e "  Dashboard:  ${BOLD}http://${BIND}:${PORTAL_PORT:-8080}${RESET}"
echo -e "  Terminal:   ${BOLD}http://${BIND}:${TERMINAL_PORT:-7681}${RESET}"
echo -e "  Notebook:   ${BOLD}http://${BIND}:${NOTEBOOK_PORT:-8888}${RESET}"
echo -e "  IDE:        ${BOLD}http://${BIND}:${IDE_PORT:-8443}${RESET}  (password: ${IDE_PASSWORD:-oglab})"
echo ""
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"

# Trap Ctrl+C to kill all background jobs
cleanup() {
    echo ""
    info "Shutting down…"
    for pid in "${PIDS[@]}"; do
        kill "$pid" 2>/dev/null
    done
    wait 2>/dev/null
    info "All services stopped."
}
trap cleanup INT TERM

wait
STARTSCRIPT

    chmod +x start.sh
    info "start.sh generated — run ${BOLD}./start.sh${RESET} to launch all services"
}

# ── Summary ──────────────────────────────────────────────────────────────
summary() {
    echo ""
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
    echo -e "  ${BOLD}${GREEN}✓ Bootstrap complete!${RESET}"
    echo ""
    echo -e "  ${BOLD}To start the lab:${RESET}"
    echo -e "    source .venv/bin/activate"
    echo -e "    ./start.sh"
    echo ""
    echo -e "  ${BOLD}Services:${RESET}"
    echo -e "    Dashboard  http://127.0.0.1:8080   — Goal tracking, experiments, agents"
    echo -e "    Terminal   http://127.0.0.1:7681   — Full shell in browser"
    echo -e "    Notebook   http://127.0.0.1:8888   — Jupyter Lab"
    echo -e "    IDE        http://127.0.0.1:8443   — VS Code (code-server)"
    echo ""
    echo -e "  ${BOLD}Quick test:${RESET}"
    echo -e "    python3 examples/peanut_farmer/run.py"
    echo ""

    if [[ "$PLATFORM" == "gentoo" ]]; then
        echo -e "  ${BOLD}Gentoo user:${RESET}"
        echo -e "    Default login:  gentoofoo / gentoofoo"
        echo -e "    ${YELLOW}Change your password now:  passwd${RESET}"
        echo ""
    fi

    echo -e "  Edit ${BOLD}lab.conf${RESET} to change resource limits or ports."
    echo -e "  Edit ${BOLD}.env${RESET} to change model backend or API keys."
    echo ""
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
    echo ""
}

# =============================================================================
# Main
# =============================================================================
main() {
    banner
    detect_hardware
    ask_resources
    install_system_deps
    setup_python
    install_services
    download_model
    write_config
    write_start_script
    summary
}

PIDS=()
GPU_NAME=""
GPU_MEM=""
main "$@"
