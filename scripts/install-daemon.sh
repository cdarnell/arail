#!/usr/bin/env bash
# scripts/install-daemon.sh
#
# Install ARAIL's lab services as macOS launchd LaunchAgents so the lab is
# persistent: starts at login (RunAtLoad), respawns on crash (KeepAlive),
# survives closing the terminal. Modeled on qukaizen-nucleus's
# install-trainer-launchd.sh.
#
# Services: portal (always), memory/LanceDB (always), mlx OpenAI server
# (only when MODEL_BACKEND=mlx in .env). ttyd/jupyter/code-server stay in
# the dev/foreground start.sh deliberately — they hold no lab state and
# auto-respawning browser-reachable shells at login is attack surface with
# no persistence upside.
#
# Idempotent: re-running re-renders and reloads only when changed.
#
# Usage:
#     ./arailctl install-daemon      (or ./scripts/install-daemon.sh)
#     ./arailctl uninstall-daemon    (or ./scripts/install-daemon.sh --uninstall)
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TEMPLATE="$REPO_ROOT/scripts/launchd/io.arail.service.plist.template"
AGENTS_DIR="$HOME/Library/LaunchAgents"
LAUNCHCTL="${LAUNCHCTL:-launchctl}"
LOG_DIR="$REPO_ROOT/lab/logs"

die() { echo "✗ $*" >&2; exit 1; }

[[ "$(uname -s)" == "Darwin" ]] || die "launchd supervision is macOS-only (Gentoo boxes use scripts/gentoo-bootstrap.sh OpenRC)"

# Load lab config the same way start.sh does — ports come from .env/lab.conf.
cd "$REPO_ROOT"
# shellcheck disable=SC1091
[[ -f .env ]] && set -a && source .env && set +a
if [[ -f lab.conf ]]; then
    # shellcheck disable=SC1091
    source lab.conf
fi

BIND="${BIND_ADDR:-127.0.0.1}"

# service_name  app_module                    port
render_targets() {
    echo "portal arail.portal.app:app ${PORTAL_PORT:-8080}"
    echo "memory arail.memory_service:app ${LANCE_PORT:-7414}"
    if [[ "${MODEL_BACKEND:-auto}" == "mlx" ]]; then
        echo "mlx arail.mlx_openai_server:app ${MLX_OPENAI_PORT:-11435}"
    fi
}

all_labels() { echo "io.arail.portal io.arail.memory io.arail.mlx"; }

if [[ "${1:-}" == "--uninstall" ]]; then
    removed=0
    for label in $(all_labels); do
        plist="$AGENTS_DIR/$label.plist"
        if [[ -f "$plist" ]]; then
            "$LAUNCHCTL" unload "$plist" 2>/dev/null || true
            rm "$plist"
            echo "✓ Uninstalled $label"
            removed=1
        fi
    done
    [[ "$removed" == 1 ]] || echo "→ Already uninstalled (no io.arail.* agents)"
    exit 0
fi

[[ -f "$TEMPLATE" ]] || die "Template not found: $TEMPLATE"
[[ -x "$REPO_ROOT/.venv/bin/python" ]] || die "No .venv — run ./arailctl setup first"

# Refuse to install over a running foreground lab (double-start = port war).
if pgrep -f "uvicorn.*arail\.portal\.app" >/dev/null 2>&1 \
        && ! "$LAUNCHCTL" list io.arail.portal >/dev/null 2>&1; then
    die "A foreground lab is running (start.sh). Stop it first: ./arailctl stop"
fi

mkdir -p "$AGENTS_DIR" "$LOG_DIR"

rotate_log() {
    # launchd holds the fd while the agent runs, so (re)load time is the
    # honest rotation window (same story opencode tells).
    local f="$1"
    if [[ -f "$f" ]] && [[ "$(stat -f%z "$f" 2>/dev/null || echo 0)" -gt 10485760 ]]; then
        mv "$f" "$f.1"
    fi
}

render_targets | while read -r svc app port; do
    label="io.arail.$svc"
    installed="$AGENTS_DIR/$label.plist"
    rendered="$(mktemp)"
    sed -e "s|REPLACE_ME_LABEL|$label|g" \
        -e "s|REPLACE_ME_SERVICE|$svc|g" \
        -e "s|REPLACE_ME_REPO|$REPO_ROOT|g" \
        -e "s|REPLACE_ME_HOME|$HOME|g" \
        -e "s|REPLACE_ME_BIND|$BIND|g" \
        -e "s|REPLACE_ME_APP|$app|g" \
        -e "s|REPLACE_ME_PORT|$port|g" \
        "$TEMPLATE" > "$rendered"

    if [[ -f "$installed" ]] && cmp -s "$rendered" "$installed"; then
        echo "→ $label already up to date"
        rm -f "$rendered"
    else
        [[ -f "$installed" ]] && "$LAUNCHCTL" unload "$installed" 2>/dev/null || true
        rotate_log "$LOG_DIR/$svc.out.log"
        rotate_log "$LOG_DIR/$svc.err.log"
        mv "$rendered" "$installed"
        echo "✓ Wrote $installed"
    fi
    "$LAUNCHCTL" load "$installed" 2>/dev/null || true
done

# The mlx agent must not linger when the backend is no longer mlx.
if [[ "${MODEL_BACKEND:-auto}" != "mlx" ]] && [[ -f "$AGENTS_DIR/io.arail.mlx.plist" ]]; then
    "$LAUNCHCTL" unload "$AGENTS_DIR/io.arail.mlx.plist" 2>/dev/null || true
    rm "$AGENTS_DIR/io.arail.mlx.plist"
    echo "✓ Removed io.arail.mlx (MODEL_BACKEND is not mlx)"
fi

echo ""
echo "✓ Lab supervised by launchd — starts at login, respawns on crash."
echo "  Status:   ./arailctl status   (or: launchctl list | grep io.arail)"
echo "  Logs:     tail -F $LOG_DIR/portal.{out,err}.log"
echo "  Stop:     ./arailctl stop     (unloads agents; stays stopped)"
echo "  Remove:   ./arailctl uninstall-daemon"
echo "  Dev mode: ./arailctl uninstall-daemon && ./arailctl start"
