#!/usr/bin/env bash
# tests/cli/restart_driver.sh — `--root` flag + `restart` redesign
# regression driver (sprints/2026-07-29-elite-cli/ARCHITECTURE.md §9, §10).
#
# WP3 ("--root for start/stop"): T18, F11.
# WP4 ("restart redesign", grown into this same file — both are grouped
# under the architecture's single "--root / restart:" test heading):
# T19-T21, F9, F12, F13.
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

echo "OK: ${pass_count} scenario(s) passed — --root flag (T18, F11)"
