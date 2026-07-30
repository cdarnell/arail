#!/usr/bin/env bash
# tests/cli/color_driver.sh — ANSI color-gating regression driver
# (sprints/2026-07-29-elite-cli/ARCHITECTURE.md §13 "ANSI leaks into
# non-tty output" / F25). Gate: T7 (part), F25.
#
# For each of arailctl, start.sh, status.sh, reset.sh, setup.sh: piped
# stdout (the default, non-tty) must carry zero ESC bytes; NO_COLOR=1 must
# do the same even if some future caller runs it against a real tty;
# ARAIL_COLOR=always must force ESC bytes even though stdout is piped
# here; ARAIL_COLOR=never must suppress them unconditionally.
#
# Every invocation here is side-effect-free (usage/help/--list banners, or
# an early-exit unknown-flag rejection) and runs against a throwaway fake
# repo — never the real one.
set -uo pipefail

DRIVER_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "$DRIVER_DIR/lib.sh"

fail() { echo "FAIL: $1" >&2; exit 1; }
pass_count=0
ok_scenario() { pass_count=$((pass_count + 1)); }

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
fake="$WORK/repo"
make_fake_repo "$fake" >/dev/null

_has_esc() {
    # 0 (true) iff the input contains a raw ESC byte (\x1b).
    printf '%s' "$1" | grep -qP '\x1b' 2>/dev/null && return 0
    printf '%s' "$1" | grep -q "$(printf '\033')" 2>/dev/null
}

# _assert_color_gating <label> <requires_color:0|1> <cmd...> — runs <cmd>
# four ways (default piped, NO_COLOR=1, ARAIL_COLOR=always,
# ARAIL_COLOR=never) and asserts ESC-byte presence/absence for each.
# <requires_color>=0 skips the "always must actually show color" half —
# some invocations (e.g. start.sh --list, which is pure python3-printed
# plain text) legitimately never emit a colored line at all; the point of
# testing them here is still "never leaks in the other three modes".
_assert_color_gating() {
    local label="$1" requires_color="$2"; shift 2
    local out

    out="$( "$@" 2>&1 )"
    _has_esc "$out" && fail "$label: default piped invocation leaked ANSI codes"

    out="$( NO_COLOR=1 "$@" 2>&1 )"
    _has_esc "$out" && fail "$label: NO_COLOR=1 leaked ANSI codes"

    out="$( ARAIL_COLOR=always "$@" 2>&1 )"
    if [[ "$requires_color" == "1" ]]; then
        _has_esc "$out" || fail "$label: ARAIL_COLOR=always produced no ANSI codes at all"
    fi

    out="$( ARAIL_COLOR=never "$@" 2>&1 )"
    _has_esc "$out" && fail "$label: ARAIL_COLOR=never leaked ANSI codes"

    ok_scenario
}

_assert_color_gating "arailctl help" 1 bash "$fake/arailctl" help
_assert_color_gating "start.sh --list" 0 bash -c "cd '$fake' && bash scripts/start.sh --list"
_assert_color_gating "status.sh" 1 bash -c "cd '$fake' && bash scripts/status.sh"
_assert_color_gating "reset.sh --help" 1 bash -c "cd '$fake' && bash scripts/reset.sh --help"
_assert_color_gating "setup.sh unknown flag" 1 bash -c "cd '$fake' && bash scripts/setup.sh --totally-bogus-flag </dev/null"

echo "OK: ${pass_count} scenario(s) passed — ANSI color gating"
