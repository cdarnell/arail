#!/usr/bin/env bash
# tests/cli/warmup_driver.sh — regression driver for `start --warm`
# (sprints/2026-07-29-elite-cli/ARCHITECTURE.md §11, WP6). Gate: T23.
#
# Drives the REAL scripts/start.sh root path against a throwaway fake repo
# with the REAL-BINDING stub uvicorn (tests/cli/stub_uvicorn_serving.py via
# tests/cli/lib.sh — the same enabling capability root_start_driver.sh
# uses), dialing the /api/instance body's warm/warm_ms/backend/warm_skipped
# fields per scenario.
#
# The instance path shares the exact same _warm_report() helper (called
# with a different URL) — rather than re-standing-up the instance path's
# own identity dance (a random UUID token minted INSIDE _instance_start,
# which a static fixture file cannot predict), this driver pins the
# instance path's WIRING with cheap source-text assertions (the shared
# helper's actual polling/reporting behavior is already fully exercised
# below against the root path). See BUILD_LOG.md's WP6 section for why.
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

SAFE_PATH="/usr/bin:/bin:/usr/sbin:/sbin"

WORK="$(cd "$(mktemp -d)" && pwd -P)"
trap 'rm -rf "$WORK"' EXIT
FAKE_HOME="$WORK/home"
mkdir -p "$FAKE_HOME"

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

# _warm_fixture <fake-repo> <warm:true|false> [<warm_ms>] [<backend>] [<skipped>]
# [<omit_warm_fields:0|1>] — the last flag simulates an "older portal" whose
# /api/instance body has no warm/backend/warm_ms/warm_skipped keys at all
# (T23's "absent fields" case), rather than an explicit warm:false.
_warm_fixture() {
    local fake="$1" warm="$2" warm_ms="${3:-}" backend="${4:-}" skipped="${5:-}" omit="${6:-0}"
    local f="$WORK/warmfixture-$$-$RANDOM.json"
    if [[ "$omit" == "1" ]]; then
        printf '{"slug":"root","checkout":"%s"}' "$fake" > "$f"
        printf '%s' "$f"
        return 0
    fi
    local ms_json backend_json skipped_json
    [[ -n "$warm_ms" ]] && ms_json="$warm_ms" || ms_json="null"
    [[ -n "$backend" ]] && backend_json="\"$backend\"" || backend_json="null"
    [[ -n "$skipped" ]] && skipped_json="\"$skipped\"" || skipped_json="null"
    printf '{"slug":"root","checkout":"%s","warm":%s,"warm_ms":%s,"backend":%s,"warm_skipped":%s}' \
        "$fake" "$warm" "$ms_json" "$backend_json" "$skipped_json" > "$f"
    printf '%s' "$f"
}

# ---------------------------------------------------------------------------
# T23a: warm=true immediately, with backend + warm_ms -> one "warm-up: ✓"
# line naming the backend and a duration; exit code untouched (still
# running at the harness timeout, same as every other happy-path root-lab
# scenario); F14 (never blocks/gates readiness — the readiness banner
# above it must still print).
# ---------------------------------------------------------------------------
_new_scenario repo23a; fake23a="$FAKE"
fixture23a="$(_warm_fixture "$fake23a" true 4200 ollama_native)"
out23a="$( cd "$fake23a" && HOME="$FAKE_HOME" PATH="$SAFE_PATH" ARAIL_NO_BROWSER=1 \
    STUB_FIXTURE="$fixture23a" STUB_STATUS=200 \
    _timeout 8 bash scripts/start.sh --warm 2>&1 )"
rc23a=$?
[[ "$rc23a" == "124" ]] || fail "T23a: expected the lab to still be running at the timeout (rc 124), got $rc23a — output:\n$out23a"
echo "$out23a" | grep -q "✓ Portal" || fail "T23a: readiness banner missing — output:\n$out23a"
echo "$out23a" | grep -q "warm-up: ✓" || fail "T23a: no warm-up success line — output:\n$out23a"
echo "$out23a" | grep -q "ollama_native" || fail "T23a: warm-up line does not name the backend — output:\n$out23a"
echo "$out23a" | grep -Eq "warm-up: ✓ .* in 4\.2s" || fail "T23a: warm-up line missing the duration — output:\n$out23a"
ok_scenario

# ---------------------------------------------------------------------------
# T23b: warm=false forever -> after the (shortened, via ARAIL_WARM_TIMEOUT_
# SEC) cap, exactly one "⚠ not complete" line; exit code untouched (still
# running afterward — F14: a warm-up timeout never fails the start).
# ---------------------------------------------------------------------------
_new_scenario repo23b; fake23b="$FAKE"
fixture23b="$(_warm_fixture "$fake23b" false)"
out23b="$( cd "$fake23b" && HOME="$FAKE_HOME" PATH="$SAFE_PATH" ARAIL_NO_BROWSER=1 \
    ARAIL_WARM_TIMEOUT_SEC=2 \
    STUB_FIXTURE="$fixture23b" STUB_STATUS=200 \
    _timeout 8 bash scripts/start.sh --warm 2>&1 )"
rc23b=$?
[[ "$rc23b" == "124" ]] || fail "T23b: expected the lab to still be running at the timeout (rc 124), got $rc23b — output:\n$out23b"
echo "$out23b" | grep -q "warm-up: ⚠ not complete within 2s" || fail "T23b: no warm-up timeout line — output:\n$out23b"
echo "$out23b" | grep -q "warm-up: ✓" && fail "T23b: must NOT report success — output:\n$out23b"
ok_scenario

# ---------------------------------------------------------------------------
# T23c: /api/instance body has no warm/backend/warm_ms/warm_skipped keys at
# all (an "older portal") -> graceful degrade to the same timeout line, no
# crash, lab still comes up and keeps running.
# ---------------------------------------------------------------------------
_new_scenario repo23c; fake23c="$FAKE"
fixture23c="$(_warm_fixture "$fake23c" "" "" "" "" 1)"
out23c="$( cd "$fake23c" && HOME="$FAKE_HOME" PATH="$SAFE_PATH" ARAIL_NO_BROWSER=1 \
    ARAIL_WARM_TIMEOUT_SEC=2 \
    STUB_FIXTURE="$fixture23c" STUB_STATUS=200 \
    _timeout 8 bash scripts/start.sh --warm 2>&1 )"
rc23c=$?
[[ "$rc23c" == "124" ]] || fail "T23c: expected the lab to still be running at the timeout (rc 124), got $rc23c — output:\n$out23c"
echo "$out23c" | grep -q "✓ Portal" || fail "T23c: readiness banner missing — output:\n$out23c"
echo "$out23c" | grep -q "warm-up: ⚠ not complete within 2s" || fail "T23c: no graceful degrade line for the field-absent case — output:\n$out23c"
ok_scenario

# ---------------------------------------------------------------------------
# T23d (regression net): without --warm, no "warm-up:" line is ever
# printed — the flag is opt-in, not a new default line on every boot.
# ---------------------------------------------------------------------------
_new_scenario repo23d; fake23d="$FAKE"
fixture23d="$(_warm_fixture "$fake23d" true 100 ollama_native)"
out23d="$( cd "$fake23d" && HOME="$FAKE_HOME" PATH="$SAFE_PATH" ARAIL_NO_BROWSER=1 \
    STUB_FIXTURE="$fixture23d" STUB_STATUS=200 \
    _timeout 8 bash scripts/start.sh 2>&1 )"
rc23d=$?
[[ "$rc23d" == "124" ]] || fail "T23d: expected the lab to still be running at the timeout (rc 124), got $rc23d — output:\n$out23d"
echo "$out23d" | grep -q "warm-up:" && fail "T23d: a warm-up line was printed WITHOUT --warm — output:\n$out23d"
ok_scenario

# ---------------------------------------------------------------------------
# Instance-path wiring pin (see file header for why this is a source-text
# assertion rather than a second full end-to-end boot): --warm's env
# passthrough and _warm_report call must both be present in _instance_start,
# gated on $WARM_UP, using the instance's own portal_port.
# ---------------------------------------------------------------------------
_start_sh="$CLI_TEST_REPO/scripts/start.sh"
_warm_export_n="$(grep -c 'export ARAIL_TIER0_BOOT_WARM=1' "$_start_sh")"
[[ "$_warm_export_n" == "2" ]] \
    || fail "instance/root wiring: expected exactly 2 conditional ARAIL_TIER0_BOOT_WARM=1 exports (instance + root paths) in scripts/start.sh, found $_warm_export_n"
grep -q '\[\[ "\$WARM_UP" == "1" \]\]' "$_start_sh" \
    || fail "wiring: no \$WARM_UP conditional found in scripts/start.sh"
grep -F -q '_warm_report "http://${BIND}:${portal_port}/api/instance"' "$_start_sh" \
    || fail "instance-path wiring: _warm_report is not called against the instance's own /api/instance"
grep -F -q '_warm_report "http://${BIND}:${PORTAL_PORT:-8080}/api/instance"' "$_start_sh" \
    || fail "root-path wiring: _warm_report is not called against the root lab's own /api/instance"
ok_scenario

echo "OK: ${pass_count} scenario(s) passed — warm-up (T23)"
