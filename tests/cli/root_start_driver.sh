#!/usr/bin/env bash
# tests/cli/root_start_driver.sh — regression driver for the root-lab
# readiness gate (sprints/2026-07-29-elite-cli/ARCHITECTURE.md §8, WP2).
# Gates: T13-T17, F1, F29, F30, F31, T35 (§16.2 happy path).
#
# Drives the REAL scripts/start.sh (and, for T17, the REAL arailctl daemon
# branch) against a throwaway fake repo with a REAL-BINDING stub uvicorn
# (tests/cli/stub_uvicorn_serving.py via tests/cli/lib.sh) — never a
# reimplementation of the readiness logic under test.
#
# F26/F27: every port here is randomized >= 18000 and never 8080/8090.
set -uo pipefail

DRIVER_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "$DRIVER_DIR/lib.sh"

if [[ -z "$REAL_VENV" ]]; then
    echo "SKIP: no usable .venv found (tried \$ARAIL_TEST_VENV, $CLI_TEST_REPO/.venv, sibling checkout) — cannot import arail.*"
    exit 0
fi

fail() { echo "FAIL: $1" >&2; exit 1; }
pass_count=0
ok_scenario() { pass_count=$((pass_count + 1)); }

# A minimal, sanitized base PATH (no /opt/homebrew, no developer tool
# dirs) — the developer's REAL ollama/ttyd/jupyter/code-server must never
# be reachable from a scenario that didn't deliberately stub them in.
SAFE_PATH="/usr/bin:/bin:/usr/sbin:/sbin"

# pwd -P (physical): macOS's mktemp -d returns a path under /var/folders,
# itself a symlink to /private/var/folders. scripts/start.sh resolves its
# own REPO_ROOT via `pwd -P` (REVIEW.md m5) — an unresolved $WORK here
# would make every identity-match fixture below compare against the WRONG
# (symlinked) checkout string and fail every "should succeed" scenario.
WORK="$(cd "$(mktemp -d)" && pwd -P)"
trap 'rm -rf "$WORK"' EXIT
FAKE_HOME="$WORK/home"
mkdir -p "$FAKE_HOME"

# ── Scenario setup helper ───────────────────────────────────────────────
# _new_scenario <name> -> sets globals FAKE and
# PORTAL/LANCE/TERMINAL/NOTEBOOK/IDE to fresh, distinct, F26/F27-safe
# ports and writes lab.conf with them. NOT called inside $( ) — a command
# substitution runs in a subshell, which would make every one of those
# global assignments invisible to the caller.
_new_scenario() {
    local name="$1"
    FAKE="$WORK/$name"
    make_fake_repo "$FAKE" >/dev/null
    make_fake_venv "$FAKE"
    write_stub_uvicorn_serving "$FAKE"
    PORTAL="$(cli_test_random_port)"
    LANCE="$(( PORTAL + 1 ))"
    TERMINAL="$(( PORTAL + 2 ))"
    NOTEBOOK="$(( PORTAL + 3 ))"
    IDE="$(( PORTAL + 4 ))"
    cli_test_assert_port_safe "$PORTAL"
    write_lab_conf "$FAKE" "$PORTAL" "$LANCE" "$TERMINAL" "$NOTEBOOK" "$IDE"
}

_fixture() {
    # _fixture <fake-repo> -> path to a JSON file with the correct
    # identity body (slug=root, checkout=<fake-repo>) for svc_identity_root
    # to match against.
    local fake="$1" f="$WORK/fixture-$$-$RANDOM.json"
    printf '{"slug":"root","checkout":"%s"}' "$fake" > "$f"
    printf '%s' "$f"
}

# ---------------------------------------------------------------------------
# T13 / F29: fully-serving stubs (portal, memory, terminal, notebook, ide
# all bind) -> every service prints ✓, banner says "All services running",
# and the process is still alive (blocked in `wait`) when the timeout
# fires -- i.e. the readiness gate did not exit early.
# ---------------------------------------------------------------------------
_new_scenario repo13; fake13="$FAKE"
write_stub_listen_only "$fake13" ttyd "$TERMINAL" 0
write_stub_listen_only "$fake13" jupyter "$NOTEBOOK" 0
write_stub_listen_only "$fake13" code-server "$IDE" 0
fixture13="$(_fixture "$fake13")"
out13="$( cd "$fake13" && HOME="$FAKE_HOME" PATH="$SAFE_PATH" ARAIL_NO_BROWSER=1 \
    STUB_FIXTURE="$fixture13" STUB_STATUS=200 \
    _timeout 8 bash scripts/start.sh 2>&1 )"
rc13=$?
[[ "$rc13" == "124" ]] || fail "T13: expected the lab to still be running at the timeout (rc 124), got $rc13 — output:\n$out13"
echo "$out13" | grep -q "✓ Portal" || fail "T13: no ✓ Portal line — output:\n$out13"
echo "$out13" | grep -q "✓ Memory" || fail "T13: no ✓ Memory line — output:\n$out13"
echo "$out13" | grep -q "✓ Terminal" || fail "T13: no ✓ Terminal line — output:\n$out13"
echo "$out13" | grep -q "✓ Notebook" || fail "T13: no ✓ Notebook line — output:\n$out13"
echo "$out13" | grep -q "✓ IDE" || fail "T13: no ✓ IDE line — output:\n$out13"
echo "$out13" | grep -q "All services running" || fail "T13: banner did not say 'All services running' — output:\n$out13"
ok_scenario

# ---------------------------------------------------------------------------
# T14 / F1 / F31: portal answers once with HTTP 401, then crashes ->
# ✗ Portal with the last-HTTP-status diagnostic (401), NO "All services
# running", exit 1, and no process is left listening on any of THIS fake
# repo's randomized ports afterward (nothing orphaned — F1's kill list is
# ${PIDS[@]} only, but that must actually reach every already-spawned
# child, including terminal/notebook/ide).
# ---------------------------------------------------------------------------
_new_scenario repo14; fake14="$FAKE"
write_stub_listen_only "$fake14" ttyd "$TERMINAL" 0
write_stub_listen_only "$fake14" jupyter "$NOTEBOOK" 0
write_stub_listen_only "$fake14" code-server "$IDE" 0
fixture14="$(_fixture "$fake14")"
out14="$( cd "$fake14" && HOME="$FAKE_HOME" PATH="$SAFE_PATH" ARAIL_NO_BROWSER=1 \
    STUB_FIXTURE="$fixture14" STUB_STATUS=401 STUB_CRASH_AFTER=1 \
    _timeout 15 bash scripts/start.sh 2>&1 )"
rc14=$?
[[ "$rc14" == "1" ]] || fail "T14: expected exit 1, got $rc14 — output:\n$out14"
echo "$out14" | grep -q "✗ Portal" || fail "T14: no ✗ Portal line — output:\n$out14"
echo "$out14" | grep -qi "401" || fail "T14: no HTTP 401 diagnostic — output:\n$out14"
echo "$out14" | grep -qi "All services running" && fail "T14: must NOT print 'All services running' — output:\n$out14"
sleep 0.5
for p in "$PORTAL" "$LANCE" "$TERMINAL" "$NOTEBOOK" "$IDE"; do
    if lsof -iTCP:"$p" -sTCP:LISTEN -P -n >/dev/null 2>&1; then
        fail "T14: port $p is still listening after start.sh exited — a child was orphaned (F1 violation)"
    fi
done
ok_scenario

# ---------------------------------------------------------------------------
# T15: portal + memory answer normally; notebook (jupyter present, but
# never binds) times out -> ⚠, banner says "degraded: notebook", the
# Notebook URL is absent from the URL block, and the process is still
# running (degrade, never abort).
# ---------------------------------------------------------------------------
_new_scenario repo15; fake15="$FAKE"
write_stub_listen_only "$fake15" jupyter "$NOTEBOOK" 1  # never_bind=1
fixture15="$(_fixture "$fake15")"
# NOTE: svc_wait_listening's per-tick lsof invocation costs more real time
# than its 0.1s sleep alone (~130-150ms/tick observed), so a 100-tick
# (nominal 10s) cap can run ~13-15s in practice — the same class of
# looseness the instance path's own curl-based polls already have, just
# more pronounced here since lsof spawns cost more than curl's. The
# timeout below is sized generously for that, not for a functional wait.
out15="$( cd "$fake15" && HOME="$FAKE_HOME" PATH="$SAFE_PATH" ARAIL_NO_BROWSER=1 \
    STUB_FIXTURE="$fixture15" STUB_STATUS=200 \
    _timeout 20 bash scripts/start.sh 2>&1 )"
rc15=$?
[[ "$rc15" == "124" ]] || fail "T15: expected the lab to still be running at the timeout (rc 124), got $rc15 — output:\n$out15"
echo "$out15" | grep -q "✓ Portal" || fail "T15: no ✓ Portal line — output:\n$out15"
echo "$out15" | grep -q "⚠.*[Nn]otebook" || fail "T15: no notebook degrade warning — output:\n$out15"
echo "$out15" | grep -qi "degraded: notebook" || fail "T15: banner did not name notebook as degraded — output:\n$out15"
echo "$out15" | grep -q "Notebook:" && fail "T15: the Notebook URL line must be ABSENT from a degraded service — output:\n$out15"
ok_scenario

# ---------------------------------------------------------------------------
# T16 / F31: a real process already listening on PORTAL_PORT -> start.sh
# refuses BEFORE spawning anything, names ./arailctl status, and the
# foreign listener survives untouched (F1: never signal a pid we didn't
# spawn).
# ---------------------------------------------------------------------------
_new_scenario repo16; fake16="$FAKE"
"$REAL_VENV/bin/python" - "$WORK/busy16.pid" "$PORTAL" <<'PY' &
import socket, sys, time
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(("127.0.0.1", int(sys.argv[2])))
s.listen(1)
open(sys.argv[1], "w").write("bound")
time.sleep(20)
PY
busy16_pid=$!
for _ in 1 2 3 4 5 6 7 8 9 10; do
    [[ -f "$WORK/busy16.pid" ]] && break
    sleep 0.3
done
fixture16="$(_fixture "$fake16")"
out16="$( cd "$fake16" && HOME="$FAKE_HOME" PATH="$SAFE_PATH" ARAIL_NO_BROWSER=1 \
    STUB_FIXTURE="$fixture16" \
    _timeout 8 bash scripts/start.sh 2>&1 )"
rc16=$?
still_listening=1
lsof -iTCP:"$PORTAL" -sTCP:LISTEN -P -n >/dev/null 2>&1 || still_listening=0
kill "$busy16_pid" 2>/dev/null || true
wait "$busy16_pid" 2>/dev/null || true
[[ "$rc16" == "1" ]] || fail "T16: expected exit 1, got $rc16 — output:\n$out16"
echo "$out16" | grep -qi "already running" || fail "T16: no 'already running' refusal message — output:\n$out16"
echo "$out16" | grep -qi "status" || fail "T16: refusal did not mention ./arailctl status — output:\n$out16"
[[ "$still_listening" == "1" ]] || fail "T16: the foreign listener on the portal port did not survive (F1 violation)"
ok_scenario

# ---------------------------------------------------------------------------
# T17: daemon-mode readiness (arailctl, not scripts/start.sh) — a stub
# launchctl fakes daemon_active()==true and, on `kickstart`, spawns the
# real-binding serving stub in the portal's place (simulating "launchd
# already had the job loaded"). Case (a): it answers -> ✓ + URL, exit 0.
# Case (b): kickstart spawns nothing -> ✗ + the log hint, exit 1 (this
# leg has no pid to early-out on in daemon mode, same as the real
# arailctl code — it genuinely waits the cap, hence the longer timeout).
# ---------------------------------------------------------------------------
_write_stub_launchctl() {
    # _write_stub_launchctl <fake> <spawn:0|1> <portal-port> <fixture>
    local fake="$1" spawn="$2" port="$3" fixture="$4"
    mkdir -p "$fake/stubbin"
    if [[ "$spawn" == "1" ]]; then
        cat > "$fake/stubbin/launchctl" <<EOF
#!/usr/bin/env bash
case "\$1 \$2" in
    "list io.arail.portal") echo '        "PID" = 4242;'; exit 0 ;;
esac
case "\$1" in
    load) exit 0 ;;
    kickstart)
        STUB_FIXTURE="$fixture" STUB_STATUS=200 \\
            "$fake/.venv/bin/uvicorn" "arail.portal.app:app" --host 127.0.0.1 --port "$port" \\
            > "$fake/lab/logs/portal.out.log" 2>&1 &
        disown
        exit 0
        ;;
    *) exit 0 ;;
esac
EOF
    else
        cat > "$fake/stubbin/launchctl" <<'EOF'
#!/usr/bin/env bash
case "$1 $2" in
    "list io.arail.portal") echo '        "PID" = 4242;'; exit 0 ;;
esac
exit 0
EOF
    fi
    chmod +x "$fake/stubbin/launchctl"
}

# (a) ready
_new_scenario repo17a; fake17a="$FAKE"
mkdir -p "$FAKE_HOME/Library/LaunchAgents"
: > "$FAKE_HOME/Library/LaunchAgents/io.arail.portal.plist"
fixture17a="$(_fixture "$fake17a")"
_write_stub_launchctl "$fake17a" 1 "$PORTAL" "$fixture17a"
out17a="$( cd "$fake17a" && HOME="$FAKE_HOME" PATH="$fake17a/stubbin:$SAFE_PATH" ARAIL_NO_BROWSER=1 \
    _timeout 10 bash arailctl start 2>&1 )"
rc17a=$?
# The stub launchctl's `kickstart` backgrounds a REAL process to simulate
# "launchd already had the job loaded" — nothing in this harness's own
# process tree owns it (that's the point: launchd would, for real), so it
# must be reaped explicitly rather than relying on _timeout's
# process-group kill (which only fires on an actual timeout, and this
# scenario is expected to finish well under its cap).
cli_test_kill_port_listener "$PORTAL"
[[ "$rc17a" == "0" ]] || fail "T17a: expected exit 0, got $rc17a — output:\n$out17a"
echo "$out17a" | grep -qi "http://127.0.0.1:${PORTAL}" || fail "T17a: no portal URL printed — output:\n$out17a"
ok_scenario

# (b) not ready (kickstart spawns nothing) — genuinely waits the 30s cap;
# this is the one intentionally slow leg of this driver.
_new_scenario repo17b; fake17b="$FAKE"
_write_stub_launchctl "$fake17b" 0 "$PORTAL" "$(_fixture "$fake17b")"
out17b="$( cd "$fake17b" && HOME="$FAKE_HOME" PATH="$fake17b/stubbin:$SAFE_PATH" ARAIL_NO_BROWSER=1 \
    _timeout 40 bash arailctl start 2>&1 )"
rc17b=$?
[[ "$rc17b" == "1" ]] || fail "T17b: expected exit 1, got $rc17b — output:\n$out17b"
echo "$out17b" | grep -qi "portal.err.log" || fail "T17b: no log-tail hint — output:\n$out17b"
ok_scenario

# ---------------------------------------------------------------------------
# T35 (§16.2 happy path, REVIEW.md m10): golden path on a clean fake repo —
# start --root --no-browser -> status (0) -> restart --root -> status (0)
# -> stop --root -> status (4). Every step non-tty, every exit code
# asserted. This is also the only end-to-end coverage `restart --root`'s
# FOREGROUND path has at all (root_start_driver.sh's T13-T17 only ever
# drive `start`; restart_driver.sh's --root scenarios stop short of a
# real re-start), and — since it drives a REAL `stop --root` against a
# REAL running root lab spawned by a REAL `start --root` — it is the one
# scenario that would have caught B2 in its original, unscoped-fallback
# shape even without a fabricated sibling instance.
#
# `start --root` and `restart --root` both block in a foreground `wait`
# once up (same shape as T13/T18a), so each is backgrounded via a tiny
# exec-wrapper script — `exec`, not `cmd &` inside `( )`, so the
# backgrounded pid IS start.sh's own pid (no subshell indirection): a
# SIGTERM sent to that pid reaches start.sh's own `trap cleanup INT TERM`
# directly, exactly like a real terminal Ctrl-C would.
# ---------------------------------------------------------------------------
_new_scenario repo35; fake35="$FAKE"
fixture35="$(_fixture "$fake35")"

cat > "$WORK/t35_run_start.sh" <<EOF
#!/usr/bin/env bash
cd "$fake35"
export HOME="$FAKE_HOME" PATH="$SAFE_PATH" ARAIL_NO_BROWSER=1
export STUB_FIXTURE="$fixture35" STUB_STATUS=200
exec bash scripts/start.sh --root --no-browser
EOF
chmod +x "$WORK/t35_run_start.sh"
cat > "$WORK/t35_run_restart.sh" <<EOF
#!/usr/bin/env bash
cd "$fake35"
export HOME="$FAKE_HOME" PATH="$SAFE_PATH" ARAIL_NO_BROWSER=1
export STUB_FIXTURE="$fixture35" STUB_STATUS=200
exec bash arailctl restart --root
EOF
chmod +x "$WORK/t35_run_restart.sh"

# _t35_wait_for_marker <logfile> <ERE> — NOT a curl/port poll. `restart
# --root`'s stop phase (a REAL stop_services() call) can take up to ~2s to
# confirm the OLD portal is dead before the start phase even begins
# re-spawning a NEW one; polling the port alone cannot tell "the OLD
# server is still up because the restart hasn't gotten to the stop yet"
# apart from "the NEW server came up for real" — the first check can
# succeed instantly against the STILL-LIVE old process, sending this
# scenario on to its next step (a second `stop --root`) while restart's
# own stop-then-start is still in flight underneath it (found by running
# this scenario back-to-back after T13-T17: flaked once in ~8 runs with a
# genuinely torn state — Portal up, Memory down — exactly what that race
# produces). Waiting for start.sh's own "✓ Portal" readiness line in the
# invocation's OWN log is unambiguous: it only ever prints once, after
# THIS invocation's identity-gated readiness probe (§8.2) itself passed.
_t35_wait_for_marker() {
    local log="$1" marker="$2" i
    for i in $(seq 1 100); do
        grep -qE "$marker" "$log" 2>/dev/null && return 0
        sleep 0.1
    done
    return 1
}
_t35_run_status() {
    ( cd "$fake35" && HOME="$FAKE_HOME" PATH="$SAFE_PATH" _timeout 10 bash arailctl status </dev/null 2>&1 )
}

"$WORK/t35_run_start.sh" > "$WORK/t35_start.log" 2>&1 &
t35_start_pid=$!
_t35_wait_for_marker "$WORK/t35_start.log" '✓ Portal' || fail "T35: start --root never became ready — log:\n$(cat "$WORK/t35_start.log")"

t35_out_status1="$(_t35_run_status)"; t35_rc_status1=$?
[[ "$t35_rc_status1" == "0" ]] || fail "T35: status after start --root expected exit 0, got $t35_rc_status1 — output:\n$t35_out_status1"

"$WORK/t35_run_restart.sh" > "$WORK/t35_restart.log" 2>&1 &
t35_restart_pid=$!
_t35_wait_for_marker "$WORK/t35_restart.log" '✓ Portal' || fail "T35: restart --root never became ready — log:\n$(cat "$WORK/t35_restart.log")"
echo "$(cat "$WORK/t35_restart.log")" | grep -qi "the lab is now DOWN" && fail "T35: restart --root reported the lab as DOWN — log:\n$(cat "$WORK/t35_restart.log")"

t35_out_status2="$(_t35_run_status)"; t35_rc_status2=$?
[[ "$t35_rc_status2" == "0" ]] || fail "T35: status after restart --root expected exit 0, got $t35_rc_status2 — output:\n$t35_out_status2"

t35_out_stop="$( cd "$fake35" && HOME="$FAKE_HOME" PATH="$SAFE_PATH" _timeout 10 bash arailctl stop --root </dev/null 2>&1 )"
t35_rc_stop=$?
[[ "$t35_rc_stop" == "0" ]] || fail "T35: stop --root expected exit 0, got $t35_rc_stop — output:\n$t35_out_stop"

sleep 0.3
t35_out_status3="$(_t35_run_status)"; t35_rc_status3=$?
[[ "$t35_rc_status3" == "4" ]] || fail "T35: status after stop --root expected exit 4 (nothing running), got $t35_rc_status3 — output:\n$t35_out_status3"
ok_scenario

cli_test_kill_port_listener "$PORTAL"
kill "$t35_start_pid" "$t35_restart_pid" 2>/dev/null || true
wait "$t35_start_pid" "$t35_restart_pid" 2>/dev/null || true

echo "OK: ${pass_count} scenario(s) passed — root-lab readiness gate (T13-T17, T35)"
