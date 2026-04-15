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

# Unified password — set by capture_password() below. One secret covers:
#   - code-server (IDE) login
#   - Open Notebook data encryption key
#   - future auth proxy
OGLAB_PASSWORD=""

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
# Unified password — one secret for IDE + Open Notebook + future auth
# -----------------------------------------------------------------------------
capture_password() {
    # Reuse an existing password if one is already stored in .env.
    if [[ -f .env ]]; then
        local existing
        existing="$(grep -E '^OGLAB_PASSWORD=' .env | head -n1 | cut -d= -f2-)"
        if [[ -n "$existing" && "$existing" != "change-me" ]]; then
            OGLAB_PASSWORD="$existing"
            info "Reusing existing OGLAB_PASSWORD from .env"
            return
        fi
    fi

    local generated
    generated="$(python3 -c 'import secrets; print(secrets.token_urlsafe(18))')"

    # Non-interactive path — just use the generated value.
    if [[ ! -t 0 ]] || [[ "${OGLAB_NONINTERACTIVE:-0}" == "1" ]]; then
        OGLAB_PASSWORD="$generated"
        info "Generated OGLAB_PASSWORD (non-interactive). See .env after setup."
        return
    fi

    echo ""
    echo -e "${BOLD}━━━ Lab password${RESET}"
    echo ""
    echo "  One password covers every login surface in the lab:"
    echo "    • code-server IDE  (http://127.0.0.1:8443)"
    echo "    • Open Notebook    (encrypts your research data)"
    echo ""
    echo "  Press Enter to accept a generated value, or type your own."
    echo ""
    read -rsp "  Password [generated]: " typed
    echo ""
    OGLAB_PASSWORD="${typed:-$generated}"
    if [[ -z "$typed" ]]; then
        info "Using generated password — saved to .env and lab.conf."
    fi
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

        rm -f .env.bak
        info ".env created with MODEL_BACKEND=${ACCEL}"
    else
        info ".env already exists — preserving model settings."
    fi

    # Password + add-on keys: always ensure they match OGLAB_PASSWORD.
    # Idempotent — safe to re-run on an existing .env.
    _set_env_var OGLAB_PASSWORD "$OGLAB_PASSWORD"
    _set_env_var OPEN_NOTEBOOK_ENCRYPTION_KEY "$OGLAB_PASSWORD"
}

# Set KEY=VALUE in .env, replacing (or uncommenting) any existing entry.
# Uses a python helper so arbitrary characters in VALUE don't break sed.
_set_env_var() {
    local key="$1" value="$2"
    python3 - "$key" "$value" <<'PY'
import pathlib, sys
key, value = sys.argv[1], sys.argv[2]
p = pathlib.Path(".env")
lines = p.read_text().splitlines() if p.exists() else []
out, replaced = [], False
for line in lines:
    stripped = line.lstrip("# ").rstrip()
    if stripped.startswith(f"{key}="):
        out.append(f"{key}={value}")
        replaced = True
    else:
        out.append(line)
if not replaced:
    if out and out[-1] != "":
        out.append("")
    out.append(f"{key}={value}")
p.write_text("\n".join(out) + "\n")
PY
}

# -----------------------------------------------------------------------------
# Runtime config files
# -----------------------------------------------------------------------------
setup_runtime_files() {
    cat > lab.conf << CONF
# OGLab runtime config — generated by setup.sh
PORTAL_PORT=8080
TERMINAL_PORT=7681
NOTEBOOK_PORT=8888
IDE_PORT=8443
IDE_PASSWORD=${OGLAB_PASSWORD}
BIND_ADDR=127.0.0.1
CONF
    info "lab.conf written"

    local cs_dir="${HOME}/.config/code-server"
    mkdir -p "$cs_dir"
    cat > "${cs_dir}/config.yaml" << YAML
bind-addr: 127.0.0.1:8443
auth: password
password: ${OGLAB_PASSWORD}
cert: false
YAML
    info "code-server config written"

    mkdir -p lab/data/goals lab/data/goals/history lab/data/consent lab/data/experiments lab/models
}

# -----------------------------------------------------------------------------
# Personal knowledge management scaffold
# -----------------------------------------------------------------------------
setup_pkb() {
    local pkb_root="lab/pkb"
    mkdir -p "$pkb_root"/{inbox,sources/{papers,articles,datasets},agents/{research,experiments,synthesis,recommendations},notes/scratch,compiled/{reports,summaries,exports},inference/{prompts,completions,chains}}
    [[ -f "$pkb_root/sources/bookmarks.md" ]] || cat > "$pkb_root/sources/bookmarks.md" << 'BOOKMARKS'
# Bookmarks
# Save URLs with a one-line description. One per line.
# Format: URL — description
BOOKMARKS
    [[ -f "$pkb_root/notes/journal.md" ]] || cat > "$pkb_root/notes/journal.md" << JOURNAL
# Lab Journal

A running log of what happened, what you learned, and what you're thinking.
Newest entries at the top.

---

## $(date +%Y-%m-%d)

Lab initialized with setup.sh.
JOURNAL
    [[ -f "$pkb_root/notes/ideas.md" ]] || cat > "$pkb_root/notes/ideas.md" << 'IDEAS'
# Ideas

Quick captures. Hunches. What-ifs. No pressure — just write.

- 
IDEAS
    info "PKB ready at $pkb_root"
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
# Capture intent + goal (interactive; writes bootstrap_goal.json)
# -----------------------------------------------------------------------------
capture_goal() {
    # Skip if non-interactive (CI, Docker, pipe)
    if [[ ! -t 0 ]] || [[ "${OGLAB_NONINTERACTIVE:-0}" == "1" ]]; then
        info "Non-interactive shell — skipping goal capture. Set LAB_INTENT + goal via portal later."
        return
    fi

    local goal_path="lab/data/goals/bootstrap_goal.json"
    if [[ -f "$goal_path" ]]; then
        info "Bootstrap goal already set — skipping. (Delete $goal_path to re-capture.)"
        return
    fi

    echo ""
    echo -e "${BOLD}━━━ Lab intent${RESET}"
    echo ""
    echo "  What kind of lab is this?"
    echo ""
    echo "    1) ai         — AI engineering, models, inference, toolchains"
    echo "    2) ml         — Machine learning, training, datasets, benchmarks"
    echo "    3) farming    — Crop science, soil, regional growing"
    echo "    4) business   — Market research, unit economics, competitive intel"
    echo "    5) education  — Learning science, curriculum, mastery"
    echo "    6) health     — Exercise, nutrition, sleep, wellness protocols"
    echo "    7) culinary   — Cooking technique, flavor chemistry, recipe dev"
    echo ""
    read -rp "  Choice [1-7, default 1]: " choice
    local intent intent_name
    case "${choice:-1}" in
        1|"") intent=ai;        intent_name="AI Engineer" ;;
        2)    intent=ml;        intent_name="ML Researcher" ;;
        3)    intent=farming;   intent_name="Farmer" ;;
        4)    intent=business;  intent_name="Analyst" ;;
        5)    intent=education; intent_name="Educator" ;;
        6)    intent=health;    intent_name="Health Researcher" ;;
        7)    intent=culinary;  intent_name="Culinary Scientist" ;;
        *)    intent=ai;        intent_name="AI Engineer" ;;
    esac

    echo ""
    echo -e "${BOLD}━━━ Research goal${RESET}"
    echo ""
    echo "  What do you want the lab to research? One sentence is fine."
    echo "  Examples:"
    echo "    • Find the best 8B model for code generation on a 32 GB Mac"
    echo "    • Grow peanuts in USDA zone 7 with minimal irrigation"
    echo "    • Master French pastry lamination technique"
    echo ""
    read -rp "  Goal: " goal
    if [[ -z "${goal// }" ]]; then
        warn "Empty goal — skipping capture. You can set one from the dashboard after ./oglab start."
        return
    fi

    echo ""
    echo -e "${BOLD}━━━ Work windows${RESET}"
    echo ""
    echo "  The lab scheduler has two modes:"
    echo "    ☀  active — light work only, lab stays responsive"
    echo "    🌙  heavy — experiments + deep GPU work (while you're away)"
    echo ""
    echo "  Press enter to accept the default active window, or type a"
    echo "  range like ${BOLD}08:00-22:00${RESET} (24-hour time, local timezone)."
    echo ""
    read -rp "  Active hours [08:00-22:00]: " active_hours
    read -rp "  Heavy  hours [22:00-08:00]: " heavy_hours
    active_hours="${active_hours:-08:00-22:00}"
    heavy_hours="${heavy_hours:-22:00-08:00}"

    mkdir -p "$(dirname "$goal_path")"
    python3 - "$goal_path" "$goal" "$intent" "$intent_name" <<'PY'
import json, sys, datetime
path, goal, intent, intent_name = sys.argv[1:5]
payload = {
    "goal": goal,
    "intent": intent,
    "intent_name": intent_name,
    "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
}
with open(path, "w") as f:
    json.dump(payload, f, indent=2)
PY

    # Persist intent + work windows to .env so the researcher honors them
    # on every run.
    if [[ -f .env ]]; then
        _set_env_var() {
            local key="$1" val="$2"
            if grep -q "^${key}=" .env; then
                sed -i.bak "s|^${key}=.*|${key}=${val}|" .env
            else
                echo "${key}=${val}" >> .env
            fi
        }
        _set_env_var LAB_INTENT "${intent}"
        _set_env_var LAB_INTENT_NAME "${intent_name}"
        _set_env_var LAB_ACTIVE_HOURS "${active_hours}"
        _set_env_var LAB_HEAVY_HOURS "${heavy_hours}"
        rm -f .env.bak
    fi

    info "Goal saved → $goal_path"
    info "Researcher will auto-start when you run ${BOLD}./oglab start${RESET}"
}

# -----------------------------------------------------------------------------
# Verify
# -----------------------------------------------------------------------------
verify() {
    info "Running smoke tests…"
    python3 -c "from oglab.router import ModelRouter; import oglab.portal.app; from oglab.pkb import scaffold; scaffold(); print('OK')" >/dev/null 2>&1 \
        && info "Smoke tests passed." \
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
    capture_password
    setup_env
    setup_runtime_files
    setup_pkb
    gentoo_notes
    wsl_notes
    download_model

    echo ""
    verify
    capture_goal

    echo ""
    echo -e "${BOLD}✓ Setup complete.${RESET}"
    info "Next step:  ${BOLD}./oglab start${RESET}  — portal + agents come online together"
    echo ""
}

main "$@"
