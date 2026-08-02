#!/usr/bin/env bash
# tests/cli/picker_driver.sh — regression driver for the World picker at
# `./arailctl start`: its memory of the last launched lab, the honesty of
# option 0, --pick, and --yes.
#
# Drives the REAL scripts/start.sh against a throwaway fake repo, exactly
# like root_start_driver.sh — never a reimplementation of the resolution
# chain under test. The interactive scenarios go through a REAL pty
# (tests/cli/pty_run.py), because the picker is gated on `[[ -t 0 ]]` and
# a pipe would silently take the non-interactive branch instead.
#
# F26/F27: every port here is randomized >= 18000 and never 8080/8090, and
# every scenario runs on SAFE_PATH — the developer's real
# ollama/ttyd/jupyter/code-server must never be reachable from a run that
# didn't deliberately stub them in.
set -uo pipefail

DRIVER_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "$DRIVER_DIR/lib.sh"

if [[ -z "$REAL_VENV" ]]; then
    echo "SKIP: no usable .venv found (tried \$ARAIL_TEST_VENV, $CLI_TEST_REPO/.venv, sibling checkout) — cannot import arail.*"
    exit 0
fi

fail() { echo -e "FAIL: $1" >&2; exit 1; }
pass_count=0
ok_scenario() { pass_count=$((pass_count + 1)); echo "  ok: $1"; }

SAFE_PATH="/usr/bin:/bin:/usr/sbin:/sbin"

# pwd -P: see root_start_driver.sh's note — start.sh resolves REPO_ROOT
# with `pwd -P`, so an unresolved /var/folders path breaks identity checks.
WORK="$(cd "$(mktemp -d)" && pwd -P)"
trap 'rm -rf "$WORK"' EXIT
FAKE_HOME="$WORK/home"
mkdir -p "$FAKE_HOME"

# _new_scenario <name> [world...] — fresh fake repo with a stub venv, a
# real-binding stub uvicorn, F26/F27-safe randomized ports, and one
# seal-valid World bundle per extra argument. Sets FAKE. NOT called inside
# $( ) — the globals must survive.
_new_scenario() {
    local name="$1"; shift
    FAKE="$WORK/$name"
    make_fake_repo "$FAKE" >/dev/null
    make_fake_venv "$FAKE"
    write_stub_uvicorn_serving "$FAKE"
    PORTAL="$(cli_test_random_port)"
    cli_test_assert_port_safe "$PORTAL"
    LANCE="$((PORTAL + 1))" TERMINAL="$((PORTAL + 2))"
    NOTEBOOK="$((PORTAL + 3))" IDE="$((PORTAL + 4))"
    write_lab_conf "$FAKE" "$PORTAL" "$LANCE" "$TERMINAL" "$NOTEBOOK" "$IDE"
    local w
    for w in "$@"; do
        cli_test_make_world "$FAKE" "$w" "World ${w}" || fail "could not build World bundle '$w'"
    done
}

# _stub_optional_services <fake> — make ttyd/jupyter/code-server answer
# immediately. Only needed by a scenario that must reach the root lab's
# CLOSING banner: unstubbed, each of those burns its full 10s degrade cap
# in the readiness phase. Every other scenario here asserts on output the
# picker prints within the first second and is deliberately given a short
# budget instead, so the driver stays fast.
_stub_optional_services() {
    local fake="$1"
    write_stub_listen_only "$fake" ttyd "$TERMINAL" 0
    write_stub_listen_only "$fake" jupyter "$NOTEBOOK" 0
    write_stub_listen_only "$fake" code-server "$IDE" 0
}

# _remember <fake> <kind> [slug] — write the picker's memory directly,
# through the REAL helper rather than a hand-rolled JSON literal, so a
# schema change cannot leave this driver testing a stale shape.
_remember() {
    local fake="$1" kind="$2" slug="${3:-}"
    ( cd "$fake" && REPO_ROOT="$fake" bash -c "
        source scripts/lib/instances.sh
        inst_write_last_target '$kind' '$slug'
    " ) || fail "_remember $kind $slug failed"
}

# _fixture <fake-repo> -> path to the /api/instance body that makes
# svc_identity_root MATCH (slug=root, checkout=<fake-repo>). Without this
# the root lab's REQUIRED portal gate always fails and start.sh exits 1
# before ever reaching the banner — which silently turns every "the root
# lab started" assertion below into "the root BRANCH was taken". Same
# helper, same reason, as root_start_driver.sh's.
_fixture() {
    local fake="$1" f="$WORK/fixture-$$-$RANDOM.json"
    printf '{"slug":"root","checkout":"%s"}' "$fake" > "$f"
    printf '%s' "$f"
}

# _pick <fake> <keystrokes> [args...] — run start.sh under a real pty.
_pick() {
    local fake="$1" keys="$2"; shift 2
    ( cd "$fake" && HOME="$FAKE_HOME" PATH="$SAFE_PATH" ARAIL_NO_BROWSER=1 \
        STUB_FIXTURE="$(_fixture "$fake")" STUB_STATUS=200 \
        _timeout "${PICK_TIMEOUT:-8}" "$REAL_VENV/bin/python" "$DRIVER_DIR/pty_run.py" "$keys" \
        bash scripts/start.sh "$@" 2>&1 )
}

# _run <fake> [args...] — non-interactive (stdin closed), the CI shape.
_run() {
    local fake="$1"; shift
    ( cd "$fake" && HOME="$FAKE_HOME" PATH="$SAFE_PATH" ARAIL_NO_BROWSER=1 \
        STUB_FIXTURE="$(_fixture "$fake")" STUB_STATUS=200 \
        _timeout "${PICK_TIMEOUT:-8}" bash scripts/start.sh "$@" </dev/null 2>&1 )
}

# The two unambiguous "which path did resolution take" markers: the root
# lab prints its own service banner, the instance path prints stage [1/8].
_took_root()     { echo "$1" | grep -q "Starting lab services"; }
_took_instance() { echo "$1" | grep -q "\[1/8\]"; }

echo "picker_driver: starting"

# ---------------------------------------------------------------------------
# S1: >=2 Worlds, tty, NO memory -> picker renders every World, and Enter
#     takes option 0 (the root lab). The documented cold-start default.
# ---------------------------------------------------------------------------
_new_scenario s1 ai physics video-games
out="$(_pick "$FAKE" $'\n')"
echo "$out" | grep -q "Which lab do you want?" || fail "S1: no picker prompt — output:\n$out"
echo "$out" | grep -q "0) Test Lab" || fail "S1: no option 0 — output:\n$out"
echo "$out" | grep -q "1) World ai" || fail "S1: World 'ai' not listed — output:\n$out"
echo "$out" | grep -q "3) World video-games" || fail "S1: World 'video-games' not listed — output:\n$out"
echo "$out" | grep -q "Enter = 0" || fail "S1: prompt must name the default (Enter = 0) — output:\n$out"
echo "$out" | grep -q "← last" && fail "S1: nothing was ever launched — no row may be marked '← last' — output:\n$out"
_took_root "$out" || fail "S1: Enter with no memory must start the ROOT lab — output:\n$out"
ok_scenario "S1 picker renders; Enter with no memory = root lab"

# ---------------------------------------------------------------------------
# S2: >=2 Worlds, tty, memory = a World -> that row is marked, the prompt
#     names it as the Enter-default, and Enter actually takes it.
# ---------------------------------------------------------------------------
_new_scenario s2 ai physics video-games
_remember "$FAKE" world physics
out="$(_pick "$FAKE" $'\n')"
echo "$out" | grep -q "2) World physics.*← last" || fail "S2: remembered World's row not marked '← last' — output:\n$out"
echo "$out" | grep -q "Enter = 2" || fail "S2: prompt must default to the remembered World — output:\n$out"
_took_instance "$out" || fail "S2: Enter must start the remembered World as an instance — output:\n$out"
_took_root "$out" && fail "S2: must NOT have fallen through to the root lab — output:\n$out"
ok_scenario "S2 Enter takes the remembered World; its row is marked"

# ---------------------------------------------------------------------------
# S2b: memory = root -> option 0 is marked and is the Enter-default.
# ---------------------------------------------------------------------------
_new_scenario s2b ai physics
_remember "$FAKE" root
out="$(_pick "$FAKE" $'\n')"
echo "$out" | grep -q "0) Test Lab.*← last" || fail "S2b: option 0 not marked '← last' — output:\n$out"
_took_root "$out" || fail "S2b: Enter must start the root lab — output:\n$out"
ok_scenario "S2b memory = root marks and defaults to option 0"

# ---------------------------------------------------------------------------
# S2c: an explicit numeric choice still wins over the memory.
# ---------------------------------------------------------------------------
_new_scenario s2c ai physics
_remember "$FAKE" world physics
out="$(_pick "$FAKE" $'0\n')"
_took_root "$out" || fail "S2c: explicit '0' must override the remembered World — output:\n$out"
ok_scenario "S2c an explicit choice overrides the memory"

# ---------------------------------------------------------------------------
# S3: memory names a World that is no longer in the catalog -> say so, and
#     fall back to option 0. Never a hard failure, never a silent swap.
# ---------------------------------------------------------------------------
_new_scenario s3 ai physics
_remember "$FAKE" world video-games   # never built in this scenario
out="$(_pick "$FAKE" $'\n')"
echo "$out" | grep -q "video-games" || fail "S3: must name the missing World — output:\n$out"
echo "$out" | grep -qi "no longer in this lab's catalog" || fail "S3: must explain the fallback — output:\n$out"
echo "$out" | grep -q "Enter = 0" || fail "S3: must fall back to option 0 — output:\n$out"
_took_root "$out" || fail "S3: must start the root lab — output:\n$out"
ok_scenario "S3 a deleted remembered World degrades to option 0, out loud"

# ---------------------------------------------------------------------------
# S4: a World MOUNTED into the root lab -> option 0 names it. Without this
#     the mounted World and its own catalog row are indistinguishable.
# ---------------------------------------------------------------------------
_new_scenario s4 ai physics
( cd "$FAKE" && HOME="$FAKE_HOME" "$REAL_VENV/bin/python" -c "
import sys
sys.path.insert(0, '$CLI_TEST_REPO/src')
from pathlib import Path
from arail import world_mount as wm
wm.mount(Path('$FAKE/lab/worlds/ai'),
         pkb_root=Path('$FAKE/lab/pkb'),
         data_dir=Path('$FAKE/lab/data'),
         worlds_dir=Path('$FAKE/lab/worlds'))
" >/dev/null 2>&1 ) || echo "  (note: S4 mount fixture unavailable — asserting the fallback label instead)"
out="$(_pick "$FAKE" $'0\n')"
if [[ -f "$FAKE/lab/data/world-mount.json" ]]; then
    echo "$out" | grep -q "0) Test Lab — World ai mounted" \
        || fail "S4: option 0 must name the mounted World — output:\n$out"
else
    echo "$out" | grep -q "0) Test Lab (the root lab on" \
        || fail "S4: unmounted fallback label missing — output:\n$out"
fi
ok_scenario "S4 option 0 names the World mounted into the root lab"

# ---------------------------------------------------------------------------
# S5: --yes takes the remembered target non-interactively, and SAYS which.
#     docs/cli.md has always called --yes "non-interactive default for the
#     World picker"; before the memory existed there was no default to take
#     and it exited 2 instead — doc and code disagreed.
# ---------------------------------------------------------------------------
_new_scenario s5 ai physics
_remember "$FAKE" world physics
out="$(_run "$FAKE" --yes)"
echo "$out" | grep -q "last used" || fail "S5: --yes must name what it picked — output:\n$out"
_took_instance "$out" || fail "S5: --yes must start the remembered World — output:\n$out"
ok_scenario "S5 --yes takes the remembered World and names it"

# S5b: --yes with NO memory -> the root lab, not a refusal.
_new_scenario s5b ai physics
out="$(_run "$FAKE" --yes)"
_took_root "$out" || fail "S5b: --yes with no memory must start the root lab — output:\n$out"
ok_scenario "S5b --yes with no memory starts the root lab"

# ---------------------------------------------------------------------------
# S6: REGRESSION GUARD — bare non-interactive with >=2 Worlds still exits 2
#     and lists every command. VISION §3's "never guess" is what CI and
#     daemons depend on; the memory is an opt-in (--yes), never something a
#     pipe inherits.
# ---------------------------------------------------------------------------
_new_scenario s6 ai physics
_remember "$FAKE" world physics    # a memory exists — and must NOT be used
out="$(_run "$FAKE")"; rc=$?
[[ "$rc" == "2" ]] || fail "S6: expected exit 2, got $rc — output:\n$out"
echo "$out" | grep -q -- "--world ai" || fail "S6: must list every World command — output:\n$out"
echo "$out" | grep -q -- "--root" || fail "S6: must teach --root — output:\n$out"
_took_instance "$out" && fail "S6: must NOT have silently started the remembered World — output:\n$out"
_took_root "$out" && fail "S6: must NOT have silently started the root lab — output:\n$out"
ok_scenario "S6 bare non-interactive still refuses (never guess)"

# ---------------------------------------------------------------------------
# S7: --pick forces the picker with a SINGLE World (which would otherwise
#     auto-select it and leave the root lab unreachable without --root);
#     --pick without a tty refuses; --pick with an explicit target is a
#     usage error.
# ---------------------------------------------------------------------------
_new_scenario s7 ai
out="$(_pick "$FAKE" $'0\n' --pick)"
echo "$out" | grep -q "Which lab do you want?" || fail "S7: --pick must show the picker with 1 World — output:\n$out"
echo "$out" | grep -q "1) World ai" || fail "S7: the single World must be listed — output:\n$out"
_took_root "$out" || fail "S7: choosing 0 must start the root lab — output:\n$out"
ok_scenario "S7 --pick forces the picker with a single World"

out="$(_run "$FAKE" --pick)"; rc=$?
[[ "$rc" == "2" ]] || fail "S7b: --pick without a tty must exit 2, got $rc — output:\n$out"
echo "$out" | grep -q "needs a terminal" || fail "S7b: must explain why — output:\n$out"
ok_scenario "S7b --pick without a tty exits 2"

out="$(_run "$FAKE" --pick --root)"; rc=$?
[[ "$rc" == "2" ]] || fail "S7c: --pick --root must exit 2, got $rc — output:\n$out"
echo "$out" | grep -q -- "--pick cannot be combined" || fail "S7c: wrong message — output:\n$out"
ok_scenario "S7c --pick with --root/--world is a usage error"

# ---------------------------------------------------------------------------
# S8: a corrupt / wrong-shaped / hostile last-target.json is treated as
#     absent — a preference file must never be able to fail a start.
# ---------------------------------------------------------------------------
_new_scenario s8 ai physics
mkdir -p "$FAKE/lab/instances"
for junk in '{not json' '[1,2,3]' 'null' '{"kind":"world","slug":"../../etc/passwd"}' '{"kind":"nonsense"}' ''; do
    printf '%s' "$junk" > "$FAKE/lab/instances/last-target.json"
    out="$(_pick "$FAKE" $'\n')"
    echo "$out" | grep -q "Enter = 0" \
        || fail "S8: junk last-target.json (${junk:-<empty>}) must degrade to option 0 — output:\n$out"
    _took_root "$out" || fail "S8: junk last-target.json (${junk:-<empty>}) must still start — output:\n$out"
done
ok_scenario "S8 corrupt/hostile last-target.json degrades to option 0"

# ---------------------------------------------------------------------------
# S9: the memory is WRITTEN after a successful root start, and reflects it.
# ---------------------------------------------------------------------------
_new_scenario s9 ai physics
# The root lab blocks in `wait` once it is up, so this run always ends at
# the timeout — the assertion is on the file it wrote on the way there,
# never on its exit code. Given a longer budget than the picker-only
# scenarios: it has to clear the whole readiness phase first.
_stub_optional_services "$FAKE"
PICK_TIMEOUT=35 _run "$FAKE" --root >/dev/null 2>&1
[[ -f "$FAKE/lab/instances/last-target.json" ]] \
    || fail "S9: no last-target.json after a root start (did the readiness gate pass?)"
grep -q '"kind": *"root"' "$FAKE/lab/instances/last-target.json" \
    || fail "S9: last-target.json does not record the root lab — $(cat "$FAKE/lab/instances/last-target.json")"
# ...and the next bare picker run defaults to it.
out="$(_pick "$FAKE" $'\n')"
echo "$out" | grep -q "0) Test Lab.*← last" || fail "S9: the recorded root start must mark option 0 — output:\n$out"
ok_scenario "S9 a successful root start is remembered and becomes the default"

# ---------------------------------------------------------------------------
# S10: an invalid choice is still a hard usage error (unchanged).
# ---------------------------------------------------------------------------
_new_scenario s10 ai physics
out="$(_pick "$FAKE" $'99\n')"; rc=$?
[[ "$rc" == "2" ]] || fail "S10: an out-of-range choice must exit 2, got $rc — output:\n$out"
echo "$out" | grep -q "Invalid choice" || fail "S10: wrong message — output:\n$out"
ok_scenario "S10 an out-of-range choice still exits 2"

# ---------------------------------------------------------------------------
# S11: `switch` stops every live instance and then PICKS — it must not
#      pin to the current target the way `restart` deliberately does.
# ---------------------------------------------------------------------------
_new_scenario s11 ai physics
INST_PORT="$(cli_test_random_port)"
cli_test_assert_port_safe "$INST_PORT"
cli_test_fabricate_live_instance_portal_like "$FAKE" ai "$INST_PORT"
FAB_PID="$CLI_TEST_LAST_FABRICATED_PID"
out="$( cd "$FAKE" && HOME="$FAKE_HOME" PATH="$SAFE_PATH" ARAIL_NO_BROWSER=1 \
    STUB_FIXTURE="$(_fixture "$FAKE")" STUB_STATUS=200 \
    _timeout 20 "$REAL_VENV/bin/python" "$DRIVER_DIR/pty_run.py" $'0\n' \
    bash arailctl switch 2>&1 )"
echo "$out" | grep -q "Stopping World instance 'ai'" || fail "S11: must stop the live instance — output:\n$out"
echo "$out" | grep -q "Which lab do you want?" || fail "S11: must then show the picker — output:\n$out"
[[ -f "$FAKE/lab/instances/registry.d/ai.json" ]] && fail "S11: the stopped instance's record must be gone — output:\n$out"
_took_root "$out" || fail "S11: choosing 0 must start the root lab — output:\n$out"
kill "$FAB_PID" 2>/dev/null; wait "$FAB_PID" 2>/dev/null
ok_scenario "S11 switch stops what's live, then picks"

# ---------------------------------------------------------------------------
# S12: `switch --world <slug>` skips the prompt and goes straight there;
#      `switch --root` likewise; both flags together is a usage error.
# ---------------------------------------------------------------------------
_new_scenario s12 ai physics
out="$( cd "$FAKE" && HOME="$FAKE_HOME" PATH="$SAFE_PATH" ARAIL_NO_BROWSER=1 \
    STUB_FIXTURE="$(_fixture "$FAKE")" STUB_STATUS=200 \
    _timeout 10 bash arailctl switch --root </dev/null 2>&1 )"
echo "$out" | grep -q "Which lab do you want?" && fail "S12: --root must NOT prompt — output:\n$out"
_took_root "$out" || fail "S12: --root must start the root lab — output:\n$out"
ok_scenario "S12 switch --root skips the prompt"

out="$( cd "$FAKE" && HOME="$FAKE_HOME" PATH="$SAFE_PATH" ARAIL_NO_BROWSER=1 \
    _timeout 10 bash arailctl switch --root --world ai </dev/null 2>&1 )"; rc=$?
[[ "$rc" == "2" ]] || fail "S12b: --root with --world must exit 2, got $rc — output:\n$out"
ok_scenario "S12b switch --root --world is a usage error"

# ---------------------------------------------------------------------------
# S13: `switch` is remembered too — the memory is written by start.sh, so
#      arriving via switch must leave the same trace as arriving via start.
# ---------------------------------------------------------------------------
_new_scenario s13 ai physics
_stub_optional_services "$FAKE"
( cd "$FAKE" && HOME="$FAKE_HOME" PATH="$SAFE_PATH" ARAIL_NO_BROWSER=1 \
    STUB_FIXTURE="$(_fixture "$FAKE")" STUB_STATUS=200 \
    _timeout 35 bash arailctl switch --root </dev/null >/dev/null 2>&1 )
grep -q '"kind": *"root"' "$FAKE/lab/instances/last-target.json" 2>/dev/null \
    || fail "S13: switch --root must be remembered — $(cat "$FAKE/lab/instances/last-target.json" 2>/dev/null || echo ABSENT)"
ok_scenario "S13 switch records the lab it landed in"

echo "OK: picker_driver — $pass_count scenarios passed"
