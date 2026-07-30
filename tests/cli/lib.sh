#!/usr/bin/env bash
# tests/cli/lib.sh — shared harness for the tests/cli/*_driver.sh scripts
# (sprints/2026-07-29-elite-cli/ARCHITECTURE.md §16.1).
#
# Modeled directly on tests/instance_start_driver.sh: real scripts/ copied
# into a throwaway repo, a controllable venv, stub PATH, isolated HOME (so
# a developer's real launchd plist/lab can never leak in), and a portable
# `_timeout` (macOS ships none).
#
# F26/F27 (load-bearing, not just isolation): every port this harness uses
# is randomized >= 18000 and is NEVER 8080/8090. reset.sh's pre-upgrade
# fallback stop pattern matches on argv WITHOUT --app-dir; on the wrong
# port it could reach a developer's real running lab. Every driver that
# sources this file MUST call `cli_test_assert_port_safe` on any port it
# is about to use before touching it.
set -uo pipefail

CLI_TEST_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLI_TEST_REPO="$(cd "$CLI_TEST_DIR/../.." && pwd)"

_cli_test_find_venv() {
    local c
    for c in "${ARAIL_TEST_VENV:-}" "$CLI_TEST_REPO/.venv" "$CLI_TEST_REPO/../.venv"; do
        [[ -n "$c" && -x "$c/bin/python" ]] && { printf '%s' "$c"; return 0; }
    done
    return 1
}

REAL_VENV="$(_cli_test_find_venv)" || REAL_VENV=""

# Portable timeout wrapper (macOS ships no timeout(1)) — kills the WHOLE
# process group on expiry so no stub server/uvicorn ever survives a driver
# run. Requires REAL_VENV (python3).
_timeout() {
    local secs="$1"; shift
    "$REAL_VENV/bin/python" -c '
import os, signal, subprocess, sys
secs = float(sys.argv[1])
cmd = sys.argv[2:]
p = subprocess.Popen(cmd, start_new_session=True)
try:
    sys.exit(p.wait(timeout=secs))
except subprocess.TimeoutExpired:
    try:
        os.killpg(os.getpgid(p.pid), signal.SIGKILL)
    except Exception:
        pass
    sys.exit(124)
' "$secs" "$@"
}

# F26: a random high port, never the two real lab ports.
cli_test_random_port() {
    local p=$(( 18000 + RANDOM % 20000 ))
    while [[ "$p" == "8080" || "$p" == "8090" ]]; do
        p=$(( p + 1 ))
    done
    printf '%s' "$p"
}

# F27: hard refusal if a driver ever computes 8080/8090 as a working port —
# stated in this file's own header as a load-bearing safety property, not
# just isolation, per ARCHITECTURE.md F27.
cli_test_assert_port_safe() {
    local p="$1"
    case "$p" in
        8080|8090)
            echo "REFUSING to run: port $p is a real ARAIL lab port (F27) — a bug in this harness would risk killing a developer's real running lab" >&2
            exit 1
            ;;
    esac
}

# ── Fake repo: real scripts/ + arailctl, throwaway lab/, isolated env ───
# make_fake_repo <dest-dir>
make_fake_repo() {
    local fake="$1"
    mkdir -p "$fake"
    cp -R "$CLI_TEST_REPO/scripts" "$fake/scripts"
    cp "$CLI_TEST_REPO/arailctl" "$fake/arailctl"
    mkdir -p "$fake/lab/worlds" "$fake/lab/models" "$fake/lab/data" "$fake/lab/logs"
    printf 'LAB_NAME="Test Lab"\nLAB_SHORT_NAME=test-lab\n' > "$fake/.env"
    printf '%s' "$fake"
}

# ── Fake venv: a REAL, working python (site-packages symlinked from the
# real venv, so `import arail` works) but a `uvicorn` this harness fully
# controls. Needed because `source .venv/bin/activate` (start.sh, and
# arailctl's `doctor`/`wiki`/etc. cases) always PREPENDS $VIRTUAL_ENV/bin
# ahead of anything already on PATH — a stub `uvicorn` prepended onto PATH
# before invoking start.sh would otherwise be shadowed by the real venv's
# own (fully working) uvicorn the moment activate runs. Symlinking
# individual files (not the whole venv dir, unlike
# tests/instance_start_driver.sh's simpler needs) is what makes overriding
# just uvicorn possible while everything else keeps working.
#
# ALSO note: a real venv's `bin/activate` bakes an ABSOLUTE VIRTUAL_ENV
# path in at creation time (this repo's own is a hardcoded path) — reusing
# it verbatim would point PATH back at the REAL venv/bin, defeating this
# function's whole purpose. A minimal from-scratch activate script is
# written instead.
make_fake_venv() {
    local fake="$1"
    [[ -n "$REAL_VENV" ]] || return 1
    mkdir -p "$fake/.venv/bin"
    ln -s "$REAL_VENV/lib" "$fake/.venv/lib" 2>/dev/null || true
    [[ -f "$REAL_VENV/pyvenv.cfg" ]] && ln -s "$REAL_VENV/pyvenv.cfg" "$fake/.venv/pyvenv.cfg"
    local f base
    for f in "$REAL_VENV"/bin/*; do
        base="$(basename "$f")"
        case "$base" in
            uvicorn|uvicorn3) continue ;;  # this harness supplies its own
            # CRITICAL: never symlink any activate* variant here — the
            # `cat >` below would then follow the symlink and OVERWRITE
            # THE REAL VENV'S OWN activate script in place (this is not
            # hypothetical: it happened once while writing this file and
            # corrupted the real .venv/bin/activate; regenerated via
            # `python3.11 -m venv .venv`, no --clear, which rewrites only
            # the activation scripts and leaves site-packages untouched).
            activate|activate.*|Activate.*) continue ;;
        esac
        ln -s "$f" "$fake/.venv/bin/$base"
    done
    # A real, non-symlinked file — safe to `cat >` (see the CRITICAL note
    # in the loop above for why this must never be a pre-existing symlink).
    cat > "$fake/.venv/bin/activate" <<ACTIVATE
#!/usr/bin/env bash
# Minimal test-stub activate (tests/cli/lib.sh:make_fake_venv) — see that
# function's header for why the real venv's own activate can't be reused.
export VIRTUAL_ENV="${fake}/.venv"
export PATH="\${VIRTUAL_ENV}/bin:\$PATH"
ACTIVATE
    chmod +x "$fake/.venv/bin/activate"
}

fake_venv_python() {
    printf '%s/.venv/bin/python3' "$1"
}

# link_real_uvicorn <fake> — symlink the REAL, working uvicorn into a fake
# venv built by make_fake_venv (which otherwise never puts one there).
# For drivers that only need `command -v uvicorn` to succeed (e.g.
# `doctor`'s preflight) and never actually invoke it.
link_real_uvicorn() {
    local fake="$1"
    [[ -n "$REAL_VENV" && -e "$REAL_VENV/bin/uvicorn" ]] || return 1
    ln -sf "$REAL_VENV/bin/uvicorn" "$fake/.venv/bin/uvicorn"
}

# ── The "serving" stub uvicorn (§16.1's enabling capability): actually
# BINDS <host>:<port> and answers /api/instance and /health for real,
# dialed per-scenario via env vars (see tests/cli/stub_uvicorn_serving.py's
# own header for the exact controls: STUB_STATUS, STUB_FIXTURE,
# STUB_CRASH_AFTER, STUB_NEVER_BIND).
write_stub_uvicorn_serving() {
    local fake="$1"
    cp "$CLI_TEST_DIR/stub_uvicorn_serving.py" "$fake/.venv/stub_uvicorn_serving.py"
    cat > "$fake/.venv/bin/uvicorn" <<EOF
#!/usr/bin/env bash
# A REAL-BINDING stub uvicorn (ARCHITECTURE.md §16.1) — parses just enough
# argv (module target + --host/--port) to hand off to the python stub
# server; every behavior knob is an env var the driver sets before it
# invokes start.sh/arailctl (see stub_uvicorn_serving.py).
module=""; host="127.0.0.1"; port="8080"
while [[ \$# -gt 0 ]]; do
    case "\$1" in
        --host) host="\$2"; shift 2 ;;
        --port) port="\$2"; shift 2 ;;
        --app-dir) shift 2 ;;
        --log-level) shift 2 ;;
        *) [[ -z "\$module" ]] && module="\$1"; shift ;;
    esac
done
exec "$fake/.venv/bin/python3" "$fake/.venv/stub_uvicorn_serving.py" "\$module" "\$host" "\$port"
EOF
    chmod +x "$fake/.venv/bin/uvicorn"
}

# ── Listen-only stubs (ttyd / jupyter / code-server): either bind <port>
# and hold it open, or (never_bind=1) start but never bind at all —
# simulating "installed, but the tab never comes up" (T15).
write_stub_listen_only() {
    local fake="$1" name="$2" port="$3" never_bind="${4:-0}"
    if [[ "$never_bind" == "1" ]]; then
        cat > "$fake/.venv/bin/$name" <<'EOF'
#!/usr/bin/env bash
trap 'exit 0' TERM INT
sleep 300 &
wait
EOF
    else
        cat > "$fake/.venv/bin/$name" <<EOF
#!/usr/bin/env bash
exec "$fake/.venv/bin/python3" -c "
import socket, signal, sys
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(('127.0.0.1', $port))
s.listen(5)
signal.signal(signal.SIGTERM, lambda *a: sys.exit(0))
signal.signal(signal.SIGINT, lambda *a: sys.exit(0))
signal.pause()
"
EOF
    fi
    chmod +x "$fake/.venv/bin/$name"
}

# cli_test_kill_port_listener <port> — best-effort cleanup for a scenario
# that simulates launchd/a supervisor spawning a REAL process this harness
# does not otherwise track in a PIDS array (e.g. a stub `launchctl
# kickstart` backgrounding a serving stub — nothing in that path is a
# child this driver's own `_timeout` process-group kill would reach, since
# the real production equivalent is "launchd owns it", which this harness
# only simulates). Never fails a driver on its own.
cli_test_kill_port_listener() {
    local port="$1" pid
    pid="$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null | head -n1)"
    [[ -n "$pid" ]] && kill "$pid" 2>/dev/null
    return 0
}

# ── lab.conf writer: F26/F27-safe random ports, all distinct.
write_lab_conf() {
    local fake="$1" portal="$2" lance="$3" terminal="$4" notebook="$5" ide="$6"
    cat > "$fake/lab.conf" <<EOF
PORTAL_PORT=${portal}
LANCE_PORT=${lance}
TERMINAL_PORT=${terminal}
NOTEBOOK_PORT=${notebook}
IDE_PORT=${ide}
BIND_ADDR=127.0.0.1
EOF
}
