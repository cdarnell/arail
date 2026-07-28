#!/usr/bin/env bash
# Regression driver for scripts/start.sh's Concurrent-Worlds retrofit
# (sprints/2026-07-28-concurrent-worlds/ARCHITECTURE.md §3, §10 WP4).
#
# Drives the REAL scripts/start.sh (never a reimplementation) inside a
# throwaway fake repo: real scripts/, a symlinked .venv (so `arail.*` and
# `arail.world_mount` import for real), stub uvicorn/ollama/open/xdg-open
# binaries prepended to PATH so no real server, model backend, or browser
# is ever touched, and (where a scenario needs it) fixture World bundles
# built with tests/world_bundle_builder.py's make_bundle().
#
# Exits 0 and prints "OK: <n> scenario(s)" on success; non-zero with
# "FAIL: <reason>" otherwise (same contract as
# tests/shell_source_safety_driver.sh).
set -uo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
REAL_VENV="${ARAIL_TEST_VENV:-$REPO/.venv}"
if [[ ! -x "$REAL_VENV/bin/python" ]]; then
    # Fall back to the sibling checkout's venv (this worktree ships none —
    # see sprints/2026-07-28-concurrent-worlds/BUILD_LOG.md).
    REAL_VENV="$(cd "$REPO/.." 2>/dev/null && pwd)/.venv"
fi
if [[ ! -x "$REAL_VENV/bin/python" ]]; then
    echo "SKIP: no usable .venv found (tried \$ARAIL_TEST_VENV, $REPO/.venv, sibling checkout) — cannot import arail.*"
    exit 0
fi

fail() { echo "FAIL: $1" >&2; exit 1; }
pass_count=0
ok_scenario() { pass_count=$((pass_count + 1)); }

# macOS ships no `timeout(1)` (no coreutils by default). Portable wrapper
# via python3 (always present under REAL_VENV): kills the whole process
# group on timeout so a stray background child never survives the driver.
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

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# Isolated HOME: daemon_active() (scripts/lib/instances.sh) reads
# $HOME/Library/LaunchAgents/io.arail.portal.plist — on a developer machine
# that has ./arailctl install-daemon'd for real, the REAL HOME's plist would
# otherwise leak into every scenario here and wrongly trip the daemon guard.
FAKE_HOME="$WORK/home"
mkdir -p "$FAKE_HOME"

# ── Build one throwaway repo: real scripts/, symlinked .venv, empty lab/ ──
_make_fake_repo() {
    local name="$1"
    local fake="$WORK/$name"
    mkdir -p "$fake"
    cp -R "$REPO/scripts" "$fake/scripts"
    ln -s "$REAL_VENV" "$fake/.venv"
    mkdir -p "$fake/lab/worlds" "$fake/lab/models" "$fake/lab/data"
    printf 'LAB_NAME="Test Lab"\nLAB_SHORT_NAME=test-lab\n' > "$fake/.env"
    printf 'PORTAL_PORT=8080\n' > "$fake/lab.conf"
    printf '%s' "$fake"
}

# ── Stub bin dir: fake uvicorn (dies instantly — never binds), fake
# ollama/open/xdg-open (no-ops) prepended to PATH so no real service, model
# backend, or browser is ever touched. curl/python3/pgrep/ps/kill/launchctl
# stay real (needed for the actual bind-check / registry / daemon logic
# under test).
_make_stub_bin() {
    local bin="$WORK/stubbin"
    mkdir -p "$bin"
    cat > "$bin/uvicorn" <<'EOF'
#!/usr/bin/env bash
# Simulates an instant crash — never binds, never answers /api/instance.
# Stage [6/8]'s readiness poll must detect the dead PID and fail fast
# rather than waiting the full 60s cap.
exit 1
EOF
    cat > "$bin/ollama" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
    cat > "$bin/open" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
    cat > "$bin/xdg-open" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
    chmod +x "$bin"/*
    printf '%s' "$bin"
}

STUB_BIN="$(_make_stub_bin)"

_make_world() {
    local fake="$1" slug="$2" name="$3"
    PYTHONPATH="$REPO/tests" "$REAL_VENV/bin/python" -c "
from pathlib import Path
from world_bundle_builder import make_bundle
make_bundle(Path('$fake/lab/worlds'), slug='$slug', display_name='$name')
"
}

_run_start() {
    # _run_start <fake_repo> [args...] — always with a tight timeout since
    # every scenario here is expected to conclude (success, refusal, or a
    # fast-failing stub uvicorn) well under it.
    local fake="$1"; shift
    ( cd "$fake" && PATH="$STUB_BIN:$PATH" HOME="$FAKE_HOME" ARAIL_NO_BROWSER=1 _timeout 20 bash scripts/start.sh "$@" )
}

# ---------------------------------------------------------------------------
# 1) Unknown flag -> exit 2, usage printed. Silently discarding argv was
#    the bug this sprint retires (BRIEF: "start.sh discards all arguments").
# ---------------------------------------------------------------------------
fake1="$(_make_fake_repo repo1)"
out1="$(_run_start "$fake1" --bogus-flag 2>&1)"; rc1=$?
[[ "$rc1" == "2" ]] || fail "unknown flag: expected exit 2, got $rc1 — output:\n$out1"
echo "$out1" | grep -qi "unknown flag" || fail "unknown flag: no 'Unknown flag' message — output:\n$out1"
echo "$out1" | grep -qi "usage" || fail "unknown flag: no usage line — output:\n$out1"
ok_scenario

# ---------------------------------------------------------------------------
# 2) --world with a nonexistent slug -> exit 2 (F5), before any directory
#    is created under lab/instances/.
# ---------------------------------------------------------------------------
fake2="$(_make_fake_repo repo2)"
out2="$(_run_start "$fake2" --world nosuchworld --yes 2>&1)"; rc2=$?
[[ "$rc2" == "2" ]] || fail "unknown slug: expected exit 2, got $rc2 — output:\n$out2"
[[ ! -d "$fake2/lab/instances/nosuchworld" ]] || fail "unknown slug: a half-built instance root was created (F5 violation)"
ok_scenario

# ---------------------------------------------------------------------------
# 3) --world with a path-traversal slug -> rejected by the _SLUG_RE jail
#    before ever touching the filesystem (F5).
# ---------------------------------------------------------------------------
fake3="$(_make_fake_repo repo3)"
out3="$(_run_start "$fake3" --world '../../etc' --yes 2>&1)"; rc3=$?
[[ "$rc3" != "0" ]] || fail "path traversal slug: must not exit 0 — output:\n$out3"
ok_scenario

# ---------------------------------------------------------------------------
# 4) Claim race (F6): a pre-existing (fresh) claim file blocks a concurrent
#    start for the same slug — loser exits 1, names the holder.
# ---------------------------------------------------------------------------
fake4="$(_make_fake_repo repo4)"
_make_world "$fake4" finance "Finance World"
mkdir -p "$fake4/lab/instances/registry.d"
echo "999999" > "$fake4/lab/instances/registry.d/finance.claim"
out4="$(_run_start "$fake4" --world finance --yes 2>&1)"; rc4=$?
[[ "$rc4" == "1" ]] || fail "claim race: expected exit 1, got $rc4 — output:\n$out4"
echo "$out4" | grep -qi "in progress" || fail "claim race: no 'in progress' message — output:\n$out4"
ok_scenario

# ---------------------------------------------------------------------------
# 5) Ceiling (F10): 3 live-looking instance records at the default ceiling
#    -> a 4th refuses, names the roster and the stop command. No eviction.
#    `kill` is a bash BUILTIN — a same-named PATH stub is silently ignored
#    for a bare `kill -0`, so real background `sleep` processes stand in
#    for "alive" PIDs; only `ps` (not a builtin) needs a PATH stub, to
#    supply a cmdline that matches inst_alive's module+port check.
# ---------------------------------------------------------------------------
fake5="$(_make_fake_repo repo5)"
_make_world "$fake5" fourth "Fourth World"
mkdir -p "$fake5/lab/instances/registry.d"
ceiling_bin="$WORK/ceilingbin"
mkdir -p "$ceiling_bin"
cat > "$ceiling_bin/ps" <<'EOF'
#!/usr/bin/env bash
# All 3 fixture ports in one cmdline so inst_alive's substring "--port
# <expected>" check matches regardless of which record is being probed —
# this stub doesn't know (or need to know) which pid was asked about.
echo "python -m uvicorn arail.portal.app:app --port 8090 --port 8100 --port 8110"
EOF
chmod +x "$ceiling_bin"/*
_ceiling_sleep_pids=()
for i in 1 2 3; do
    port=$((8090 + (i - 1) * 10))
    sleep 30 &
    real_pid=$!
    _ceiling_sleep_pids+=("$real_pid")
    cat > "$fake5/lab/instances/registry.d/w${i}.json" <<EOF
{"schema":"arail.instance-registry/v1","slug":"w${i}","display_name":"W${i}",
 "checkout":"$fake5","instance_root":"$fake5/lab/instances/w${i}",
 "data_dir":"$fake5/lab/instances/w${i}/data","pkb_root":"$fake5/lab/instances/w${i}/pkb",
 "bind":"127.0.0.1","portal_port":${port},"lance_port":$((port + 4)),
 "launcher_pid":${real_pid},"portal_pid":${real_pid},"memory_pid":${real_pid},"token":"t","started_at":"2026-01-01T00:00:00Z",
 "arailctl_version":"test"}
EOF
done
out5="$( cd "$fake5" && PATH="$ceiling_bin:$STUB_BIN:$PATH" HOME="$FAKE_HOME" ARAIL_NO_BROWSER=1 _timeout 20 bash scripts/start.sh --world fourth --yes 2>&1 )"; rc5=$?
for pid in "${_ceiling_sleep_pids[@]}"; do kill "$pid" 2>/dev/null || true; wait "$pid" 2>/dev/null || true; done
[[ "$rc5" == "1" ]] || fail "ceiling: expected exit 1, got $rc5 — output:\n$out5"
echo "$out5" | grep -qi "ceiling" || fail "ceiling: no ceiling message — output:\n$out5"
echo "$out5" | grep -q "stop" || fail "ceiling: no stop-command hint — output:\n$out5"
ok_scenario

# ---------------------------------------------------------------------------
# 6) Bind conflict (F1/F17's testable half in this environment — the
#    scan-then-bind TOCTOU race itself needs real timing and is exercised
#    manually/by QA, not scripted here): a port already listening blocks
#    stage [5/8] before any uvicorn is spawned; a named lsof hint is given.
# ---------------------------------------------------------------------------
fake6="$(_make_fake_repo repo6)"
_make_world "$fake6" busyport "Busy Port World"
"$REAL_VENV/bin/python" - "$WORK/busy_port.pid" <<'PY' &
import socket, sys, time
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(("127.0.0.1", 8090))
s.listen(1)
open(sys.argv[1], "w").write("bound")
time.sleep(15)
PY
busy_pid=$!
for _ in 1 2 3 4 5 6 7 8 9 10; do
    [[ -f "$WORK/busy_port.pid" ]] && break
    sleep 0.3
done
out6="$(_run_start "$fake6" --world busyport --port 8090 --yes 2>&1)"; rc6=$?
kill "$busy_pid" 2>/dev/null || true
wait "$busy_pid" 2>/dev/null || true
[[ "$rc6" == "1" ]] || fail "bind conflict: expected exit 1, got $rc6 — output:\n$out6"
echo "$out6" | grep -qi "taken" || fail "bind conflict: no 'taken' message — output:\n$out6"
ok_scenario

# ---------------------------------------------------------------------------
# 7) --list is scriptable and side-effect free: zero Worlds -> a plain
#    "no Worlds" line; two Worlds -> both slugs listed, exit 0 either way.
# ---------------------------------------------------------------------------
fake7="$(_make_fake_repo repo7)"
out7a="$(_run_start "$fake7" --list 2>&1)"; rc7a=$?
[[ "$rc7a" == "0" ]] || fail "--list (0 worlds): expected exit 0, got $rc7a — output:\n$out7a"
echo "$out7a" | grep -qi "no worlds" || fail "--list (0 worlds): expected a 'no Worlds' line — output:\n$out7a"
[[ ! -d "$fake7/lab/instances" ]] || fail "--list: must be side-effect free (no lab/instances/ created)"

_make_world "$fake7" ai "AI World"
_make_world "$fake7" finance "Finance World"
out7b="$(_run_start "$fake7" --list 2>&1)"; rc7b=$?
[[ "$rc7b" == "0" ]] || fail "--list (2 worlds): expected exit 0, got $rc7b — output:\n$out7b"
echo "$out7b" | grep -q "^ai " || fail "--list (2 worlds): 'ai' missing — output:\n$out7b"
echo "$out7b" | grep -q "^finance " || fail "--list (2 worlds): 'finance' missing — output:\n$out7b"
ok_scenario

# ---------------------------------------------------------------------------
# 8) |W| >= 2, no TTY, no --yes -> exit 2, roster + exact --world command
#    printed (VISION §3: "never guess").
# ---------------------------------------------------------------------------
fake8="$(_make_fake_repo repo8)"
_make_world "$fake8" ai "AI World"
_make_world "$fake8" finance "Finance World"
out8="$(_run_start "$fake8" < /dev/null 2>&1)"; rc8=$?
[[ "$rc8" == "2" ]] || fail "no-tty multi-world: expected exit 2, got $rc8 — output:\n$out8"
echo "$out8" | grep -q -- "--world ai" || fail "no-tty multi-world: no --world ai hint — output:\n$out8"
echo "$out8" | grep -q -- "--world finance" || fail "no-tty multi-world: no --world finance hint — output:\n$out8"
ok_scenario

# ---------------------------------------------------------------------------
# 9) |W| == 1 auto-selects the instance path — no picker, no --world
#    needed. (Stub uvicorn dies instantly, so this exercises stage [6/8]'s
#    fast-fail path, not a full successful boot — see BUILD_LOG "WP4"
#    section for why a real end-to-end boot needs WP6's /api/instance.)
# ---------------------------------------------------------------------------
fake9="$(_make_fake_repo repo9)"
_make_world "$fake9" onlyworld "Only World"
out9="$(_run_start "$fake9" --yes 2>&1)"; rc9=$?
echo "$out9" | grep -q "\[1/8\]" || fail "single-world auto-select: instance staged output missing (picker fired instead?) — output:\n$out9"
echo "$out9" | grep -qi "starting lab services" && fail "single-world auto-select: fell through to the root-lab path — output:\n$out9"
[[ "$rc9" != "0" ]] || fail "single-world auto-select: expected a non-zero exit (stub uvicorn cannot bind) — output:\n$out9"
ok_scenario

# ---------------------------------------------------------------------------
# 10) |W| == 0 -> the root-lab path, unmodified, is reached (byte-identical
#     banner text). Real service startup (uvicorn/ollama/ttyd/etc.) is out
#     of scope here — stub uvicorn dies instantly so this run concludes
#     fast; asserts on the STRUCTURE of stdout only.
# ---------------------------------------------------------------------------
fake10="$(_make_fake_repo repo10)"
out10="$( cd "$fake10" && PATH="$STUB_BIN:$PATH" HOME="$FAKE_HOME" ARAIL_NO_BROWSER=1 _timeout 10 bash scripts/start.sh 2>&1; true )"
echo "$out10" | grep -qi "starting lab services" || fail "zero worlds: root-lab banner missing — output:\n$out10"
echo "$out10" | grep -q "\[1/8\]" && fail "zero worlds: instance staged output leaked into the root-lab path — output:\n$out10"
ok_scenario

echo "OK: ${pass_count} scenario(s) passed — scripts/start.sh Concurrent-Worlds retrofit"
