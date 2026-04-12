#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

GREEN="\033[0;32m"; CYAN="\033[0;36m"; BOLD="\033[1m"; RESET="\033[0m"
info() { echo -e "${GREEN}[oglab]${RESET} $*"; }

# shellcheck disable=SC1091
source lab.conf 2>/dev/null || true
export PATH="$HOME/.local/bin:$PATH"
BIND="${BIND_ADDR:-127.0.0.1}"

[[ -f .venv/bin/activate ]] || { echo "no .venv — run ./oglab setup"; exit 1; }
# shellcheck disable=SC1091
source .venv/bin/activate

PIDS=()

echo ""
echo -e "${CYAN}${BOLD}⟨OGLab⟩ Starting lab services…${RESET}"
echo ""

info "Portal     → http://${BIND}:${PORTAL_PORT:-8080}"
uvicorn oglab.portal.app:app \
    --host "$BIND" --port "${PORTAL_PORT:-8080}" \
    --log-level warning &
PIDS+=($!)

if command -v ttyd &>/dev/null; then
    info "Terminal   → http://${BIND}:${TERMINAL_PORT:-7681}"
    ttyd -W -p "${TERMINAL_PORT:-7681}" -i "$BIND" "${SHELL:-bash}" &
    PIDS+=($!)
else
    info "Terminal   → (ttyd not installed — skipping)"
fi

if command -v jupyter &>/dev/null; then
    info "Notebook   → http://${BIND}:${NOTEBOOK_PORT:-8888}"
    jupyter lab \
        --no-browser \
        --ip="$BIND" \
        --port="${NOTEBOOK_PORT:-8888}" \
        --NotebookApp.token="" \
        --NotebookApp.password="" &
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
echo -e "  Terminal:   ${BOLD}http://${BIND}:${TERMINAL_PORT:-7681}${RESET}"
echo -e "  Notebook:   ${BOLD}http://${BIND}:${NOTEBOOK_PORT:-8888}${RESET}"
echo -e "  IDE:        ${BOLD}http://${BIND}:${IDE_PORT:-8443}${RESET}  (password: ${IDE_PASSWORD:-oglab})"
echo ""
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"

cleanup() {
    echo ""
    info "Shutting down…"
    for pid in "${PIDS[@]}"; do kill "$pid" 2>/dev/null || true; done
    wait 2>/dev/null || true
    info "All services stopped."
}
trap cleanup INT TERM

wait
