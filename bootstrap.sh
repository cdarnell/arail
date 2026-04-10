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
    step "1/10  Detecting hardware"

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

# ── Build Profile Constants ───────────────────────────────────────────
MIN_CPUS=2
MIN_RAM_GB=4
MIN_DISK_GB=8

# SLM — always loaded in RAM (Phi-3.5-mini, best sub-4B on the market)
SLM_MLX_ID="mlx-community/Phi-3.5-mini-instruct-4bit"
SLM_GGUF_ID="microsoft/Phi-3.5-mini-instruct-GGUF"
SLM_HF_ID="microsoft/Phi-3.5-mini-instruct"

# Deep engine — AirLLM 70B+ from disk
DEEP_MODEL_ID="meta-llama/Llama-3.1-70B-Instruct"

# ── 2. Build Profile (discovery-driven) ─────────────────────────────────
compute_build_profile() {
    step "2/10  Computing build profile"

    # ── Preflight gates ──
    if (( CPUS < MIN_CPUS )); then
        error "Need at least ${MIN_CPUS} CPUs — detected ${CPUS}."
    fi
    if (( TOTAL_MEM_GB < MIN_RAM_GB )); then
        error "Need at least ${MIN_RAM_GB} GB RAM — detected ${TOTAL_MEM_GB} GB."
    fi
    if (( DISK_FREE_GB < MIN_DISK_GB )); then
        error "Need at least ${MIN_DISK_GB} GB free disk — detected ${DISK_FREE_GB} GB."
    fi
    if ! command -v python3 &>/dev/null; then
        error "python3 not found. Install Python 3.10+ first."
    fi
    local pyver
    pyver="$(python3 -c 'import sys; print(sys.version_info.minor)')" 2>/dev/null || pyver=0
    if (( pyver < 10 )); then
        error "Python 3.10+ required — detected 3.${pyver}."
    fi
    if ! command -v git &>/dev/null; then
        error "git not found. Install git first."
    fi

    # ── NVMe / SSD detection ──
    DISK_TYPE="HDD"
    case "$OS" in
        Darwin)
            if diskutil info / 2>/dev/null | grep -qi "Solid State.*Yes"; then
                DISK_TYPE="SSD"
            elif diskutil info / 2>/dev/null | grep -qi "Protocol.*NVMe"; then
                DISK_TYPE="NVMe"
            fi
            ;;
        Linux)
            local root_dev
            root_dev="$(lsblk -no PKNAME "$(findmnt -n -o SOURCE /)" 2>/dev/null | head -1)" || root_dev=""
            if [[ -n "$root_dev" ]]; then
                local rota
                rota="$(lsblk -dno ROTA "/dev/${root_dev}" 2>/dev/null)" || rota="1"
                if [[ "$rota" == "0" ]]; then
                    if [[ -d "/sys/block/${root_dev}/device" ]] && \
                       grep -qi nvme <<< "$root_dev" 2>/dev/null; then
                        DISK_TYPE="NVMe"
                    else
                        DISK_TYPE="SSD"
                    fi
                fi
            fi
            ;;
    esac

    # ── Tier computation — zero user input ──
    DEEP_ENABLED="false"
    if (( DISK_FREE_GB >= 80 )) && [[ "$DISK_TYPE" != "HDD" ]]; then
        SPEC_TIER="deep"
        DEEP_ENABLED="true"
        MODEL_SIZE="small"  # SLM for interactive, AirLLM for research
    elif (( DISK_FREE_GB >= 80 )) && [[ "$DISK_TYPE" == "HDD" ]]; then
        # HDD: deep is possible but slow; warn and enable anyway
        SPEC_TIER="deep"
        DEEP_ENABLED="true"
        MODEL_SIZE="small"
    elif (( TOTAL_MEM_GB >= 16 && DISK_FREE_GB >= 40 )); then
        SPEC_TIER="full"
        MODEL_SIZE="large"
    elif (( TOTAL_MEM_GB >= 8 && DISK_FREE_GB >= 20 )); then
        SPEC_TIER="standard"
        MODEL_SIZE="medium"
    else
        SPEC_TIER="minimum"
        MODEL_SIZE="small"
    fi

    # ── Resource allocation — computed, not asked ──
    LAB_CPUS=$(( CPUS > 4 ? CPUS - 2 : CPUS ))
    LAB_MEM_GB=$(( TOTAL_MEM_GB * 3 / 4 ))
    (( LAB_MEM_GB < 2 )) && LAB_MEM_GB=2

    # ── SLM selection (always installed) ──
    case "$ACCEL" in
        mlx)  SLM_ID="$SLM_MLX_ID" ; SLM_DIR="Phi-3.5-mini-instruct-4bit" ; SLM_SIZE="~2 GB" ;;
        cpu)  SLM_ID="$SLM_GGUF_ID" ; SLM_DIR="Phi-3.5-mini-instruct-GGUF" ; SLM_SIZE="~2 GB" ;;
        cuda) SLM_ID="$SLM_HF_ID" ; SLM_DIR="Phi-3.5-mini-instruct" ; SLM_SIZE="~2 GB" ;;
        *)    SLM_ID="$SLM_GGUF_ID" ; SLM_DIR="Phi-3.5-mini-instruct-GGUF" ; SLM_SIZE="~2 GB" ;;
    esac

    # ── Fast model selection (beyond SLM, for standard / full tiers) ──
    FAST_MODEL_ID="" ; FAST_DIR="" ; FAST_SIZE=""
    case "${ACCEL}:${MODEL_SIZE}" in
        mlx:medium)  FAST_MODEL_ID="mlx-community/Mistral-7B-Instruct-v0.3-4bit" ;  FAST_DIR="Mistral-7B-Instruct-v0.3-4bit" ; FAST_SIZE="~4 GB" ;;
        mlx:large)   FAST_MODEL_ID="mlx-community/Mixtral-8x7B-Instruct-v0.1-4bit" ; FAST_DIR="Mixtral-8x7B-Instruct-v0.1-4bit" ; FAST_SIZE="~8 GB" ;;
        cuda:medium) FAST_MODEL_ID="mistralai/Mistral-7B-Instruct-v0.2" ;            FAST_DIR="Mistral-7B-Instruct-v0.2" ; FAST_SIZE="~4 GB" ;;
        cuda:large)  FAST_MODEL_ID="mistralai/Mixtral-8x7B-Instruct-v0.1" ;           FAST_DIR="Mixtral-8x7B-Instruct-v0.1" ; FAST_SIZE="~8 GB" ;;
        cpu:medium)  FAST_MODEL_ID="TheBloke/Mistral-7B-Instruct-v0.2-GGUF" ;         FAST_DIR="Mistral-7B-Instruct-v0.2-GGUF" ; FAST_SIZE="~4 GB" ;;
        cpu:large)   FAST_MODEL_ID="TheBloke/Mixtral-8x7B-Instruct-v0.1-GGUF" ;       FAST_DIR="Mixtral-8x7B-Instruct-v0.1-GGUF" ; FAST_SIZE="~8 GB" ;;
    esac

    # ── Deep model (AirLLM) ──
    DEEP_DIR="Llama-3.1-70B-Instruct"
    DEEP_SIZE="~40 GB"
}

# ── 3. Build Manifest ───────────────────────────────────────────────────
show_build_manifest() {
    step "3/10  Build manifest"

    local disk_badge="${DISK_TYPE}"
    [[ "$DISK_TYPE" == "NVMe" ]] && disk_badge="${GREEN}NVMe SSD ✓${RESET}"
    [[ "$DISK_TYPE" == "SSD" ]]  && disk_badge="${GREEN}SSD ✓${RESET}"
    [[ "$DISK_TYPE" == "HDD" ]]  && disk_badge="${YELLOW}HDD (slow for deep)${RESET}"

    local tier_color="${GREEN}"
    [[ "$SPEC_TIER" == "minimum" ]]  && tier_color="${YELLOW}"
    [[ "$SPEC_TIER" == "standard" ]] && tier_color="${CYAN}"
    [[ "$SPEC_TIER" == "deep" ]]     && tier_color="${BOLD}${GREEN}"

    echo ""
    echo -e "  ┌─── BUILD MANIFEST ──────────────────────────────────────────────┐"
    echo -e "  │                                                                 │"
    printf  "  │  Tier:          ${tier_color}▶ %-8s${RESET}                                   │\n" "$SPEC_TIER"
    printf  "  │  Platform:      %-43s  │\n" "${PLATFORM} ${ARCH} (${ACCEL})"
    printf  "  │  Disk:          %-3s GB free (%b)%*s│\n" "$DISK_FREE_GB" "$disk_badge" $((24 - ${#DISK_TYPE})) ""
    echo -e "  │                                                                 │"
    echo -e "  │  ┌─ ENGINES ─────────────────────────────────────────────┐      │"
    printf  "  │  │  ⚡ SLM (always on)   %-20s  %s  │      │\n" "${SLM_DIR}" "${SLM_SIZE}"
    if [[ -n "$FAST_MODEL_ID" ]]; then
    printf  "  │  │  🚀 Fast engine       %-20s  %s  │      │\n" "${FAST_DIR}" "${FAST_SIZE}"
    fi
    if [[ "$DEEP_ENABLED" == "true" ]]; then
    printf  "  │  │  🔬 Deep research     %-20s %s │      │\n" "${DEEP_DIR}" "${DEEP_SIZE}"
    echo -e "  │  │     via AirLLM · 4-bit · layer-by-layer from disk     │      │"
    fi
    echo -e "  │  └───────────────────────────────────────────────────────┘      │"
    echo -e "  │                                                                 │"
    printf  "  │  Resources:     %s CPUs · %s GB RAM · all services%*s│\n" "$LAB_CPUS" "$LAB_MEM_GB" $((15 - ${#LAB_CPUS} - ${#LAB_MEM_GB})) ""
    echo -e "  │  Cost tracking: cloud-equivalent savings + \$0.13/kWh energy     │"
    if [[ "$DEEP_ENABLED" == "true" ]]; then
    echo -e "  │  Research:      deep async (70B AirLLM) + fast interactive      │"
    else
    echo -e "  │  Research:      fast interactive (SLM + local model)             │"
    fi
    echo -e "  │                                                                 │"
    echo -e "  └─────────────────────────────────────────────────────────────────┘"
    echo ""

    if [[ "$DEEP_ENABLED" == "true" && "$DISK_TYPE" == "HDD" ]]; then
        warn "Your disk is a spinning HDD. Deep inference will work but expect"
        warn "significantly slower layer loading. NVMe/SSD recommended."
        echo ""
    fi

    ask "Build this lab?" "Y"
    if [[ ! "$REPLY" =~ ^[Yy] ]]; then
        info "Cancelled. Run bootstrap.sh again when ready."
        exit 0
    fi
}

# ── 3. System Packages ──────────────────────────────────────────────────
install_system_deps() {
    step "4/10  System packages"

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
    step "5/10  Python environment"

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

    # AirLLM for deep research tier
    if [[ "${DEEP_ENABLED:-false}" == "true" ]]; then
        info "Installing AirLLM (deep research — layer-by-layer inference)…"
        pip install -q airllm
    fi
}

# ── 5. Lab Services ─────────────────────────────────────────────────────
install_services() {
    step "6/10  Lab services"

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

# ── 6. Download Models ──────────────────────────────────────────────────
download_model() {
    step "7/10  AI models"

    local model_dir="./models"
    mkdir -p "$model_dir" "$model_dir/airllm_cache"

    pip install -q huggingface-hub

    # ── Always download SLM (Phi-3.5-mini — fast, always in RAM) ──
    info "SLM engine: ${SLM_ID}"
    if [[ -d "${model_dir}/${SLM_DIR}" ]]; then
        info "SLM already downloaded: ${SLM_DIR}"
    else
        info "Downloading SLM (${SLM_SIZE})…"
        python3 -c "
from huggingface_hub import snapshot_download
snapshot_download('${SLM_ID}', local_dir='${model_dir}/${SLM_DIR}')
" || warn "SLM download failed — you can download manually later."
    fi
    MODEL_ID="$SLM_ID"
    MODEL_DIR_NAME="$SLM_DIR"

    # ── Download fast model (standard/full tiers get a bigger model too) ──
    if [[ -n "$FAST_MODEL_ID" ]]; then
        info "Fast engine: ${FAST_MODEL_ID}"
        if [[ -d "${model_dir}/${FAST_DIR}" ]]; then
            info "Fast model already downloaded: ${FAST_DIR}"
        else
            info "Downloading fast model (${FAST_SIZE})…"
            python3 -c "
from huggingface_hub import snapshot_download
snapshot_download('${FAST_MODEL_ID}', local_dir='${model_dir}/${FAST_DIR}')
" || warn "Fast model download failed — you can download manually later."
        fi
        # Use the bigger model as primary
        MODEL_ID="$FAST_MODEL_ID"
        MODEL_DIR_NAME="$FAST_DIR"
    fi

    # ── Deep model (AirLLM 70B — downloaded for deep-tier systems) ──
    if [[ "$DEEP_ENABLED" == "true" ]]; then
        echo ""
        info "Deep research engine: ${DEEP_MODEL_ID}"
        info "This is a large download (~40 GB). AirLLM will load it layer-by-layer from disk."
        if [[ -d "${model_dir}/${DEEP_DIR}" ]]; then
            info "Deep model already downloaded: ${DEEP_DIR}"
        else
            info "Downloading deep model (${DEEP_SIZE})… this will take a while."
            python3 -c "
from huggingface_hub import snapshot_download
snapshot_download('${DEEP_MODEL_ID}', local_dir='${model_dir}/${DEEP_DIR}')
" || warn "Deep model download failed — you can download manually or run bootstrap again."
        fi
    fi
}

# ── 7. Write Configuration ──────────────────────────────────────────────
write_config() {
    step "8/10  Configuration"

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

        # AirLLM deep research config
        if [[ "$DEEP_ENABLED" == "true" ]]; then
            sed -i.bak "s|^AIRLLM_MODEL=.*|AIRLLM_MODEL=${DEEP_MODEL_ID}|" .env
            sed -i.bak 's/^AIRLLM_RESEARCH=.*/AIRLLM_RESEARCH=true/' .env
        else
            sed -i.bak 's/^AIRLLM_RESEARCH=.*/AIRLLM_RESEARCH=false/' .env
        fi

        # Energy rate
        sed -i.bak 's/^ENERGY_RATE_KWH=.*/ENERGY_RATE_KWH=0.13/' .env

        rm -f .env.bak
        info ".env created (backend=${ACCEL}, model=${MODEL_ID:-auto}, deep=${DEEP_ENABLED})"
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
SPEC_TIER=${SPEC_TIER}
DEEP_ENABLED=${DEEP_ENABLED}
DISK_TYPE=${DISK_TYPE}

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

# ── 8a. Research Goal ───────────────────────────────────────────────────
ask_goal() {
    echo ""
    echo -e "  ${BOLD}Almost done.${RESET} One last thing — what should this lab work on?"
    echo -e "  ${DIM}(Your goal drives the researcher agent. You can change it later.)${RESET}"
    echo ""
    ask "What do you want to research?" ""

    if [[ -n "$REPLY" ]]; then
        # Save bootstrap goal
        mkdir -p data/goals
        python3 -c "
import json, pathlib
goal = {
    'goal': '''${REPLY}''',
    'source': 'bootstrap',
    'status': 'active'
}
pathlib.Path('data/goals/bootstrap_goal.json').write_text(json.dumps(goal, indent=2))
"
        BOOTSTRAP_GOAL="$REPLY"
        info "Goal saved: ${REPLY}"
    else
        BOOTSTRAP_GOAL=""
        info "No goal set. You can set one from the portal dashboard."
    fi
}

# ── 9. Generate start.sh ───────────────────────────────────────────────
write_start_script() {
    step "9/10  Start script"

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

PIDS=()

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
    echo -e "  ${BOLD}Tier:${RESET}       ${SPEC_TIER} (${DISK_TYPE})"
    echo -e "  ${BOLD}SLM:${RESET}        ${SLM_DIR} (always in RAM)"
    if [[ -n "${FAST_MODEL_ID:-}" ]]; then
    echo -e "  ${BOLD}Fast model:${RESET} ${FAST_DIR}"
    fi
    if [[ "$DEEP_ENABLED" == "true" ]]; then
    echo -e "  ${BOLD}Deep:${RESET}       ${DEEP_DIR} via AirLLM (70B from disk)"
    fi
    echo -e "  ${BOLD}Costs:${RESET}      Cloud-equivalent tracking + \$0.13/kWh energy"
    if [[ -n "${BOOTSTRAP_GOAL:-}" ]]; then
    echo -e "  ${BOLD}Goal:${RESET}       ${BOOTSTRAP_GOAL}"
    fi
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
    compute_build_profile
    show_build_manifest
    install_system_deps
    setup_python
    install_services
    download_model
    write_config
    ask_goal
    write_start_script
    summary
}

PIDS=()
GPU_NAME=""
GPU_MEM=""
SPEC_TIER=""
DISK_FREE_GB=0
DISK_TYPE="HDD"
DEEP_ENABLED="false"
BOOTSTRAP_GOAL=""
SLM_ID=""
SLM_DIR=""
FAST_MODEL_ID=""
FAST_DIR=""
main "$@"
