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

ollama_default_enabled() {
    [[ "$PLATFORM" == "macos" && "$ACCEL" == "mlx" ]] && return 1
    return 0
}

# Numbered checkpoint banner — every major section prints one so the
# user has a visible progress spine ("━━━ 3/10  Python environment").
step()  { echo ""; echo -e "${BOLD}━━━ $*${RESET}"; echo ""; }

MODEL_MLX_ID="mlx-community/Qwen3-8B-4bit"
MODEL_HF_ID="Qwen/Qwen3-8B"
MODEL_GGUF_ID="Qwen/Qwen3-8B-GGUF"
AEROLLM_MODEL_ID="zai-org/GLM-5.1"
AEROLLM_PACKAGE_SPEC="git+https://github.com/cdarnell/aerollm@main"

# Unified password — set by capture_password() below. One secret covers:
#   - code-server (IDE) login
#   - Open Notebook data encryption key
#   - future auth proxy
OGLAB_PASSWORD=""

load_pyproject_metadata() {
    local assignments
    assignments="$(python3 - <<'PY'
from pathlib import Path
import shlex

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

data = tomllib.loads(Path("pyproject.toml").read_text())
tool = data.get("tool", {}).get("oglab", {})
models = tool.get("models", {})
sources = tool.get("package-sources", {})
values = {
    "MODEL_MLX_ID": str(models.get("mlx", "")),
    "MODEL_HF_ID": str(models.get("cuda", "")),
    "MODEL_GGUF_ID": str(models.get("cpu", "")),
    "AEROLLM_MODEL_ID": str(models.get("aerollm", "")),
    "AEROLLM_PACKAGE_SPEC": str(sources.get("aerollm", "")),
}
for key, value in values.items():
    if value:
        print(f"{key}={shlex.quote(value)}")
PY
)" || error "Could not read pyproject.toml metadata. Make sure Python can import tomllib or tomli."
    eval "$assignments"
    info "Loaded package and model metadata from ${BOLD}pyproject.toml${RESET}."
}

install_pyproject_extra() {
    local extra_name="$1"
    local label="$2"
    local log="${REPO_ROOT:-$PWD}/setup.log"
    info "Installing ${label} from pyproject extra '${extra_name}'…"
    pip install -q -e ".[${extra_name}]" 2>>"$log" || {
        warn "Install failed for pyproject extra '${extra_name}'. Last 20 lines of setup.log:"
        tail -n 20 "$log" | sed 's/^/    /' >&2
        error "Install failed for '${extra_name}'. See setup.log, then re-run: ./oglab setup"
    }
}

# -----------------------------------------------------------------------------
# Detect OS / platform
# -----------------------------------------------------------------------------
detect_platform() {
    step "1/10  Detecting hardware"

    # Guard: PowerShell / Git-Bash / MSYS shells running on Windows itself.
    # These aren't supported — users must install WSL2 Ubuntu and run from
    # there. Detect via environment variables those shells set.
    if [[ -n "${MSYSTEM:-}" ]] || [[ -n "${WT_SESSION:-}" && "$(uname -s)" == MINGW* ]]; then
        error "Windows native shell detected. Install WSL2 + Ubuntu (wsl --install in PowerShell), then run ./oglab setup from inside the Ubuntu app."
    fi

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
                warn "Intel Mac detected — using CPU backend (slower inference). MLX requires Apple Silicon."
            fi
            ;;
        Linux)
            # Check if running inside WSL
            if grep -qiE '(microsoft|wsl)' /proc/version 2>/dev/null; then
                PLATFORM="wsl"
                # WSL1 is unsupported — the kernel lacks /dev/dxg and
                # several syscalls pip + torch need.
                if ! grep -qi 'WSL2' /proc/version 2>/dev/null; then
                    error "WSL1 detected — OGLab requires WSL2. From PowerShell (admin):  wsl --set-version Ubuntu 2"
                fi
            # Check for Gentoo
            elif [[ -f /etc/gentoo-release ]]; then
                PLATFORM="gentoo"
            elif [[ -f /etc/fedora-release ]]; then
                PLATFORM="fedora"
            elif [[ -f /etc/arch-release ]]; then
                PLATFORM="arch"
            else
                PLATFORM="linux"
            fi

            # GPU detection
            if command -v nvidia-smi &>/dev/null && nvidia-smi &>/dev/null; then
                ACCEL="cuda"
                # WSL-specific: flag if the user installed the Linux
                # Nvidia driver inside WSL instead of relying on the
                # Windows-side driver.
                if [[ "$PLATFORM" == "wsl" ]] && [[ ! -f /usr/lib/wsl/lib/libcuda.so && ! -f /usr/lib/wsl/lib/libcuda.so.1 ]]; then
                    warn "CUDA detected but /usr/lib/wsl/lib/libcuda.so* is missing."
                    warn "If you installed 'nvidia-drivers' inside WSL, remove them —"
                    warn "WSL gets CUDA from the Windows-side driver only."
                fi
            else
                ACCEL="cpu"
            fi
            ;;
        *)
            error "Unsupported OS: $os. See docs/LINUX.md for the 'vibe integrate' recipe — point an AI agent at scripts/setup.sh and it'll port the 20 lines that matter."
            ;;
    esac

    info "Platform: ${BOLD}${PLATFORM}${RESET}  |  Accelerator: ${BOLD}${ACCEL}${RESET}"

    # Port-conflict pre-flight — warns if any lab port is already bound.
    check_ports
    # Sudo-cache pre-flight for platforms that need it — warns only, so
    # the user doesn't get surprised by a password prompt 90 seconds in.
    check_sudo
    # Homebrew guard — on macOS, every install_services call needs brew.
    if [[ "$PLATFORM" == "macos" ]] && ! command -v brew &>/dev/null; then
        error "Homebrew is required on macOS. Install it, then re-run:
  /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
    fi
}

# Lightweight port-conflict pre-flight. Warns (not errors) so users can
# still complete setup even with conflicting services; the fix lives in
# lab.conf and is spelled out in the warning.
check_ports() {
    local ports=(8080 7681 8888 8443 11434 7414)
    local in_use=()
    for p in "${ports[@]}"; do
        if command -v lsof &>/dev/null; then
            if lsof -iTCP:"$p" -sTCP:LISTEN -P -n &>/dev/null; then
                in_use+=("$p")
            fi
        elif command -v ss &>/dev/null; then
            if ss -ltn "sport = :$p" 2>/dev/null | tail -n +2 | grep -q .; then
                in_use+=("$p")
            fi
        fi
    done
    if (( ${#in_use[@]} > 0 )); then
        warn "Ports already in use: ${in_use[*]}"
        warn "Edit lab.conf (PORTAL_PORT / TERMINAL_PORT / NOTEBOOK_PORT / IDE_PORT) before ./oglab start."
    fi
}

# Sudo-cache warning — brew/apt/dnf branches in install_services all
# call sudo. Tell the user up front so the password prompt in the
# middle of a long install doesn't surprise them.
check_sudo() {
    case "$PLATFORM" in
        linux|wsl|fedora|arch|gentoo)
            if ! sudo -v -n 2>/dev/null; then
                warn "sudo cache is empty — setup may prompt for your password mid-run."
            fi
            ;;
    esac
}

# -----------------------------------------------------------------------------
# Python environment
# -----------------------------------------------------------------------------
ensure_python() {
    step "3/10  Python environment (.venv + core deps)"
    if ! command -v python3 &>/dev/null; then
        case "$PLATFORM" in
            gentoo)  error "Install Python, then re-run ./oglab setup:  emerge -av dev-lang/python" ;;
            macos)   error "Install Python, then re-run ./oglab setup:  brew install python@3.11" ;;
            *)       error "Install Python 3.10+ and re-run ./oglab setup." ;;
        esac
    fi

    local pyver pymajor pyminor
    pyver="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
    pymajor="${pyver%.*}"
    pyminor="${pyver#*.}"
    info "Python $pyver found"

    # Version gate: too old (< 3.10) fails hard; too new (>= 3.13) warns
    # since some accelerator wheels (mlx, vllm, torch) lag behind.
    if (( pymajor < 3 )) || (( pymajor == 3 && pyminor < 10 )); then
        error "Python $pyver is too old. Install Python 3.10-3.12 and re-run ./oglab setup."
    fi
    if (( pymajor == 3 && pyminor >= 13 )); then
        warn "Python $pyver is newer than we test (3.10-3.12)."
        warn "If pip installs fail, install python@3.11 and delete .venv before re-running."
    fi

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
    info "Installing core Python packages from ${BOLD}pyproject.toml${RESET} (one-time, ~90 s)…"
    local log="${REPO_ROOT:-$PWD}/setup.log"
    pip install -q -e ".[dev,notebook]" 2>>"$log" || {
        warn "Core deps install failed. Last 20 lines of setup.log:"
        tail -n 20 "$log" | sed 's/^/    /' >&2
        error "pip install failed. See setup.log, then re-run: ./oglab setup"
    }
    info "Core dependencies installed, including Lance memory support and notebook tooling."
}

# -----------------------------------------------------------------------------
# Platform-specific accelerator deps
# -----------------------------------------------------------------------------
install_accel_deps() {
    case "$ACCEL" in
        mlx)
            install_pyproject_extra "mlx" "MLX accelerator runtime"
            ;;
        cuda)
            install_pyproject_extra "cuda" "CUDA / vLLM runtime"
            ;;
        cpu)
            warn "No GPU detected — installing CPU inference runtime from pyproject."
            install_pyproject_extra "cpu" "CPU inference runtime"
            ;;
    esac

    # AeroLLM — "deep" backend. Multi-threaded prefetched layer
    # streaming; loads giant models (70B+) block-by-block from disk
    # so they fit in modest RAM. The dashboard chat card has a toggle
    # that routes one message through AeroLLM at a time.
    #
    # Opt-out with OGLAB_SKIP_AEROLLM=1 — it's a several-hundred-MB
    # install (torch + transformers) if your accel didn't already
    # pull those in.
    #
    # Install source is declared in pyproject.toml under
    # [tool.oglab.package-sources]. A one-off env override remains
    # available for local development only.
    #
    # Default deep model is Meta's gated Llama 3.1 70B. Setup does not
    # auto-download it: users must accept the HF license and authenticate
    # first, then pull the weights explicitly.
    if [[ "${OGLAB_SKIP_AEROLLM:-0}" != "1" ]]; then
        local aerollm_pkg="${OGLAB_AEROLLM_PACKAGE_OVERRIDE:-$AEROLLM_PACKAGE_SPEC}"
        info "Installing AeroLLM (${aerollm_pkg}) — source declared in ${BOLD}pyproject.toml${RESET}…"
        if pip install -q "$aerollm_pkg" 2>&1 | tail -5; then
            info "AeroLLM ready. Dashboard chat card has a 'Deep model' toggle."
            if [[ -n "${OGLAB_AEROLLM_PACKAGE_OVERRIDE:-}" ]]; then
                warn "Using OGLAB_AEROLLM_PACKAGE_OVERRIDE for this run only."
            fi
        else
            echo -e "${RED}[oglab]${RESET} To bypass: OGLAB_SKIP_AEROLLM=1 ./oglab setup" >&2
            error "AeroLLM install failed — check [tool.oglab.package-sources] in pyproject.toml or your OGLAB_AEROLLM_PACKAGE_OVERRIDE"
        fi
    else
        info "Skipping AeroLLM (OGLAB_SKIP_AEROLLM=1)."
    fi
}

# -----------------------------------------------------------------------------
# Optional services — the embedded browser terminal.
# ttyd powers /terminal on the portal. Without it, the terminal tab shows
# install instructions instead of a broken iframe. We try to install it
# opportunistically using whatever package manager is available; failures
# are logged and the rest of setup continues.
# -----------------------------------------------------------------------------
install_services() {
    step "2/10  System packages (ttyd, tmux, agent-browser, optional ollama)"
    # ttyd — the browser terminal.
    if ! command -v ttyd &>/dev/null; then
        case "$PLATFORM" in
            macos)
                if command -v brew &>/dev/null; then
                    info "Installing ttyd via Homebrew…"
                    brew install ttyd 2>&1 | tail -3 || warn "ttyd install failed — /terminal will show install help instead."
                else
                    warn "Homebrew not found — skipping ttyd. Install later: brew install ttyd"
                fi
                ;;
            wsl|ubuntu|debian)
                if command -v apt &>/dev/null; then
                    info "Installing ttyd via apt…"
                    sudo apt-get install -y -q ttyd 2>&1 | tail -3 || warn "ttyd install failed — install later: sudo apt install ttyd"
                fi
                ;;
            gentoo)
                command -v emerge &>/dev/null && info "ttyd on Gentoo: sudo emerge -av www-apps/ttyd"
                ;;
            *)
                warn "Unknown platform — install ttyd manually for browser terminal support."
                ;;
        esac
    else
        info "ttyd already installed ($(ttyd --version 2>&1 | head -1))"
    fi

    # tmux — terminal persistence. Without it, the browser terminal
    # iframe loses scrollback on every nav click. With it, ttyd attaches
    # to a named tmux session that survives reconnects.
    if ! command -v tmux &>/dev/null; then
        case "$PLATFORM" in
            macos)
                command -v brew &>/dev/null && info "Installing tmux via Homebrew…" \
                    && brew install tmux 2>&1 | tail -3 \
                    || warn "tmux not installed — terminal scrollback won't persist across iframe reloads."
                ;;
            wsl|ubuntu|debian)
                command -v apt &>/dev/null && info "Installing tmux via apt…" \
                    && sudo apt-get install -y -q tmux 2>&1 | tail -3 \
                    || warn "tmux not installed — install later: sudo apt install tmux"
                ;;
            *)
                warn "tmux not installed — terminal sessions won't persist across reloads."
                ;;
        esac
    else
        info "tmux already installed ($(tmux -V 2>&1))"
    fi

    # agent-browser — web research agent for the Knowledge tab.
    if ! command -v agent-browser &>/dev/null; then
        if command -v npm &>/dev/null; then
            info "Installing agent-browser…"
            npm install -g agent-browser 2>&1 | tail -3 || warn "agent-browser install failed — Knowledge tab browse will be unavailable."
            command -v agent-browser &>/dev/null && agent-browser install 2>&1 | tail -3 || true
        else
            warn "npm not found — skipping agent-browser. Install Node.js to enable web research."
        fi
    else
        info "agent-browser already installed"
    fi

    # Ollama — optional local OpenAI-compatible LLM server. On Apple
    # Silicon, OGLab's primary local inference path is direct MLX via
    # mlx-lm, so we skip Ollama by default unless explicitly enabled.
    # It remains useful for surfaces that want an HTTP API, like Open
    # Notebook or other OpenAI-compatible tools.
    local ollama_enabled=1
    if ! ollama_default_enabled && [[ "${OGLAB_ENABLE_OLLAMA:-0}" != "1" ]]; then
        ollama_enabled=0
        info "Apple Silicon detected — MLX/mlx-lm is the default local runtime."
        info "Skipping Ollama install by default. Enable it with OGLAB_ENABLE_OLLAMA=1 if you want a local OpenAI-compatible API too."
    fi

    if [[ "$ollama_enabled" == "0" ]]; then
        if command -v ollama &>/dev/null; then
            info "Ollama already installed ($(ollama --version 2>&1 | head -1))"
        fi
        return
    fi

    if ! command -v ollama &>/dev/null; then
        case "$PLATFORM" in
            macos)
                if command -v brew &>/dev/null; then
                    info "Installing Ollama…"
                    brew install ollama 2>&1 | tail -3 || warn "Ollama install failed — Open Notebook AI features will require manual setup."
                else
                    warn "Homebrew not found — install Ollama manually: https://ollama.com"
                fi
                ;;
            *)
                info "Install Ollama for local AI features: https://ollama.com"
                ;;
        esac
    else
        info "Ollama already installed ($(ollama --version 2>&1 | head -1))"
    fi

    # Pull a default model for Ollama if none exist. Skippable for
    # slow networks or locked-down school machines via OGLAB_SKIP_OLLAMA=1.
    if command -v ollama &>/dev/null; then
        if [[ "${OGLAB_SKIP_OLLAMA:-0}" == "1" ]]; then
            warn "OGLAB_SKIP_OLLAMA=1 — skipping qwen3:8b pull. Run later: ollama pull qwen3:8b"
            return
        fi
        local model_count
        model_count=$(ollama list 2>/dev/null | tail -n +2 | wc -l | tr -d ' ') || model_count="0"
        if [[ "$model_count" == "0" ]]; then
            info "Pulling default Ollama model (qwen3:8b, ~5 GB) — this may take 2-5 minutes…"
            info "Skip next time with OGLAB_SKIP_OLLAMA=1 if bandwidth is tight."
            if ! timeout 900 ollama pull qwen3:8b 2>&1 | tail -5; then
                warn "Model pull failed or timed out. Run manually: ollama pull qwen3:8b"
            fi
        else
            info "Ollama has $model_count model(s) available"
        fi
    fi
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
    echo "  See docs/LINUX.md for Gentoo notes."
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
# Brand — name your lab. Captured once, persisted to .env, every future run
# reuses it. Fork → rename → you have your own product.
# -----------------------------------------------------------------------------
capture_brand() {
    # If .env already has a LAB_NAME we respect it and move on.
    if [[ -f .env ]] && grep -q '^LAB_NAME=' .env; then
        local existing
        existing="$(grep -E '^LAB_NAME=' .env | head -n1 | cut -d= -f2- | tr -d '"')"
        if [[ -n "$existing" ]]; then
            LAB_NAME="$existing"
            info "Lab name: ${BOLD}${LAB_NAME}${RESET} (from .env)"
            return
        fi
    fi

    if [[ ! -t 0 ]] || [[ "${OGLAB_NONINTERACTIVE:-0}" == "1" ]]; then
        LAB_NAME="OGLab"
        info "Non-interactive — using default lab name: OGLab"
        return
    fi

    step "4/10  Name your lab"
    echo "  This is how the dashboard, portal, wiki, and every banner will"
    echo "  refer to your lab. Pick something that feels like yours —"
    echo "  ${BOLD}PeanutLab${RESET}, ${BOLD}Atlas${RESET}, ${BOLD}Workshop${RESET}, or keep the default."
    echo ""
    read -rp "  Lab name [OGLab]: " LAB_NAME
    LAB_NAME="${LAB_NAME:-OGLab}"

    # Lowercase short name for info tags and process titles.
    LAB_SHORT_NAME="$(echo "$LAB_NAME" | tr '[:upper:]' '[:lower:]' | tr -s '[:space:]' '-' | tr -cd 'a-z0-9-')"

    echo ""
    read -rp "  One-line tagline [AI Lab Blueprint]: " LAB_TAGLINE
    LAB_TAGLINE="${LAB_TAGLINE:-AI Lab Blueprint}"

    info "Lab name: ${BOLD}${LAB_NAME}${RESET}"
}

# -----------------------------------------------------------------------------
# Unified passphrase — one secret for IDE + Open Notebook + future auth.
#
# Contract:
#   - Interactive TTY + no existing passphrase → silent prompt w/ confirm
#   - Interactive TTY + existing passphrase     → ask "keep or rotate"
#   - Non-TTY / OGLAB_NONINTERACTIVE=1          → auto-generate, warn loudly
#   - Empty final value                         → hard-fail (caller aborts)
#
# The generated token and the final OGLAB_PASSWORD are echoed in the
# end-of-setup banner so users never have to grep .env to find it.
# -----------------------------------------------------------------------------
capture_password() {
    local existing=""
    if [[ -f .env ]]; then
        existing="$(grep -E '^OGLAB_PASSWORD=' .env | head -n1 | cut -d= -f2-)"
        # Guard against the placeholder from .env.example.
        if [[ "$existing" == "change-me" ]]; then existing=""; fi
    fi

    # Reuse path — ask the user explicitly instead of silent reuse.
    if [[ -n "$existing" ]]; then
        if [[ ! -t 0 ]] || [[ "${OGLAB_NONINTERACTIVE:-0}" == "1" ]]; then
            OGLAB_PASSWORD="$existing"
            info "Reusing existing passphrase from .env (non-interactive)."
            return
        fi
        step "5/10  Lab passphrase"
        echo "  An existing passphrase is already configured in .env."
        echo "  Press Enter to keep it, or type ${BOLD}new${RESET} to rotate it."
        echo ""
        local choice
        read -rp "  Keep existing? [Y/new]: " choice || choice=""
        case "${choice,,}" in
            ""|y|yes|keep)
                OGLAB_PASSWORD="$existing"
                info "Keeping existing passphrase."
                return
                ;;
            *)
                info "Rotating passphrase — you'll set a new one now."
                ;;
        esac
    fi

    local generated
    generated="$(python3 -c 'import secrets; print(secrets.token_urlsafe(18))')"

    # Non-interactive path — auto-generate, but warn loudly so the line
    # survives terminal scrollback. The final banner echoes the value.
    if [[ ! -t 0 ]] || [[ "${OGLAB_NONINTERACTIVE:-0}" == "1" ]]; then
        OGLAB_PASSWORD="$generated"
        warn "Non-interactive shell — passphrase auto-generated."
        warn "The final setup banner will print the value — do not miss it."
        return
    fi

    step "5/10  Lab passphrase"
    echo "  One passphrase secures every surface in the lab:"
    echo "    • code-server IDE   (http://127.0.0.1:8443)"
    echo "    • Open Notebook     (encrypts your research data at rest)"
    echo "    • any future auth   (portal, wiki, agents)"
    echo ""
    echo "  Press Enter to accept a generated value, or type your own."
    echo "  ${BOLD}Input is hidden.${RESET} You will be asked to confirm."
    echo ""
    local typed="" confirm=""
    while true; do
        read -rsp "  Passphrase [generated]: " typed; echo
        if [[ -z "$typed" ]]; then
            OGLAB_PASSWORD="$generated"
            info "Using generated passphrase."
            return
        fi
        read -rsp "  Confirm passphrase      : " confirm; echo
        if [[ "$typed" == "$confirm" ]]; then
            OGLAB_PASSWORD="$typed"
            info "Passphrase set."
            return
        fi
        warn "Passphrases did not match — try again (or press Enter to accept generated)."
    done
}

# -----------------------------------------------------------------------------
# .env file
# -----------------------------------------------------------------------------
setup_env() {
    step "6/10  Configuration files (.env + lab.conf)"
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

        sed -i.bak "s|^AEROLLM_MODEL=.*|AEROLLM_MODEL=${AEROLLM_MODEL_ID}|" .env

        rm -f .env.bak
        info ".env created with MODEL_BACKEND=${ACCEL}"
    else
        info ".env already exists — preserving model settings."
    fi

    # Passphrase + add-on keys: always ensure they match OGLAB_PASSWORD.
    # Idempotent — safe to re-run on an existing .env.
    if [[ -z "$OGLAB_PASSWORD" ]]; then
        error "Passphrase capture failed — OGLAB_PASSWORD is empty. Re-run: ./oglab setup"
    fi
    _set_env_var OGLAB_PASSWORD "$OGLAB_PASSWORD"
    _set_env_var OPEN_NOTEBOOK_ENCRYPTION_KEY "$OGLAB_PASSWORD"
    info "Passphrase written to .env (OGLAB_PASSWORD + OPEN_NOTEBOOK_ENCRYPTION_KEY)"

    # Persist brand fields so every subsequent run reads the user's choice.
    if [[ -n "${LAB_NAME:-}" ]]; then
        _set_env_var LAB_NAME "$LAB_NAME"
        _set_env_var LAB_SHORT_NAME "${LAB_SHORT_NAME:-$(echo "$LAB_NAME" | tr '[:upper:]' '[:lower:]')}"
        _set_env_var LAB_TAGLINE "${LAB_TAGLINE:-AI Lab Blueprint}"
    fi
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
# OGLab runtime config — regenerated by ./oglab setup on every run.
# To change values, edit .env instead (this file is overwritten).
PORTAL_PORT=8080
TERMINAL_PORT=7681
NOTEBOOK_PORT=8888
IDE_PORT=8443
MLX_OPENAI_PORT=11435
IDE_PASSWORD=${OGLAB_PASSWORD}
BIND_ADDR=127.0.0.1
CONF
    info "lab.conf written"

    local cs_dir="${HOME}/.config/code-server"
    local cs_cfg="${cs_dir}/config.yaml"
    mkdir -p "$cs_dir"
    if [[ -f "$cs_cfg" ]]; then
        local prev
        prev="$(grep -E '^password:' "$cs_cfg" | head -n1 | cut -d' ' -f2- || true)"
        if [[ -n "$prev" && "$prev" != "$OGLAB_PASSWORD" ]]; then
            warn "Overwriting existing code-server password in $cs_cfg"
        fi
    fi
    cat > "$cs_cfg" << YAML
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
    step "7/10  Knowledge base scaffold (lab/pkb/)"
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
    step "8/10  AI models (starter model for ${ACCEL})"
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

    echo ""
    warn "Optional deep-chat model for AeroLLM: ${AEROLLM_MODEL_ID}"
    warn "Meta Llama is gated — accept the Hugging Face license first, then authenticate with huggingface-cli login or HF_TOKEN."
    echo "  huggingface-cli download ${AEROLLM_MODEL_ID} --local-dir lab/models/Llama-3.1-70B --local-dir-use-symlinks False"
    echo "  # then set AEROLLM_MODEL=meta-llama/Llama-3.1-70B in .env and run ./oglab restart"
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

    step "9/10  Lab intent & first research goal"
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
    echo -e "  ${BOLD}─── Research goal ───${RESET}"
    echo ""

    # For the AI Engineer intent we ship a signature goal —
    # "optimize AeroLLM" — pre-filled as the default. Press Enter to
    # accept it; otherwise type a custom goal. Other intents still
    # get the free-form prompt.
    local default_goal=""
    if [[ "$intent" == "ai" ]]; then
        default_goal="Optimize AeroLLM's tokens-per-minute on frontier-scale open models (Qwen3-235B, DeepSeek-V3, GLM-5.1) running locally. Measure baseline, sweep prefetch + mixed-precision knobs, compare before/after, contribute wins upstream."
        echo "  Press Enter to accept the lab's signature research goal —"
        echo "  ${BOLD}Optimize AeroLLM${RESET} (tune the frontier-model"
        echo "  inference engine), or type a custom one."
        echo ""
        echo "  See lab/pkb/research/program.md for the full plan."
    else
        echo "  What do you want the lab to research? One sentence is fine."
        echo "  Examples:"
        echo "    • Find the best 8B model for code generation on a 32 GB Mac"
        echo "    • Grow peanuts in USDA zone 7 with minimal irrigation"
        echo "    • Master French pastry lamination technique"
    fi
    echo ""
    read -rp "  Goal${default_goal:+ [Enter for default]}: " goal
    if [[ -z "${goal// }" && -n "$default_goal" ]]; then
        goal="$default_goal"
        info "Using the lab's signature research goal (optimize AeroLLM)."
    elif [[ -z "${goal// }" ]]; then
        warn "Empty goal — skipping capture. You can set one from the dashboard after ./oglab start."
        return
    fi

    echo ""
    echo -e "  ${BOLD}─── Work windows ───${RESET}"
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
    # on every run. Uses the file-scope _set_env_var (Python-backed,
    # handles commented forms and arbitrary values correctly).
    if [[ -f .env ]]; then
        _set_env_var LAB_INTENT "${intent}"
        _set_env_var LAB_INTENT_NAME "${intent_name}"
        _set_env_var LAB_ACTIVE_HOURS "${active_hours}"
        _set_env_var LAB_HEAVY_HOURS "${heavy_hours}"
    fi

    info "Goal saved → $goal_path"
    info "Researcher will auto-start when you run ${BOLD}./oglab start${RESET}"
}

# -----------------------------------------------------------------------------
# validate_env — sanity-check the .env we just wrote. Catches the exact
# failure mode the user reported: a stale .env missing OGLAB_PASSWORD,
# or a divergent IDE_PASSWORD in lab.conf. Called from main() after
# setup_env + setup_runtime_files.
# -----------------------------------------------------------------------------
validate_env() {
    local missing=()
    local required=(MODEL_BACKEND OGLAB_PASSWORD OPEN_NOTEBOOK_ENCRYPTION_KEY LAB_NAME)
    for key in "${required[@]}"; do
        if ! grep -q "^${key}=" .env 2>/dev/null; then
            missing+=("$key")
        fi
    done
    if (( ${#missing[@]} > 0 )); then
        error "Missing required keys in .env: ${missing[*]}. Re-run: ./oglab setup"
    fi

    # Detect passphrase drift between .env and lab.conf — the current
    # user's case (IDE_PASSWORD=Austin34$, OPEN_NOTEBOOK_ENCRYPTION_KEY=Auatin34$).
    local env_pw conf_pw
    env_pw="$(grep -E '^OGLAB_PASSWORD=' .env | head -n1 | cut -d= -f2-)"
    if [[ -f lab.conf ]]; then
        conf_pw="$(grep -E '^IDE_PASSWORD=' lab.conf | head -n1 | cut -d= -f2-)"
        if [[ -n "$env_pw" && -n "$conf_pw" && "$env_pw" != "$conf_pw" ]]; then
            warn "Passphrase drift detected between .env and lab.conf — resyncing."
            sed -i.bak "s|^IDE_PASSWORD=.*|IDE_PASSWORD=${env_pw}|" lab.conf
            rm -f lab.conf.bak
        fi
    fi
    info "Environment validated."
}

# -----------------------------------------------------------------------------
# Verify
# -----------------------------------------------------------------------------
verify() {
    step "10/10  Verification"
    info "Running smoke tests…"
    local log="${REPO_ROOT:-$PWD}/setup.log"
    if python3 -c "from oglab.router import ModelRouter; import oglab.portal.app; from oglab.pkb import scaffold; scaffold(); print('OK')" >>"$log" 2>&1; then
        info "Smoke tests passed."
    else
        warn "Smoke test failed. Last 20 lines of setup.log:"
        tail -n 20 "$log" | sed 's/^/    /' >&2
        error "Inspect setup.log and re-run: ./oglab setup"
    fi
}

# =============================================================================
# Main
# =============================================================================
main() {
    echo ""
    echo -e "${BOLD}🧪 OGLab — AI Lab Blueprint Setup${RESET}"
    echo ""
    echo "  Local-first AI lab. Pick a name, capture a goal, start researching."
    echo ""
    echo "============================================="
    echo ""

    # Ordering matches the 1/10 → 10/10 banner sequence:
    #   1/10 detect_platform
    #   2/10 install_services     (OS packages — needs brew/apt, no python)
    #   3/10 ensure_python + install_core_deps + load_pyproject_metadata + install_accel_deps
    #   4/10 capture_brand
    #   5/10 capture_password
    #   6/10 setup_env + setup_runtime_files + validate_env
    #   7/10 setup_pkb
    #   8/10 download_model
    #   9/10 capture_goal
    #  10/10 verify
    detect_platform
    install_services
    ensure_python
    install_core_deps
    load_pyproject_metadata
    install_accel_deps
    capture_brand
    capture_password
    setup_env
    setup_runtime_files
    validate_env
    setup_pkb
    gentoo_notes
    wsl_notes
    download_model
    capture_goal

    echo ""
    verify

    echo ""
    echo -e "${BOLD}━━━ ✓ Setup complete${RESET}"
    echo ""
    echo "  Next steps:"
    echo -e "    1) Start the lab:      ${BOLD}./oglab start${RESET}"
    echo -e "    2) Open the dashboard: ${BOLD}http://127.0.0.1:${PORTAL_PORT:-8080}${RESET}"
    echo -e "    3) Type your goal and click ${BOLD}Run Research${RESET}"
    echo ""
    echo "  Your lab passphrase (unlocks the IDE at :${IDE_PORT:-8443}"
    echo "  and encrypts Open Notebook data):"
    echo ""
    echo -e "        ${BOLD}${OGLAB_PASSWORD}${RESET}"
    echo ""
    echo "  Also saved in:"
    echo "    .env        →  OGLAB_PASSWORD, OPEN_NOTEBOOK_ENCRYPTION_KEY"
    echo "    lab.conf    →  IDE_PASSWORD"
    echo ""
    echo "  Treat it like any password — don't commit .env to git."
    echo "  To rotate later: ./oglab setup  (answer 'new' when prompted)"
    echo ""
}

main "$@"
