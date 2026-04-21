#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

GREEN="\033[0;32m"; CYAN="\033[0;36m"; BOLD="\033[1m"; RESET="\033[0m"

# Load .env first (for LAB_NAME and friends) before anything else.
# shellcheck disable=SC1091
[[ -f .env ]] && set -a && source .env && set +a
# shellcheck disable=SC1091
source lab.conf 2>/dev/null || true

LAB_NAME="${LAB_NAME:-OGLab}"
LAB_SHORT_NAME="${LAB_SHORT_NAME:-oglab}"
LAB_LOGO="${LAB_LOGO:-⟨${LAB_NAME}⟩}"

info() { echo -e "${GREEN}[${LAB_SHORT_NAME}]${RESET} $*"; }

export PATH="$HOME/.local/bin:$PATH"
BIND="${BIND_ADDR:-127.0.0.1}"

[[ -f .venv/bin/activate ]] || { echo "no .venv — run ./oglab setup"; exit 1; }
# shellcheck disable=SC1091
source .venv/bin/activate

PIDS=()

echo ""
echo -e "${CYAN}${BOLD}${LAB_LOGO} Starting lab services…${RESET}"
echo ""

info "Portal     → http://${BIND}:${PORTAL_PORT:-8080}"
uvicorn oglab.portal.app:app \
    --host "$BIND" --port "${PORTAL_PORT:-8080}" \
    --log-level warning &
PIDS+=($!)

if [[ "${MODEL_BACKEND:-auto}" == "mlx" ]]; then
    info "MLX API    → http://${BIND}:${MLX_OPENAI_PORT:-11435}/v1"
    uvicorn oglab.mlx_openai_server:app \
        --host "$BIND" --port "${MLX_OPENAI_PORT:-11435}" \
        --log-level warning &
    PIDS+=($!)
fi

if command -v ttyd &>/dev/null; then
    info "Terminal   → http://${BIND}:${TERMINAL_PORT:-7681}"
    # Terminal persistence: when tmux is available we attach every ttyd
    # connection to a named session ("oglab") so closing the browser
    # tab, navigating away, or reloading the iframe doesn't nuke the
    # user's scrollback, pwd, running jobs, or env. New connections
    # reattach to the same session (`-A` = attach or create).
    # -t disableLeaveAlert=true suppresses ttyd's built-in
    # "Are you sure you want to leave?" prompt that used to fire on
    # every nav click. tmux already keeps the session alive, so the
    # warning is noise — not protection — inside the portal.
    TTYD_OPTS=(-W -p "${TERMINAL_PORT:-7681}" -i "$BIND"
               -t disableLeaveAlert=true
               -t scrollBar=true)
    if command -v tmux &>/dev/null; then
        TMUX_SHELL="${SHELL:-/bin/bash}"
        ttyd "${TTYD_OPTS[@]}" \
            tmux new-session -A -s "${LAB_SHORT_NAME:-oglab}" \
                "$TMUX_SHELL" &
    else
        warn "tmux not installed — terminal scrollback won't survive iframe reloads"
        warn "install: brew install tmux (mac) · sudo apt install tmux (linux)"
        ttyd "${TTYD_OPTS[@]}" "${SHELL:-bash}" &
    fi
    PIDS+=($!)
else
    platform_hint=""
    if [[ "$(uname -s)" == "Darwin" ]]; then
        platform_hint="  brew install ttyd"
    elif command -v apt >/dev/null 2>&1; then
        platform_hint="  sudo apt install ttyd"
    elif command -v dnf >/dev/null 2>&1; then
        platform_hint="  sudo dnf install ttyd"
    elif command -v pacman >/dev/null 2>&1; then
        platform_hint="  sudo pacman -S ttyd"
    elif command -v emerge >/dev/null 2>&1; then
        platform_hint="  sudo emerge -av www-apps/ttyd"
    fi
    info "Terminal   → (ttyd not installed — /terminal shows install help)"
    [[ -n "$platform_hint" ]] && info "             install: ${platform_hint}"
fi

if command -v jupyter &>/dev/null; then
    info "Notebook   → http://${BIND}:${NOTEBOOK_PORT:-8888}"
    # Ensure Dark High Contrast theme is the default
    _jl_settings="$(python3 -c 'import jupyterlab,os;print(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(jupyterlab.__file__)))),"share","jupyter","lab","settings"))' 2>/dev/null || echo "")"
    if [[ -n "$_jl_settings" ]]; then
        mkdir -p "$_jl_settings"
        cat > "$_jl_settings/overrides.json" <<'JLTHEME'
{
  "@jupyterlab/apputils-extension:themes": {
    "theme": "JupyterLab Dark High Contrast"
  }
}
JLTHEME
    fi
    jupyter lab \
        --no-browser \
        --ip="$BIND" \
        --port="${NOTEBOOK_PORT:-8888}" \
        --NotebookApp.token="" \
        --NotebookApp.password="" \
        --ServerApp.tornado_settings='{"headers":{"Content-Security-Policy":"frame-ancestors '\''self'\'' http://127.0.0.1:* http://localhost:*"}}' &
    PIDS+=($!)
else
    info "Notebook   → (jupyter not installed — skipping)"
fi

if command -v code-server &>/dev/null; then
    info "IDE        → http://${BIND}:${IDE_PORT:-8443}"
    code-server \
        --bind-addr "${BIND}:${IDE_PORT:-8443}" \
        --auth password \
        --disable-telemetry \
        . &
    PIDS+=($!)
else
    info "IDE        → (code-server not installed — skipping)"
fi

echo ""
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo -e "  ${BOLD}All services running.${RESET}  Press Ctrl+C to stop."
echo ""
echo -e "  Dashboard:  ${BOLD}http://${BIND}:${PORTAL_PORT:-8080}${RESET}"
echo -e "  MLX API:    ${BOLD}http://${BIND}:${MLX_OPENAI_PORT:-11435}/v1${RESET}"
echo -e "  Terminal:   ${BOLD}http://${BIND}:${TERMINAL_PORT:-7681}${RESET}"
echo -e "  Notebook:   ${BOLD}http://${BIND}:${NOTEBOOK_PORT:-8888}${RESET}"
echo -e "  IDE:        ${BOLD}http://${BIND}:${IDE_PORT:-8443}${RESET}  (password in ${BOLD}lab.conf${RESET})"
echo ""
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"

# Auto-open the dashboard unless suppressed or headless.
if [[ "${OGLAB_NO_BROWSER:-0}" != "1" ]] && [[ -t 1 ]]; then
    dashboard_url="http://${BIND}:${PORTAL_PORT:-8080}"
    (
        # Give uvicorn a moment to bind the port before opening the browser.
        for _ in 1 2 3 4 5 6 7 8 9 10; do
            if curl -sf -o /dev/null "$dashboard_url" 2>/dev/null; then break; fi
            sleep 0.5
        done
        if command -v open >/dev/null; then open "$dashboard_url"
        elif command -v xdg-open >/dev/null; then xdg-open "$dashboard_url" >/dev/null 2>&1
        fi
    ) &
fi

cleanup() {
    echo ""
    info "Shutting down…"
    for pid in "${PIDS[@]}"; do kill "$pid" 2>/dev/null || true; done
    wait 2>/dev/null || true
    info "All services stopped."
}
trap cleanup INT TERM

wait
