#!/usr/bin/env bash
# tests/cli/restart_driver.sh — `--root` flag + `restart` redesign
# regression driver (sprints/2026-07-29-elite-cli/ARCHITECTURE.md §9, §10).
#
# WP3 ("--root for start/stop"): T18, F11.
# WP4 ("restart redesign", grown into this same file — both are grouped
# under the architecture's single "--root / restart:" test heading):
# T19-T21, F9, F12, F13.
# REVIEW.md B2: stop --root / restart --root sibling-World-survival.
#
# Drives the REAL scripts/start.sh, scripts/reset.sh, and arailctl (never a
# reimplementation). F26/F27: every port here is randomized >= 18000 and
# never 8080/8090.
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

SAFE_PATH="/usr/bin:/bin:/usr/sbin:/sbin"

# pwd -P: see root_start_driver.sh's identical header note — macOS's
# mktemp -d returns a symlinked path, and start.sh resolves REPO_ROOT via
# `pwd -P` (REVIEW.md m5), so an unresolved $WORK breaks every identity
# fixture comparison below.
WORK="$(cd "$(mktemp -d)" && pwd -P)"
trap 'rm -rf "$WORK"' EXIT
FAKE_HOME="$WORK/home"
mkdir -p "$FAKE_HOME"

_fixture() {
    local fake="$1" f="$WORK/fixture-$$-$RANDOM.json"
    printf '{"slug":"root","checkout":"%s"}' "$fake" > "$f"
    printf '%s' "$f"
}

# ---------------------------------------------------------------------------
# T18 / F11 setup: one fake repo, three World bundles ("ai", "finance", and
# — deliberately — one literally named "root", for F11) plus a fully-
# serving stub so `--root` can actually reach "wait" (T18a).
# ---------------------------------------------------------------------------
FAKE18="$WORK/repo18"
make_fake_repo "$FAKE18" >/dev/null
make_fake_venv "$FAKE18"
write_stub_uvicorn_serving "$FAKE18"
cli_test_make_world "$FAKE18" ai "AI World"
cli_test_make_world "$FAKE18" finance "Finance World"
cli_test_make_world "$FAKE18" root "A World Literally Named Root"
PORTAL18="$(cli_test_random_port)"
cli_test_assert_port_safe "$PORTAL18"
write_lab_conf "$FAKE18" "$PORTAL18" "$((PORTAL18 + 1))" "$((PORTAL18 + 2))" "$((PORTAL18 + 3))" "$((PORTAL18 + 4))"
FIXTURE18="$(_fixture "$FAKE18")"

# (a) start --root, >=2 Worlds configured, no tty -> starts the root lab
# (previously impossible: bare `start` would have hit the picker/refusal).
out18a="$( cd "$FAKE18" && HOME="$FAKE_HOME" PATH="$SAFE_PATH" ARAIL_NO_BROWSER=1 \
    STUB_FIXTURE="$FIXTURE18" STUB_STATUS=200 \
    _timeout 8 bash arailctl start --root </dev/null 2>&1 )"
rc18a=$?
[[ "$rc18a" == "124" ]] || fail "T18a: expected the root lab to still be running at the timeout (rc 124), got $rc18a — output:\n$out18a"
echo "$out18a" | grep -q "✓ Portal" || fail "T18a: no ✓ Portal line — output:\n$out18a"
ok_scenario

# (b) bare `start`, >=2 Worlds, no tty -> still exits 2, and the refusal now
# lists --root alongside the per-World lines (gap 2's actual fix).
out18b="$( cd "$FAKE18" && HOME="$FAKE_HOME" PATH="$SAFE_PATH" ARAIL_NO_BROWSER=1 \
    _timeout 8 bash arailctl start </dev/null 2>&1 )"
rc18b=$?
[[ "$rc18b" == "2" ]] || fail "T18b: expected exit 2, got $rc18b — output:\n$out18b"
echo "$out18b" | grep -q -- "--world ai" || fail "T18b: no --world ai hint — output:\n$out18b"
echo "$out18b" | grep -q -- "--world finance" || fail "T18b: no --world finance hint — output:\n$out18b"
echo "$out18b" | grep -q -- "start --root" || fail "T18b: refusal does not list --root — output:\n$out18b"
ok_scenario

# F11: a World is also named "root" — the refusal must disambiguate rather
# than let the two silently look alike.
echo "$out18b" | grep -qi "also named 'root'" || fail "F11: no disambiguation note for the World literally named 'root' — output:\n$out18b"
ok_scenario

# (c) --root --world x together -> exit 2 (mutually exclusive), before any
# daemon/picker logic even runs.
out18c="$( cd "$FAKE18" && HOME="$FAKE_HOME" PATH="$SAFE_PATH" ARAIL_NO_BROWSER=1 \
    _timeout 8 bash arailctl start --root --world ai </dev/null 2>&1 )"
rc18c=$?
[[ "$rc18c" == "2" ]] || fail "T18c: expected exit 2, got $rc18c — output:\n$out18c"
echo "$out18c" | grep -qi "mutually exclusive" || fail "T18c: no mutual-exclusion message — output:\n$out18c"
ok_scenario

# ---------------------------------------------------------------------------
# REVIEW.md B2 (stop --root): a World instance whose portal happens to
# share the ROOT lab's own configured PORTAL_PORT — the exact shape of
# `./arailctl start --world ai --port 8080`, which
# .github/workflows/blueprint-smoke.yml:220 uses against the real default
# port — must survive `stop --root`. World-instance portals are spawned by
# start.sh's instance path WITHOUT --app-dir (deliberately), so
# stop_services()'s pre-QA-11 port-only fallback used to match and kill
# them; docs/cli.md:205 promises "never touches a live World instance,
# even while one is running" and this is the scenario that promise must
# hold under. cli_test_fabricate_live_instance_portal_like is required
# here (not the plain cli_test_fabricate_live_instance) because
# stop_services() finds its fallback candidates via a REAL `pgrep -f`,
# which no stubbed `ps` on PATH can influence.
# ---------------------------------------------------------------------------
FAKEB2S="$WORK/repob2stop"
make_fake_repo "$FAKEB2S" >/dev/null
PORTALB2S="$(cli_test_random_port)"; cli_test_assert_port_safe "$PORTALB2S"
write_lab_conf "$FAKEB2S" "$PORTALB2S" "$((PORTALB2S + 1))" "$((PORTALB2S + 2))" "$((PORTALB2S + 3))" "$((PORTALB2S + 4))"
cli_test_fabricate_live_instance_portal_like "$FAKEB2S" ai "$PORTALB2S"
pid_b2s="$CLI_TEST_LAST_FABRICATED_PID"
sleep 0.3

out_b2s="$( cd "$FAKEB2S" && HOME="$FAKE_HOME" PATH="$SAFE_PATH" \
    _timeout 15 bash arailctl stop --root </dev/null 2>&1 )"
rc_b2s=$?
[[ "$rc_b2s" == "0" ]] || fail "B2(stop --root): expected exit 0, got $rc_b2s — output:\n$out_b2s"
kill -0 "$pid_b2s" 2>/dev/null || fail "B2(stop --root): the sibling World instance was KILLED by 'stop --root' — output:\n$out_b2s"
[[ -f "$FAKEB2S/lab/instances/registry.d/ai.json" ]] || fail "B2(stop --root): the sibling's registry record was removed by 'stop --root'"
ok_scenario
kill "$pid_b2s" 2>/dev/null || true; wait "$pid_b2s" 2>/dev/null || true

# ---------------------------------------------------------------------------
# REVIEW.md B2 (restart --root): same collision, via restart --root's own
# stop phase (`reset.sh stop --root`, the identical stop_services() call).
# The fixture has no .venv/lab.conf-backed root lab of its own, so the
# subsequent START phase fails fast (F13's DOWN notice) — irrelevant to
# what this scenario asserts: the STOP phase must never touch the sibling.
# ---------------------------------------------------------------------------
FAKEB2R="$WORK/repob2restart"
make_fake_repo "$FAKEB2R" >/dev/null
PORTALB2R="$(cli_test_random_port)"; cli_test_assert_port_safe "$PORTALB2R"
write_lab_conf "$FAKEB2R" "$PORTALB2R" "$((PORTALB2R + 1))" "$((PORTALB2R + 2))" "$((PORTALB2R + 3))" "$((PORTALB2R + 4))"
cli_test_fabricate_live_instance_portal_like "$FAKEB2R" ai "$PORTALB2R"
pid_b2r="$CLI_TEST_LAST_FABRICATED_PID"
sleep 0.3

out_b2r="$( cd "$FAKEB2R" && HOME="$FAKE_HOME" PATH="$SAFE_PATH" \
    _timeout 15 bash arailctl restart --root </dev/null 2>&1 )"
rc_b2r=$?
kill -0 "$pid_b2r" 2>/dev/null || fail "B2(restart --root): the sibling World instance was KILLED by 'restart --root' — output:\n$out_b2r"
[[ -f "$FAKEB2R/lab/instances/registry.d/ai.json" ]] || fail "B2(restart --root): the sibling's registry record was removed by 'restart --root'"
ok_scenario
kill "$pid_b2r" 2>/dev/null || true; wait "$pid_b2r" 2>/dev/null || true

# ---------------------------------------------------------------------------
# T19 / T21b / F13: two fabricated LIVE World instances ("a", "b" — real
# `sleep` processes standing in for portal/memory/launcher pid alike, via
# cli_test_fabricate_live_instance, so this exercises the registry/kill
# logic WITHOUT a full 8-stage boot). Neither has a real World bundle, so
# the start phase fails fast and deterministically at stage [2/8] ("no
# such World") — which is exactly what lets this scenario assert BOTH
# gates at once: `restart --world a` must stop EXACTLY "a" (T19 — "b"
# survives, the gap-3 regression net) and, since the subsequent start
# fails, must print the loud DOWN notice (T21b/F13).
# ---------------------------------------------------------------------------
FAKE19="$WORK/repo19"
make_fake_repo "$FAKE19" >/dev/null
make_fake_venv "$FAKE19"
PORT_A19="$(cli_test_random_port)"; cli_test_assert_port_safe "$PORT_A19"
PORT_B19=$((PORT_A19 + 1))
cli_test_write_stub_ps_for_slugs "$FAKE19/stubbin" "a:${PORT_A19}" "b:${PORT_B19}"
cli_test_fabricate_live_instance "$FAKE19" a "$PORT_A19"; pid_a19="$CLI_TEST_LAST_FABRICATED_PID"
cli_test_fabricate_live_instance "$FAKE19" b "$PORT_B19"; pid_b19="$CLI_TEST_LAST_FABRICATED_PID"

out19="$( cd "$FAKE19" && HOME="$FAKE_HOME" PATH="$FAKE19/stubbin:$SAFE_PATH" ARAIL_NO_BROWSER=1 \
    _timeout 20 bash arailctl restart --world a </dev/null 2>&1 )"
rc19=$?

# Assertions FIRST, cleanup kills LAST — b must still be alive when we
# check it; killing it ourselves before the check would make the
# assertion meaningless.
[[ "$rc19" == "2" ]] || fail "T19/T21b: expected exit 2 (start fails: no bundle for 'a'), got $rc19 — output:\n$out19"
[[ ! -f "$FAKE19/lab/instances/registry.d/a.json" ]] || fail "T19: a's registry record should have been removed by the scoped stop — output:\n$out19"
[[ -f "$FAKE19/lab/instances/registry.d/b.json" ]] || fail "T19: b's registry record was REMOVED — restart --world a must never touch a sibling (gap-3 regression) — output:\n$out19"
kill -0 "$pid_b19" 2>/dev/null || fail "T19: b's process was killed — restart --world a must never touch a sibling (gap-3 regression) — output:\n$out19"
echo "$out19" | grep -qi "the lab is now DOWN" || fail "T21b/F13: no 'the lab is now DOWN' notice after a successful stop + failed start — output:\n$out19"
ok_scenario

kill "$pid_a19" 2>/dev/null || true; wait "$pid_a19" 2>/dev/null || true
kill "$pid_b19" 2>/dev/null || true; wait "$pid_b19" 2>/dev/null || true

# ---------------------------------------------------------------------------
# T20(a): bare `restart`, exactly 1 live instance -> that instance's stop is
# scoped, and its slug is INJECTED into the start phase (never re-parsed —
# the "no such World: solo" fast-fail is itself the proof the injected
# --world reached start.sh).
# ---------------------------------------------------------------------------
FAKE20A="$WORK/repo20a"
make_fake_repo "$FAKE20A" >/dev/null
make_fake_venv "$FAKE20A"
PORT_SOLO="$(cli_test_random_port)"; cli_test_assert_port_safe "$PORT_SOLO"
cli_test_write_stub_ps_for_slugs "$FAKE20A/stubbin" "solo:${PORT_SOLO}"
cli_test_fabricate_live_instance "$FAKE20A" solo "$PORT_SOLO"; pid_solo="$CLI_TEST_LAST_FABRICATED_PID"

out20a="$( cd "$FAKE20A" && HOME="$FAKE_HOME" PATH="$FAKE20A/stubbin:$SAFE_PATH" ARAIL_NO_BROWSER=1 \
    _timeout 20 bash arailctl restart </dev/null 2>&1 )"
rc20a=$?
kill "$pid_solo" 2>/dev/null || true; wait "$pid_solo" 2>/dev/null || true

[[ "$rc20a" == "2" ]] || fail "T20a: expected exit 2 (injected --world solo fails fast: no bundle), got $rc20a — output:\n$out20a"
[[ ! -f "$FAKE20A/lab/instances/registry.d/solo.json" ]] || fail "T20a: solo's registry record should have been removed — output:\n$out20a"
echo "$out20a" | grep -qi "no such World: solo" || fail "T20a: bare restart did not inject --world solo into the start phase — output:\n$out20a"
ok_scenario

# ---------------------------------------------------------------------------
# T20(b): bare `restart`, 0 live instances -> behaves like `start` (stop
# --root finds nothing to stop; the ORIGINAL argv reaches start.sh
# unmodified, which does its own resolution). Proven via a pre-existing
# listener on the root portal port: start.sh's OWN pre-spawn refusal
# ("already running") is a fast, deterministic tell that start's own
# resolution logic ran, not some restart-specific shortcut.
# ---------------------------------------------------------------------------
FAKE20B="$WORK/repo20b"
make_fake_repo "$FAKE20B" >/dev/null
make_fake_venv "$FAKE20B"
PORT20B="$(cli_test_random_port)"; cli_test_assert_port_safe "$PORT20B"
write_lab_conf "$FAKE20B" "$PORT20B" "$((PORT20B + 1))" "$((PORT20B + 2))" "$((PORT20B + 3))" "$((PORT20B + 4))"
"$REAL_VENV/bin/python" - "$WORK/busy20b.pid" "$PORT20B" <<'PY' &
import socket, sys, time
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(("127.0.0.1", int(sys.argv[2])))
s.listen(1)
open(sys.argv[1], "w").write("bound")
time.sleep(15)
PY
busy20b_pid=$!
for _ in 1 2 3 4 5 6 7 8 9 10; do
    [[ -f "$WORK/busy20b.pid" ]] && break
    sleep 0.3
done
out20b="$( cd "$FAKE20B" && HOME="$FAKE_HOME" PATH="$SAFE_PATH" ARAIL_NO_BROWSER=1 \
    _timeout 15 bash arailctl restart </dev/null 2>&1 )"
rc20b=$?
kill "$busy20b_pid" 2>/dev/null || true; wait "$busy20b_pid" 2>/dev/null || true
[[ "$rc20b" == "1" ]] || fail "T20b: expected exit 1 (start's own 'already running' refusal), got $rc20b — output:\n$out20b"
echo "$out20b" | grep -qi "already running" || fail "T20b: bare restart with 0 live instances did not fall through to start's own resolution — output:\n$out20b"
ok_scenario

# ---------------------------------------------------------------------------
# T20(c) / F12: bare `restart`, >=2 live instances -> exit 2, naming each
# `restart --world <slug>` plus `--root` — NO stop is attempted for this
# branch (neither instance is touched).
# ---------------------------------------------------------------------------
FAKE20C="$WORK/repo20c"
make_fake_repo "$FAKE20C" >/dev/null
make_fake_venv "$FAKE20C"
PORT_X="$(cli_test_random_port)"; cli_test_assert_port_safe "$PORT_X"
PORT_Y=$((PORT_X + 1))
cli_test_write_stub_ps_for_slugs "$FAKE20C/stubbin" "x:${PORT_X}" "y:${PORT_Y}"
cli_test_fabricate_live_instance "$FAKE20C" x "$PORT_X"; pid_x="$CLI_TEST_LAST_FABRICATED_PID"
cli_test_fabricate_live_instance "$FAKE20C" y "$PORT_Y"; pid_y="$CLI_TEST_LAST_FABRICATED_PID"

out20c="$( cd "$FAKE20C" && HOME="$FAKE_HOME" PATH="$FAKE20C/stubbin:$SAFE_PATH" ARAIL_NO_BROWSER=1 \
    _timeout 15 bash arailctl restart </dev/null 2>&1 )"
rc20c=$?
[[ "$rc20c" == "2" ]] || fail "T20c/F12: expected exit 2, got $rc20c — output:\n$out20c"
echo "$out20c" | grep -q -- "restart --world x" || fail "T20c/F12: no restart --world x hint — output:\n$out20c"
echo "$out20c" | grep -q -- "restart --world y" || fail "T20c/F12: no restart --world y hint — output:\n$out20c"
echo "$out20c" | grep -q -- "restart --root" || fail "T20c/F12: no restart --root hint — output:\n$out20c"
[[ -f "$FAKE20C/lab/instances/registry.d/x.json" ]] || fail "T20c/F12: x's record was removed — no stop should be attempted when the target is ambiguous"
[[ -f "$FAKE20C/lab/instances/registry.d/y.json" ]] || fail "T20c/F12: y's record was removed — no stop should be attempted when the target is ambiguous"
kill -0 "$pid_x" 2>/dev/null || fail "T20c/F12: x's process was killed despite the ambiguity refusal"
kill -0 "$pid_y" 2>/dev/null || fail "T20c/F12: y's process was killed despite the ambiguity refusal"
ok_scenario

# ---------------------------------------------------------------------------
# T20(d): `restart --all` -> exit 2, explicit refusal (needs a supervisor,
# §3.2) — reuses the same 2-live-instance repo; neither instance touched.
# ---------------------------------------------------------------------------
out20d="$( cd "$FAKE20C" && HOME="$FAKE_HOME" PATH="$FAKE20C/stubbin:$SAFE_PATH" ARAIL_NO_BROWSER=1 \
    _timeout 15 bash arailctl restart --all </dev/null 2>&1 )"
rc20d=$?
[[ "$rc20d" == "2" ]] || fail "T20d: expected exit 2, got $rc20d — output:\n$out20d"
echo "$out20d" | grep -qi "not supported" || fail "T20d: no 'not supported' explanation — output:\n$out20d"
echo "$out20d" | grep -qi -- "stop --all" || fail "T20d: no 'stop --all' escape hatch mentioned — output:\n$out20d"
[[ -f "$FAKE20C/lab/instances/registry.d/x.json" ]] || fail "T20d: x's record was removed — --all must refuse before touching anything"
[[ -f "$FAKE20C/lab/instances/registry.d/y.json" ]] || fail "T20d: y's record was removed — --all must refuse before touching anything"
ok_scenario
kill "$pid_x" 2>/dev/null || true; wait "$pid_x" 2>/dev/null || true
kill "$pid_y" 2>/dev/null || true; wait "$pid_y" 2>/dev/null || true

# ---------------------------------------------------------------------------
# T21(a): the stop phase itself fails -> start is never attempted, exit 1.
# reset.sh/start.sh are swapped for tiny stand-ins for JUST this scenario —
# this targets ARAILCTL's OWN stop-then-start control flow (does it abort
# before starting when the stop's exit code is nonzero?), not reset.sh's
# internal stop logic (covered elsewhere, e.g. tests/test_reset_stop_scope.py)
# — a deliberate, narrow exception to "always drive the real scripts."
# ---------------------------------------------------------------------------
FAKE21A="$WORK/repo21a"
make_fake_repo "$FAKE21A" >/dev/null
cat > "$FAKE21A/scripts/reset.sh" <<'EOF'
#!/usr/bin/env bash
exit 9
EOF
cat > "$FAKE21A/scripts/start.sh" <<'EOF'
#!/usr/bin/env bash
echo "START_WAS_INVOKED"
exit 0
EOF
chmod +x "$FAKE21A/scripts/reset.sh" "$FAKE21A/scripts/start.sh"
out21a="$( cd "$FAKE21A" && HOME="$FAKE_HOME" PATH="$SAFE_PATH" ARAIL_NO_BROWSER=1 \
    _timeout 10 bash arailctl restart --root </dev/null 2>&1 )"
rc21a=$?
[[ "$rc21a" == "1" ]] || fail "T21a: expected exit 1 when the stop phase fails, got $rc21a — output:\n$out21a"
echo "$out21a" | grep -qi "start not attempted" || fail "T21a: no 'start not attempted' message — output:\n$out21a"
echo "$out21a" | grep -q "START_WAS_INVOKED" && fail "T21a: start.sh was invoked despite the stop phase failing — output:\n$out21a"
ok_scenario

# ---------------------------------------------------------------------------
# F9: daemon-mode edge cases — `restart --world x` / `restart --root` must
# refuse (never silently kickstart the root daemon instead). A stub
# launchctl logs every invocation so "kickstart was never reached" is an
# assertion, not an inference. Placed LAST in this driver (mirrors
# root_start_driver.sh's own T17 ordering): once the plist file exists in
# the shared $FAKE_HOME, a LATER scenario using a bare $SAFE_PATH (the
# real system launchctl) would otherwise see whatever this dev machine's
# REAL launchd actually reports for io.arail.portal.
# ---------------------------------------------------------------------------
FAKEF9="$WORK/repof9"
make_fake_repo "$FAKEF9" >/dev/null
mkdir -p "$FAKE_HOME/Library/LaunchAgents"
: > "$FAKE_HOME/Library/LaunchAgents/io.arail.portal.plist"
mkdir -p "$FAKEF9/stubbin"
F9_LAUNCHCTL_LOG="$WORK/f9-launchctl.log"
cat > "$FAKEF9/stubbin/launchctl" <<EOF
#!/usr/bin/env bash
echo "\$@" >> "$F9_LAUNCHCTL_LOG"
case "\$1 \$2" in
    "list io.arail.portal") echo '        "PID" = 4242;'; exit 0 ;;
esac
exit 0
EOF
chmod +x "$FAKEF9/stubbin/launchctl"

: > "$F9_LAUNCHCTL_LOG"
out_f9a="$( cd "$FAKEF9" && HOME="$FAKE_HOME" PATH="$FAKEF9/stubbin:$SAFE_PATH" ARAIL_NO_BROWSER=1 \
    _timeout 10 bash arailctl restart --world someworld </dev/null 2>&1 )"
rc_f9a=$?
[[ "$rc_f9a" == "1" ]] || fail "F9(a): expected exit 1, got $rc_f9a — output:\n$out_f9a"
echo "$out_f9a" | grep -qi "single-instance" || fail "F9(a): no single-instance refusal message — output:\n$out_f9a"
grep -q "kickstart" "$F9_LAUNCHCTL_LOG" && fail "F9(a): kickstart was invoked despite the daemon-mode --world refusal"
ok_scenario

: > "$F9_LAUNCHCTL_LOG"
out_f9b="$( cd "$FAKEF9" && HOME="$FAKE_HOME" PATH="$FAKEF9/stubbin:$SAFE_PATH" ARAIL_NO_BROWSER=1 \
    _timeout 10 bash arailctl restart --root </dev/null 2>&1 )"
rc_f9b=$?
[[ "$rc_f9b" == "1" ]] || fail "F9(b): expected exit 1, got $rc_f9b — output:\n$out_f9b"
echo "$out_f9b" | grep -qi "redundant" || fail "F9(b): no redundant-with-daemon refusal message — output:\n$out_f9b"
grep -q "kickstart" "$F9_LAUNCHCTL_LOG" && fail "F9(b): kickstart was invoked despite the daemon-mode --root refusal"
ok_scenario

echo "OK: ${pass_count} scenario(s) passed — --root flag + restart redesign (T18-T21, F9, F11, F12, F13)"
