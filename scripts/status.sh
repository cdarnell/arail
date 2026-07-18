#!/usr/bin/env bash
# ./arailctl status — show what's running and where.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

BOLD="\033[1m"; GREEN="\033[0;32m"; YELLOW="\033[0;33m"; DIM="\033[2m"; RESET="\033[0m"
ok()   { echo -e "  ${GREEN}✓${RESET} $*"; }
warn() { echo -e "  ${YELLOW}⚠${RESET} $*"; }
dim()  { echo -e "  ${DIM}$*${RESET}"; }

# shellcheck disable=SC1091
[[ -f .env ]] && set -a && source .env && set +a
# shellcheck disable=SC1091
source lab.conf 2>/dev/null || true
BIND="${BIND_ADDR:-127.0.0.1}"
LAB_NAME="${LAB_NAME:-Arail}"

echo ""
echo -e "${BOLD}${LAB_NAME} — Status${RESET}"
echo ""

# ── venv + install ────────────────────────────────────────────────
if [[ -d .venv ]]; then
    ok ".venv present"
else
    warn ".venv missing — run ./arailctl setup"
fi

# ── services ──────────────────────────────────────────────────────
check() {
    local name="$1" port="$2" pattern="$3"
    if pgrep -f "$pattern" >/dev/null 2>&1; then
        ok "${name} running on http://${BIND}:${port}"
    else
        dim "${name} not running"
    fi
}

# ── supervision ───────────────────────────────────────────────────
if [[ "$(uname -s)" == "Darwin" ]] && [[ -f "$HOME/Library/LaunchAgents/io.arail.portal.plist" ]]; then
    echo -e "  ${BOLD}Supervision${RESET}: daemon (launchd)"
    for label in io.arail.portal io.arail.memory io.arail.mlx; do
        [[ -f "$HOME/Library/LaunchAgents/$label.plist" ]] || continue
        line="$(launchctl list "$label" 2>/dev/null | tr -d '\t{};"' | grep -E 'PID|LastExitStatus' | tr '\n' ' ' || true)"
        if [[ -n "$line" ]]; then
            ok "${label}: ${line}"
        else
            dim "${label}: installed, not loaded"
        fi
    done
    echo ""
else
    echo -e "  ${BOLD}Supervision${RESET}: foreground (start.sh) — see ./arailctl install-daemon"
    echo ""
fi

check "Portal   " "${PORTAL_PORT:-8080}"   "uvicorn.*arail\.portal\.app"
check "MLX API  " "${MLX_OPENAI_PORT:-11435}" "uvicorn.*arail\.mlx_openai_server"
check "Notebook " "${NOTEBOOK_PORT:-8888}" "jupyter-lab"
check "Terminal " "${TERMINAL_PORT:-7681}" "ttyd"
check "IDE      " "${IDE_PORT:-8443}"      "code-server"

# ── scheduler ─────────────────────────────────────────────────────
if command -v curl >/dev/null && curl -sf "http://${BIND}:${PORTAL_PORT:-8080}/api/jobs/state" >/dev/null 2>&1; then
    echo ""
    state_json="$(curl -sf "http://${BIND}:${PORTAL_PORT:-8080}/api/jobs/state")"
    window=$(echo "$state_json"  | python3 -c "import sys,json;print(json.load(sys.stdin).get('label','?'))" 2>/dev/null || echo "?")
    halted=$(echo "$state_json"  | python3 -c "import sys,json;print(json.load(sys.stdin).get('halted','?'))" 2>/dev/null || echo "?")
    echo -e "  ${BOLD}Scheduler${RESET}"
    dim "window: ${window}"
    dim "halted: ${halted}"
fi

# ── lab/ state ────────────────────────────────────────────────────
echo ""
echo -e "  ${BOLD}Runtime state${RESET}"
for d in lab/data lab/models lab/pkb; do
    if [[ -d "$d" ]]; then
        sz=$(du -sh "$d" 2>/dev/null | awk '{print $1}')
        dim "${d}  ${sz}"
    fi
done

echo ""
