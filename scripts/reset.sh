#!/usr/bin/env bash
# =============================================================================
#  ${LAB_NAME} Reset — Clean wipe / selective reset
# =============================================================================
set -euo pipefail

BOLD="\033[1m"
RED="\033[0;31m"
GREEN="\033[0;32m"
YELLOW="\033[0;33m"
RESET="\033[0m"

info()  { echo -e "  ${GREEN}✓${RESET} $*"; }
warn()  { echo -e "  ${YELLOW}⚠${RESET} $*"; }
error() { echo -e "  ${RED}✗${RESET} $*"; }

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AUTO_CONFIRM="false"
DESTROY_LOG="/tmp/oglab-destroy.log"
cd "$REPO_ROOT"

# shellcheck disable=SC1091
[[ -f .env ]] && set -a && source .env && set +a
LAB_NAME="${LAB_NAME:-OGLab}"

# ── Stop running services ────────────────────────────────────────────
stop_services() {
    info "Stopping ${LAB_NAME} services..."
    local pids=()
    for proc in "uvicorn" "ttyd" "jupyter-lab" "jupyter-lab-script" "code-server"; do
        local p
        p=$(pgrep -f "$proc" 2>/dev/null || true)
        [[ -n "$p" ]] && pids+=($p)
    done
    if (( ${#pids[@]} > 0 )); then
        kill "${pids[@]}" 2>/dev/null || true
        info "Stopped ${#pids[@]} process(es)."
    else
        info "No running services found."
    fi
}

# ── Size report ──────────────────────────────────────────────────────
report_size() {
    local dir="$1"
    if [[ -d "$dir" ]]; then
        du -sh "$dir" 2>/dev/null | awk '{print $1}'
    else
        echo "0B"
    fi
}

# ── Reset modes ──────────────────────────────────────────────────────
reset_models() {
    local sz
    sz=$(report_size "lab/models")
    if [[ -d lab/models ]]; then
        warn "Removing lab/models/ (${sz})..."
        rm -rf lab/models
        info "Models removed."
    else
        info "No lab/models/ directory."
    fi
}

reset_data() {
    if [[ -d lab/data ]]; then
        local sz
        sz=$(report_size "lab/data")
        warn "Removing lab/data/ (${sz})..."
        rm -rf lab/data
        info "lab/data/ removed."
    fi
}

reset_plugins() {
    local plugins_dir="$HOME/.oglab/plugins"
    if [[ -d "$plugins_dir" ]]; then
        local sz
        sz=$(report_size "$plugins_dir")
        warn "Removing ${plugins_dir} (${sz})..."
        rm -rf "$plugins_dir"
        info "Plugins removed."
    else
        info "No plugins installed."
    fi
}

reset_env() {
    for f in .env lab.conf; do
        if [[ -f "$f" ]]; then
            warn "Removing ${f}..."
            rm -f "$f"
            info "${f} removed."
        fi
    done
    if [[ -d .venv ]]; then
        local sz
        sz=$(report_size ".venv")
        warn "Removing .venv/ (${sz})..."
        rm -rf .venv
        info "Virtual environment removed."
    fi
}

full_wipe() {
    stop_services
    reset_models
    reset_data
    reset_plugins
    reset_env
    # Also clean caches
    for dir in __pycache__ .pytest_cache oglab.egg-info; do
        find . -type d -name "$dir" -exec rm -rf {} + 2>/dev/null || true
    done
    find . -name "*.pyc" -delete 2>/dev/null || true
    info "Full wipe complete. Source code preserved."
    info "Run ${BOLD}./oglab setup${RESET} to rebuild."
}

destroy_lab() {
    stop_services

    local target_dir="$REPO_ROOT"
    local helper
    helper="$(mktemp /tmp/oglab-destroy.XXXXXX.sh)"

    cat > "$helper" <<EOF
#!/usr/bin/env bash
set -euo pipefail
sleep 2

rm -rf "$target_dir"
rm -rf "$HOME/.config/code-server"
rm -rf "$HOME/.local/share/code-server"
rm -rf "$HOME/.cache/code-server"
rm -rf "$HOME/.local/bin/code-server"
rm -rf "$HOME"/.local/lib/code-server-*
rm -rf "$HOME/.local/share/jupyter/runtime"
rm -rf "$HOME/.jupyter"
rm -rf /tmp/oglab*
rm -f /tmp/jpserver-*.json /tmp/jupyter-*.html
rm -f "$helper"
EOF

    chmod +x "$helper"
    nohup bash "$helper" > "$DESTROY_LOG" 2>&1 < /dev/null &

    warn "Destroy scheduled. This removes the entire local lab copy and its app data."
    info "Destroy log: ${DESTROY_LOG}"
    info "Source directory scheduled for deletion: ${target_dir}"
}

# ── Usage / menu ─────────────────────────────────────────────────────
usage() {
    echo ""
    echo -e "  ${BOLD}${LAB_NAME} Reset${RESET}"
    echo ""
    echo "  Usage: ./oglab reset [mode] [--yes]"
    echo ""
    echo "  Modes:"
    echo "    models    Remove downloaded models only"
    echo "    data      Remove experiments and data"
    echo "    plugins   Remove installed plugins"
    echo "    env       Remove .venv, .env, lab.conf"
    echo "    full      Complete wipe (everything except source code)"
    echo "    destroy   Delete the entire local lab copy and app data"
    echo "    stop      Just stop running services"
    echo ""
    echo "  If no mode given, interactive menu is shown."
    echo ""
}

interactive_menu() {
    echo ""
    echo -e "  ${BOLD}${LAB_NAME} Reset${RESET}"
    echo ""

    # Show sizes
    echo -e "  Current footprint:"
    for dir in lab/models lab/data lab/pkb .venv; do
        if [[ -d "$dir" ]]; then
            echo -e "    ${dir}/  $(report_size "$dir")"
        fi
    done
    echo ""

    echo "  What do you want to reset?"
    echo ""
    echo "    1) Models only"
    echo "    2) Data & experiments"
    echo "    3) Plugins"
    echo "    4) Environment (.venv, .env, configs)"
    echo "    5) Full wipe (all of the above)"
    echo "    6) Destroy this lab copy entirely"
    echo "    7) Just stop services"
    echo "    0) Cancel"
    echo ""
    read -rp "  Choice [0-7]: " choice

    case "${choice}" in
        1) confirm_and_run "models" reset_models ;;
        2) confirm_and_run "data & experiments" reset_data ;;
        3) confirm_and_run "plugins" reset_plugins ;;
        4) confirm_and_run "environment" reset_env ;;
        5) confirm_and_run "FULL WIPE" full_wipe ;;
        6) confirm_and_run "DESTROY LAB" destroy_lab ;;
        7) stop_services ;;
        0|"") echo "  Cancelled."; exit 0 ;;
        *) error "Invalid choice."; exit 1 ;;
    esac
}

confirm_and_run() {
    local label="$1"
    local fn="$2"
    if [[ "$AUTO_CONFIRM" == "true" ]]; then
        "$fn"
        return
    fi

    echo ""
    read -rp "  Confirm reset ${label}? [y/N] " yn
    case "${yn}" in
        [Yy]*) "$fn" ;;
        *)     echo "  Cancelled."; exit 0 ;;
    esac
}

# ── Entry point ──────────────────────────────────────────────────────
MODE=""
for arg in "$@"; do
    case "$arg" in
        --yes|-y) AUTO_CONFIRM="true" ;;
        *)
            if [[ -z "$MODE" ]]; then
                MODE="$arg"
            fi
            ;;
    esac
done

case "${MODE:-}" in
    models)  confirm_and_run "models" reset_models ;;
    data)    confirm_and_run "data & experiments" reset_data ;;
    plugins) confirm_and_run "plugins" reset_plugins ;;
    env)     confirm_and_run "environment" reset_env ;;
    full)    confirm_and_run "FULL WIPE" full_wipe ;;
    destroy) confirm_and_run "DESTROY LAB" destroy_lab ;;
    stop)    stop_services ;;
    -h|--help) usage; exit 0 ;;
    "")      interactive_menu ;;
    *)       usage; exit 1 ;;
esac

echo ""
info "Done."
