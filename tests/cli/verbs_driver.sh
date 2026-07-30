#!/usr/bin/env bash
# tests/cli/verbs_driver.sh — exit-code matrix regression driver
# (sprints/2026-07-29-elite-cli/ARCHITECTURE.md §12, WP1). Gates: T6, T7
# (partial — this driver covers the rows this sprint's WP1+WP2 actually
# changed; later work packages grow this file as restart/install/status
# gain their own exit-code contracts), T9, F33.
#
# Every invocation is non-tty (`</dev/null`, captured stdout) — F8: no
# verb may prompt or hang with no tty.
set -uo pipefail

DRIVER_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "$DRIVER_DIR/lib.sh"

fail() { echo "FAIL: $1" >&2; exit 1; }
pass_count=0
ok_scenario() { pass_count=$((pass_count + 1)); }

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# ---------------------------------------------------------------------------
# F33: every `case` arm in arailctl appears somewhere in docs/cli.md (drift
# guard — cheap enough to run unconditionally, no venv needed).
# ---------------------------------------------------------------------------
_arailctl_verbs="$(grep -oE '^[[:space:]]{4}[a-zA-Z][a-zA-Z0-9_-]*(\|[a-zA-Z0-9_-]+)*\)' "$CLI_TEST_REPO/arailctl" \
    | sed -E 's/^[[:space:]]+//; s/\)$//' \
    | tr '|' '\n' \
    | sort -u)"
_missing=""
while IFS= read -r v; do
    [[ -n "$v" ]] || continue
    case "$v" in
        min|max) continue ;;  # tier-name case arm, not a verb
    esac
    grep -qF "$v" "$CLI_TEST_REPO/docs/cli.md" || _missing="${_missing}${v} "
done <<< "$_arailctl_verbs"
if [[ -n "$_missing" ]]; then
    fail "F33: docs/cli.md is missing these arailctl verbs: $_missing"
fi
ok_scenario

# ---------------------------------------------------------------------------
# T7 (setup rows): unknown flag -> exit 2, non-tty, no mutation (checked
# by running against a COPY of setup.sh, never the real repo).
# ---------------------------------------------------------------------------
fake_setup="$WORK/setup-repo"
mkdir -p "$fake_setup"
cp "$CLI_TEST_REPO/scripts/setup.sh" "$fake_setup/setup.sh"
out="$( cd "$fake_setup" && bash setup.sh --totally-bogus-flag </dev/null 2>&1 )"
rc=$?
[[ "$rc" == "2" ]] || fail "setup unknown flag: expected exit 2, got $rc — output:\n$out"
echo "$out" | grep -qi "unknown flag" || fail "setup unknown flag: no 'unknown flag' message — output:\n$out"
[[ ! -e "$fake_setup/.env" ]] || fail "setup unknown flag: must exit before writing .env"
ok_scenario

# ---------------------------------------------------------------------------
# T9: doctor's exit-code contract.
# ---------------------------------------------------------------------------
if [[ -z "$REAL_VENV" ]]; then
    echo "SKIP: doctor scenarios (T9) — no usable .venv found"
else
    # (a) healthy: uvicorn present, ttyd/code-server/model absent (the CI
    # invariant, A8) -> 0.
    fake_a="$WORK/doctor-a"
    make_fake_repo "$fake_a" >/dev/null
    make_fake_venv "$fake_a"
    link_real_uvicorn "$fake_a"
    out_a="$( cd "$fake_a" && PATH="/usr/bin:/bin:/usr/sbin:/sbin" bash arailctl doctor 2>&1 )"
    rc_a=$?
    [[ "$rc_a" == "0" ]] || fail "doctor healthy: expected exit 0, got $rc_a — output:\n$out_a"
    ok_scenario

    # (b) uvicorn removed from PATH (and absent from the fake venv, since
    # make_fake_venv never puts one there unless link_real_uvicorn is
    # called) -> 3.
    fake_b="$WORK/doctor-b"
    make_fake_repo "$fake_b" >/dev/null
    make_fake_venv "$fake_b"
    out_b="$( cd "$fake_b" && PATH="/usr/bin:/bin:/usr/sbin:/sbin" bash arailctl doctor 2>&1 )"
    rc_b=$?
    [[ "$rc_b" == "3" ]] || fail "doctor uvicorn-missing: expected exit 3, got $rc_b — output:\n$out_b"
    echo "$out_b" | grep -qi "missing: uvicorn" || fail "doctor uvicorn-missing: no 'missing: uvicorn' line — output:\n$out_b"
    ok_scenario

    # (c) no .venv at all -> 1.
    fake_c="$WORK/doctor-c"
    make_fake_repo "$fake_c" >/dev/null
    out_c="$( cd "$fake_c" && PATH="/usr/bin:/bin:/usr/sbin:/sbin" bash arailctl doctor 2>&1 )"
    rc_c=$?
    [[ "$rc_c" == "1" ]] || fail "doctor no-venv: expected exit 1, got $rc_c — output:\n$out_c"
    ok_scenario

    # (d) --strict with an optional binary missing (ttyd/jupyter/code-server
    # all absent here) -> 3.
    fake_d="$WORK/doctor-d"
    make_fake_repo "$fake_d" >/dev/null
    make_fake_venv "$fake_d"
    link_real_uvicorn "$fake_d"
    out_d="$( cd "$fake_d" && PATH="/usr/bin:/bin:/usr/sbin:/sbin" bash arailctl doctor --strict 2>&1 )"
    rc_d=$?
    [[ "$rc_d" == "3" ]] || fail "doctor --strict optional-missing: expected exit 3, got $rc_d — output:\n$out_d"
    ok_scenario
fi

echo "OK: ${pass_count} scenario(s) passed — verb exit-code matrix (T6/T7 partial, T9, F33)"
