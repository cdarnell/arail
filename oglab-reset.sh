#!/usr/bin/env bash
# =============================================================================
#  OGLab Reset — Clean wipe / selective reset
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

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── Stop running services ────────────────────────────────────────────
stop_services() {
    info "Stopping OGLab services..."
    if [[ -f start.sh ]]; then
        # Extract PIDs from any running OGLab processes
        local pids=()
        for proc in "uvicorn" "ttyd" "jupyter" "code-server"; do
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
    else
        info "No start.sh — nothing to stop."
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
    sz=$(report_size "models")
    if [[ -d models ]]; then
        warn "Removing models/ (${sz})..."
        rm -rf models
        info "Models removed."
    else
        info "No models/ directory."
    fi
}

reset_data() {
    for dir in data experiments; do
        if [[ -d "$dir" ]]; then
            local sz
            sz=$(report_size "$dir")
            warn "Removing ${dir}/ (${sz})..."
            rm -rf "$dir"
            info "${dir}/ removed."
        fi
    done
}

reset_plugins() {
    if [[ -d plugins ]]; then
        local sz
        sz=$(report_size "plugins")
        warn "Removing plugins/ (${sz})..."
        rm -rf plugins
        info "Plugins removed."
    else
        info "No plugins/ directory."
    fi
}

reset_env() {
    for f in .env lab.conf start.sh; do
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
    info "Run ${BOLD}bash bootstrap.sh${RESET} to rebuild."
}

# ── Usage / menu ─────────────────────────────────────────────────────
usage() {
    echo ""
    echo -e "  ${BOLD}OGLab Reset${RESET}"
    echo ""
    echo "  Usage: bash oglab-reset.sh [mode]"
    echo ""
    echo "  Modes:"
    echo "    models    Remove downloaded models only"
    echo "    data      Remove experiments and data"
    echo "    plugins   Remove installed plugins"
    echo "    env       Remove .venv, .env, lab.conf, start.sh"
    echo "    full      Complete wipe (everything except source code)"
    echo "    stop      Just stop running services"
    echo ""
    echo "  If no mode given, interactive menu is shown."
    echo ""
}

interactive_menu() {
    echo ""
    echo -e "  ${BOLD}OGLab Reset${RESET}"
    echo ""

    # Show sizes
    echo -e "  Current footprint:"
    for dir in models data experiments plugins .venv; do
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
    echo "    6) Just stop services"
    echo "    0) Cancel"
    echo ""
    read -rp "  Choice [0-6]: " choice

    case "${choice}" in
        1) confirm_and_run "models" reset_models ;;
        2) confirm_and_run "data & experiments" reset_data ;;
        3) confirm_and_run "plugins" reset_plugins ;;
        4) confirm_and_run "environment" reset_env ;;
        5) confirm_and_run "FULL WIPE" full_wipe ;;
        6) stop_services ;;
        0|"") echo "  Cancelled."; exit 0 ;;
        *) error "Invalid choice."; exit 1 ;;
    esac
}

confirm_and_run() {
    local label="$1"
    local fn="$2"
    echo ""
    read -rp "  Confirm reset ${label}? [y/N] " yn
    case "${yn}" in
        [Yy]*) "$fn" ;;
        *)     echo "  Cancelled."; exit 0 ;;
    esac
}

# ── Entry point ──────────────────────────────────────────────────────
case "${1:-}" in
    models)  confirm_and_run "models" reset_models ;;
    data)    confirm_and_run "data & experiments" reset_data ;;
    plugins) confirm_and_run "plugins" reset_plugins ;;
    env)     confirm_and_run "environment" reset_env ;;
    full)    confirm_and_run "FULL WIPE" full_wipe ;;
    stop)    stop_services ;;
    -h|--help) usage ;;
    "")      interactive_menu ;;
    *)       usage; exit 1 ;;
esac

echo ""
info "Done."
