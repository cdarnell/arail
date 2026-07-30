#!/usr/bin/env bash
# ./arailctl status — show what's running and where.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# shellcheck disable=SC1091
source "$REPO_ROOT/scripts/lib/instances.sh"

BOLD="\033[1m"; GREEN="\033[0;32m"; YELLOW="\033[0;33m"; DIM="\033[2m"; RESET="\033[0m"
ok()   { echo -e "  ${GREEN}✓${RESET} $*"; }
warn() { echo -e "  ${YELLOW}⚠${RESET} $*"; }
dim()  { echo -e "  ${DIM}$*${RESET}"; }

# shellcheck disable=SC1091
[[ -f .env ]] && set -a && source .env && set +a
# Latent set -e landmine found while restructuring this file for WP5: under
# bash 3.2 (macOS's shipped /bin/bash), `source <missing-file> || true`
# does NOT reach the `|| true` — a "file not found" source error aborts a
# non-interactive shell outright even under a trailing `||`. On a fresh
# checkout before ./arailctl setup has ever run (no lab.conf yet), a bare
# `./arailctl status` would crash with no message. Same class of fix as
# ARCHITECTURE.md §10's "Ruling on the two latent fixes" for start.sh —
# guard with an existence check instead, matching the .env line above it.
# shellcheck disable=SC1091
[[ -f lab.conf ]] && source lab.conf
BIND="${BIND_ADDR:-127.0.0.1}"
LAB_NAME="${LAB_NAME:-Arail}"

# ── Instances (ARCHITECTURE.md §4.1) ────────────────────────────────
# Registry-driven table, no-network by default (predicate steps 1-3 only —
# the <2s win condition for 3 instances). --probe adds step 4 (the
# /api/instance token+checkout check) and a mismatch column. --json is
# scripting output — it prints ONLY the row array (no header, no other
# sections) and exits, so a caller can pipe it straight into a JSON parser.
STATUS_JSON=0
STATUS_PROBE=0
for _status_arg in "$@"; do
    case "$_status_arg" in
        --json)  STATUS_JSON=1 ;;
        --probe) STATUS_PROBE=1 ;;
    esac
done

if [[ "$STATUS_JSON" != "1" ]]; then
    echo ""
    echo -e "${BOLD}${LAB_NAME} — Status${RESET}"
    echo ""
fi

_status_build_rows() {
    local slug rec rc probe_field data_dir_field
    while IFS= read -r slug; do
        [[ -n "$slug" ]] || continue
        if rec="$(inst_read_record "$slug" 2>/dev/null)"; then
            rc=0
        else
            rc=$?
        fi
        if (( rc == 2 )); then
            printf '{"slug":%s,"state":"unreadable"}\n' "$(python3 -c 'import json,sys;print(json.dumps(sys.argv[1]))' "$slug")"
            continue
        fi
        (( rc == 0 )) || continue

        data_dir_field="$(inst_record_field "$rec" data_dir)"
        local data_missing="false"
        [[ -n "$data_dir_field" && -d "$data_dir_field" ]] || data_missing="true"

        if inst_alive "$slug"; then
            probe_field="null"
            if [[ "$STATUS_PROBE" == "1" ]]; then
                if inst_probe_matches "$slug" "$rec"; then
                    probe_field="null"
                else
                    local bind port raw
                    bind="$(inst_record_field "$rec" bind)"
                    port="$(inst_record_field "$rec" portal_port)"
                    raw="$(curl -sf -m 0.7 "http://${bind}:${port}/api/instance" 2>/dev/null || true)"
                    probe_field="$(python3 -c '
import json, sys
raw = sys.argv[1]
try:
    d = json.loads(raw)
    print(json.dumps(d.get("checkout", "")))
except Exception:
    print("null")
' "$raw")"
                fi
            fi
            python3 -c '
import json, sys
rec = json.loads(sys.argv[1])
rec["state"] = "live"
rec["data_root_missing"] = (sys.argv[2] == "true")
probe = sys.argv[3]
rec["probe_mismatch_checkout"] = json.loads(probe) if probe != "null" else None
print(json.dumps(rec))
' "$rec" "$data_missing" "$probe_field"
        else
            python3 -c '
import json, sys
rec = json.loads(sys.argv[1])
rec["state"] = "stale"
print(json.dumps(rec))
' "$rec"
        fi
    done < <(inst_list_slugs)
    # A `while read` loop's own exit status is that of its final `read`
    # (nonzero at EOF) when the body ran zero or more times — under
    # `set -eo pipefail`, letting that propagate would abort the caller's
    # `_status_rows_json="$(_status_build_rows | python3 ...)"` assignment
    # (a plain assignment is NOT exempt from errexit) the moment a repo has
    # zero registered instances. This function must always return 0.
    return 0
}

_status_rows_json="$(_status_build_rows | python3 -c '
import json, sys
rows = []
for line in sys.stdin:
    line = line.strip()
    if line:
        rows.append(json.loads(line))
print(json.dumps(rows))
')"

if [[ "$STATUS_JSON" == "1" ]]; then
    printf '%s\n' "$_status_rows_json"
    # Prune stale records even in --json mode (§2.5 side effect) before
    # exiting — --json is a complete, self-contained invocation, not a
    # prefix of the human-readable run below.
    inst_prune_all
    exit 0
else
    echo -e "  ${BOLD}Instances${RESET}  (checkout: ${REPO_ROOT})"
    echo ""
    python3 -c '
import json, sys
rows = json.loads(sys.argv[1])
if not rows:
    print("  (no World instances — see ./arailctl start --world <slug>)")
for r in rows:
    slug = r.get("slug", "?")
    state = r.get("state", "?")
    if state == "unreadable":
        print(f"  ✗ {slug:<10} unreadable (corrupt registry record — quarantined)")
        continue
    name = r.get("display_name") or slug
    port = r.get("portal_port", "?")
    pid = r.get("portal_pid", "?")
    if state == "stale":
        print(f"  ✗ {slug:<10} {name:<18} stale (pid {pid} gone)")
        continue
    mismatch = r.get("probe_mismatch_checkout")
    if mismatch:
        print(f"  ⚠ {slug:<10} {name:<18} :{port}  pid {pid}  serving from a DIFFERENT checkout: {mismatch}")
    else:
        print(f"  ● {slug:<10} {name:<18} :{port}  pid {pid}")
    if r.get("data_root_missing"):
        print("                 ⚠ data root missing")
    data_dir = r.get("data_dir", "")
    if data_dir:
        print(f"                 data  {data_dir}")
' "$_status_rows_json"
    echo ""
fi

# Prune stale records now that the table above has rendered them once
# (ARCHITECTURE.md §2.5 — a status command that silently deletes what it
# just reported would be surprising).
inst_prune_all

# ── venv + install ────────────────────────────────────────────────
if [[ -d .venv ]]; then
    ok ".venv present"
else
    warn ".venv missing — run ./arailctl setup"
fi

# ── services ──────────────────────────────────────────────────────
# check() used to take $port but only PRINT it — the match was
# `pgrep -f <pattern>`, port-agnostic, so with N instances it could report
# "Portal running on :8080" while looking at an unrelated :8090 process
# (ARCHITECTURE.md §2.6 status.sh row). Fixed for the two uvicorn checks
# (Portal, MLX API) below by folding the port into the caller's pattern
# argument. ttyd/jupyter/code-server are left as module-name matches: they
# are root-lab-exclusive singletons a World instance never starts (§3.6),
# so there is no second process to disambiguate from, and their actual
# command lines don't use a "--port <n>" flag (ttyd: -p, jupyter: --port=,
# code-server: --bind-addr) — a blind ".*--port" suffix would break them.
check() {
    local name="$1" port="$2" pattern="$3"
    if pgrep -f "$pattern" >/dev/null 2>&1; then
        ok "${name} running on http://${BIND}:${port}"
    else
        dim "${name} not running"
    fi
}

# ── supervision ───────────────────────────────────────────────────
# daemon_active() is the verdict (plist exists AND launchctl reports a live
# PID); plist-exists-alone only earns an "installed, inactive" footnote —
# see ARCHITECTURE.md §2.6 (status.sh:42 row) and the plist-trap fix (F9).
if daemon_active; then
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
elif daemon_plist_installed; then
    echo -e "  ${BOLD}Supervision${RESET}: foreground (start.sh) — launchd plists installed but inactive"
    echo ""
else
    echo -e "  ${BOLD}Supervision${RESET}: foreground (start.sh) — see ./arailctl install-daemon"
    echo ""
fi

check "Portal   " "${PORTAL_PORT:-8080}"   "uvicorn.*arail\.portal\.app.*--port ${PORTAL_PORT:-8080}"
check "MLX API  " "${MLX_OPENAI_PORT:-11435}" "uvicorn.*arail\.mlx_openai_server.*--port ${MLX_OPENAI_PORT:-11435}"
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
