#!/usr/bin/env bash
# tests/cli/install_driver.sh — regression driver for `install`
# (sprints/2026-07-29-elite-cli/ARCHITECTURE.md §6, WP7).
# Gates: T24-T28, F5-F7, F21, F22, F28, F32.
#
# Drives the REAL scripts/install.sh, scripts/update.sh, and arailctl
# against a throwaway fake repo tracking a REAL local bare git "remote"
# (tests/cli/lib.sh:cli_test_make_git_install_repo) — never a
# reimplementation of git plumbing or the phase logic under test.
#
# F26/F27: every port here is randomized >= 18000 and never 8080/8090
# (used only incidentally, via cli_test_fabricate_live_instance for T26).
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

# _run_install <fake-dir> [args...] — real scripts/install.sh, non-tty
# stdin (F8: never prompts), a sanitized PATH, isolated HOME.
_run_install() {
    local fake="$1"; shift
    ( cd "$fake" && HOME="$FAKE_HOME" PATH="$SAFE_PATH" \
        _timeout 30 bash scripts/install.sh "$@" </dev/null 2>&1 )
}

# _run_ctl <fake-dir> [args...] — the real arailctl entry point (for the
# tier/upgrade/update dispatch scenarios, T28).
_run_ctl() {
    local fake="$1"; shift
    ( cd "$fake" && HOME="$FAKE_HOME" PATH="$SAFE_PATH" \
        _timeout 30 bash arailctl "$@" </dev/null 2>&1 )
}

_write_pending_manifest() {
    local fake="$1"
    cat > "$fake/components.json" <<'EOF'
{
  "meta": {"schema_version": 1, "description": "install_driver.sh fixture"},
  "components": [
    {
      "name": "widget", "type": "system",
      "description": "synthetic test component",
      "version_cmd": "echo 1.0.0",
      "check_cmd": "echo 2.0.0 available",
      "update_cmd": "true",
      "post_update_cmd": null,
      "optional": false,
      "platforms": []
    }
  ]
}
EOF
}

_write_current_manifest() {
    local fake="$1"
    cat > "$fake/components.json" <<'EOF'
{
  "meta": {"schema_version": 1, "description": "install_driver.sh fixture"},
  "components": [
    {
      "name": "widget", "type": "system",
      "description": "synthetic test component",
      "version_cmd": "echo 1.0.0",
      "check_cmd": "",
      "update_cmd": "true",
      "post_update_cmd": null,
      "optional": false,
      "platforms": []
    }
  ]
}
EOF
}

_write_failing_apply_manifest() {
    local fake="$1"
    cat > "$fake/components.json" <<'EOF'
{
  "meta": {"schema_version": 1, "description": "install_driver.sh fixture"},
  "components": [
    {
      "name": "widget", "type": "system",
      "description": "synthetic test component whose update always fails",
      "version_cmd": "echo 1.0.0",
      "check_cmd": "echo 2.0.0 available",
      "update_cmd": "false",
      "post_update_cmd": null,
      "optional": false,
      "platforms": []
    }
  ]
}
EOF
}

# ---------------------------------------------------------------------------
# T24 / F5 / F28: clean tracking branch, one commit behind a local bare
# remote (the SOURCE PHASE itself modified between the two commits, so a
# marker only the NEW bytes print proves the re-exec actually ran the new
# script, not a cached copy of the old one) -> ff pull, old...new sha range
# printed, branch+toplevel printed (F28), exit 0.
# ---------------------------------------------------------------------------
fake24="$WORK/repo24"; bare24="$WORK/remote24.git"
cli_test_make_git_install_repo "$fake24" "$bare24"
cli_test_mark_provisioned "$fake24" hybrid
_new_install_sha="$(cli_test_publish_git_change "$bare24" main "scripts/install.sh" \
    "#!/usr/bin/env bash
echo 'T24_REEXEC_MARKER: this is the NEW install.sh' >&2
$(tail -n +2 "$fake24/scripts/install.sh")
")"
out24="$(_run_install "$fake24" --only source)"
rc24=$?
[[ "$rc24" == "0" ]] || fail "T24: expected exit 0, got $rc24 — output:\n$out24"
echo "$out24" | grep -q "T24_REEXEC_MARKER" || fail "T24: the re-exec did not run the NEW script's bytes — output:\n$out24"
echo "$out24" | grep -Eq '✓ [0-9a-f]{7}…[0-9a-f]{7} \(1 commit' || fail "T24: no old...new sha range printed — output:\n$out24"
echo "$out24" | grep -q "toplevel:" || fail "T24/F28: branch+toplevel not printed before pulling — output:\n$out24"
ok_scenario

# ---------------------------------------------------------------------------
# T25 / F6: five refusal reasons, each named, each exit 3, each leaving the
# worktree's HEAD sha unchanged (no stash/reset/clean/merge). One of the
# five (dirty tree) is combined with `--only source,verify` to also prove
# "remaining phases still run" after a refusal.
# ---------------------------------------------------------------------------
_t25_head() { git -C "$1" rev-parse HEAD 2>/dev/null; }

# (a) dirty tree — ALSO proves remaining phases still run.
fake25a="$WORK/repo25a"; bare25a="$WORK/remote25a.git"
cli_test_make_git_install_repo "$fake25a" "$bare25a"
cli_test_mark_provisioned "$fake25a" hybrid
link_real_uvicorn "$fake25a" || true
head_before_25a="$(_t25_head "$fake25a")"
: > "$fake25a/untracked.txt"
out25a="$(_run_install "$fake25a" --only source,verify)"
rc25a=$?
[[ "$rc25a" == "3" ]] || fail "T25a (dirty): expected exit 3, got $rc25a — output:\n$out25a"
echo "$out25a" | grep -qi "dirty" || fail "T25a: refusal did not name 'dirty' — output:\n$out25a"
echo "$out25a" | grep -q "\[5/5\] verify" || fail "T25a: verify phase did not run after the source refusal — output:\n$out25a"
[[ "$(_t25_head "$fake25a")" == "$head_before_25a" ]] || fail "T25a: HEAD moved despite the refusal"
[[ -f "$fake25a/untracked.txt" ]] || fail "T25a: the untracked file disappeared — something ran clean/reset"
ok_scenario

# (b) detached HEAD
fake25b="$WORK/repo25b"; bare25b="$WORK/remote25b.git"
cli_test_make_git_install_repo "$fake25b" "$bare25b"
cli_test_mark_provisioned "$fake25b" hybrid
git -C "$fake25b" checkout --quiet --detach HEAD
head_before_25b="$(_t25_head "$fake25b")"
out25b="$(_run_install "$fake25b" --only source)"
rc25b=$?
[[ "$rc25b" == "3" ]] || fail "T25b (detached): expected exit 3, got $rc25b — output:\n$out25b"
echo "$out25b" | grep -qi "detached" || fail "T25b: refusal did not name 'detached' — output:\n$out25b"
[[ "$(_t25_head "$fake25b")" == "$head_before_25b" ]] || fail "T25b: HEAD moved despite the refusal"
ok_scenario

# (c) no upstream tracking branch
fake25c="$WORK/repo25c"; bare25c="$WORK/remote25c.git"
cli_test_make_git_install_repo "$fake25c" "$bare25c"
cli_test_mark_provisioned "$fake25c" hybrid
git -C "$fake25c" checkout --quiet -b untracked-branch
head_before_25c="$(_t25_head "$fake25c")"
out25c="$(_run_install "$fake25c" --only source)"
rc25c=$?
[[ "$rc25c" == "3" ]] || fail "T25c (no upstream): expected exit 3, got $rc25c — output:\n$out25c"
echo "$out25c" | grep -qi "upstream" || fail "T25c: refusal did not name 'upstream' — output:\n$out25c"
[[ "$(_t25_head "$fake25c")" == "$head_before_25c" ]] || fail "T25c: HEAD moved despite the refusal"
ok_scenario

# (d) diverged (non-fast-forward): a LOCAL unpushed commit and a DIFFERENT
# REMOTE commit, both children of the same base.
fake25d="$WORK/repo25d"; bare25d="$WORK/remote25d.git"
cli_test_make_git_install_repo "$fake25d" "$bare25d"
cli_test_mark_provisioned "$fake25d" hybrid
echo "local-only change" > "$fake25d/local-file.txt"
git -C "$fake25d" add -A
git -C "$fake25d" -c user.email=t@t -c user.name=t commit --quiet -m "local, unpushed"
cli_test_publish_git_change "$bare25d" main "remote-file.txt" "remote-only change" >/dev/null
head_before_25d="$(_t25_head "$fake25d")"
out25d="$(_run_install "$fake25d" --only source)"
rc25d=$?
[[ "$rc25d" == "3" ]] || fail "T25d (diverged): expected exit 3, got $rc25d — output:\n$out25d"
echo "$out25d" | grep -qi "diverged" || fail "T25d: refusal did not name 'diverged' — output:\n$out25d"
[[ "$(_t25_head "$fake25d")" == "$head_before_25d" ]] || fail "T25d: HEAD moved despite the refusal"
ok_scenario

# (e) LAB_MODE=airgapped without --force
fake25e="$WORK/repo25e"; bare25e="$WORK/remote25e.git"
cli_test_make_git_install_repo "$fake25e" "$bare25e"
cli_test_mark_provisioned "$fake25e" airgapped
head_before_25e="$(_t25_head "$fake25e")"
out25e="$(_run_install "$fake25e" --only source)"
rc25e=$?
[[ "$rc25e" == "3" ]] || fail "T25e (airgapped): expected exit 3, got $rc25e — output:\n$out25e"
echo "$out25e" | grep -qi "airgapped" || fail "T25e: refusal did not name 'airgapped' — output:\n$out25e"
[[ "$(_t25_head "$fake25e")" == "$head_before_25e" ]] || fail "T25e: HEAD moved despite the refusal (a real git fetch/pull was attempted while airgapped)"
ok_scenario

# ---------------------------------------------------------------------------
# T26 / F21 / F22: a fabricated live instance blocks install AND
# install --rebuild-venv (.venv untouched); --allow-running proceeds.
# ---------------------------------------------------------------------------
fake26="$WORK/repo26"; bare26="$WORK/remote26.git"
cli_test_make_git_install_repo "$fake26" "$bare26"
cli_test_mark_provisioned "$fake26" hybrid
mkdir -p "$fake26/stubbin"
port26="$(cli_test_random_port)"
cli_test_assert_port_safe "$port26"
cli_test_write_stub_ps_for_slugs "$fake26/stubbin" "finance:${port26}"
# cli_test_fabricate_live_instance must run in THIS shell, never inside a
# subshell/$( ) — see its own header (tests/cli/lib.sh) for why:
# CLI_TEST_LAST_FABRICATED_PID would not survive otherwise.
cli_test_fabricate_live_instance "$fake26" finance "$port26"
fab26_pid="$CLI_TEST_LAST_FABRICATED_PID"

out26a="$( cd "$fake26" && HOME="$FAKE_HOME" PATH="$fake26/stubbin:$SAFE_PATH" \
    _timeout 15 bash scripts/install.sh --only verify </dev/null 2>&1 )"
rc26a=$?
[[ "$rc26a" == "1" ]] || fail "T26a: expected exit 1 (lab live, no --allow-running), got $rc26a — output:\n$out26a"
echo "$out26a" | grep -qi "stop it first" || fail "T26a: refusal did not name the stop command — output:\n$out26a"

[[ -d "$fake26/.venv" ]] || fail "T26 setup: .venv missing before the rebuild-venv attempt"
out26b="$( cd "$fake26" && HOME="$FAKE_HOME" PATH="$fake26/stubbin:$SAFE_PATH" \
    _timeout 15 bash scripts/install.sh --rebuild-venv --only verify </dev/null 2>&1 )"
rc26b=$?
[[ "$rc26b" == "1" ]] || fail "T26b: expected exit 1 (--rebuild-venv while live), got $rc26b — output:\n$out26b"
[[ -d "$fake26/.venv" ]] || fail "T26b: .venv was deleted despite the refusal (F21 violation)"

out26c="$( cd "$fake26" && HOME="$FAKE_HOME" PATH="$fake26/stubbin:$SAFE_PATH" \
    _timeout 15 bash scripts/install.sh --allow-running --only verify </dev/null 2>&1 )"
echo "$out26c" | grep -qi "stop it first" && fail "T26c: --allow-running still refused on liveness — output:\n$out26c"

kill "$fab26_pid" 2>/dev/null || true
wait "$fab26_pid" 2>/dev/null || true
ok_scenario

# ---------------------------------------------------------------------------
# T27 / F32: --check pending -> 3, nothing mutated; --check up-to-date -> 0;
# `install daemon` -> 2 + install-daemon hint; unprovisioned -> 1 + setup.
# ---------------------------------------------------------------------------
fake27a="$WORK/repo27a"; bare27a="$WORK/remote27a.git"
cli_test_make_git_install_repo "$fake27a" "$bare27a"
cli_test_mark_provisioned "$fake27a" hybrid
_write_pending_manifest "$fake27a"
manifest_before_27a="$(cat "$fake27a/components.json")"
out27a="$(_run_install "$fake27a" --check --only components)"
rc27a=$?
[[ "$rc27a" == "3" ]] || fail "T27a (--check pending): expected exit 3, got $rc27a — output:\n$out27a"
[[ "$(cat "$fake27a/components.json")" == "$manifest_before_27a" ]] || fail "T27a: components.json was mutated under --check"
ok_scenario

fake27b="$WORK/repo27b"; bare27b="$WORK/remote27b.git"
cli_test_make_git_install_repo "$fake27b" "$bare27b"
cli_test_mark_provisioned "$fake27b" hybrid
_write_current_manifest "$fake27b"
out27b="$(_run_install "$fake27b" --check --only components)"
rc27b=$?
[[ "$rc27b" == "0" ]] || fail "T27b (--check up-to-date): expected exit 0, got $rc27b — output:\n$out27b"
ok_scenario

fake27c="$WORK/repo27c"
make_fake_repo "$fake27c" >/dev/null
cli_test_mark_provisioned "$fake27c" hybrid
out27c="$(_run_install "$fake27c" daemon)"
rc27c=$?
[[ "$rc27c" == "2" ]] || fail "T27c (install daemon): expected exit 2, got $rc27c — output:\n$out27c"
echo "$out27c" | grep -qi "install-daemon" || fail "T27c: no install-daemon hint — output:\n$out27c"
ok_scenario

fake27d="$WORK/repo27d"
make_fake_repo "$fake27d" >/dev/null   # deliberately NOT provisioned
out27d="$(_run_install "$fake27d")"
rc27d=$?
[[ "$rc27d" == "1" ]] || fail "T27d (unprovisioned): expected exit 1, got $rc27d — output:\n$out27d"
echo "$out27d" | grep -qi "setup" || fail "T27d: refusal did not name ./arailctl setup — output:\n$out27d"
ok_scenario

# ---------------------------------------------------------------------------
# F7: an --apply component whose update_cmd always fails -> update.sh's own
# exit 3 (never 1), install's components phase degrades (never hard-fails).
# ---------------------------------------------------------------------------
fakeF7="$WORK/repoF7"; bareF7="$WORK/remoteF7.git"
cli_test_make_git_install_repo "$fakeF7" "$bareF7"
cli_test_mark_provisioned "$fakeF7" hybrid
_write_failing_apply_manifest "$fakeF7"
outF7="$(_run_install "$fakeF7" --only components)"
rcF7=$?
[[ "$rcF7" == "3" ]] || fail "F7: expected exit 3 (degraded, never 1, for one failing optional component), got $rcF7 — output:\n$outF7"
echo "$outF7" | grep -qi "widget" || fail "F7: the failing component was not named — output:\n$outF7"
ok_scenario

# ---------------------------------------------------------------------------
# T28: aliases. update (no --component) -> install, notice on stderr, JSON
# stdout stays parseable; update --component X -> the OLD interactive path
# (never reaches install.sh); tier/upgrade (no arg) -> print current tier,
# exit 0; upgrade <tier> -> forwards to scripts/upgrade.sh (stubbed here —
# upgrade.sh's OWN tier-switch behavior is untouched/out of scope for this
# WP; only the DISPATCH is under test).
# ---------------------------------------------------------------------------
fake28a="$WORK/repo28a"; bare28a="$WORK/remote28a.git"
cli_test_make_git_install_repo "$fake28a" "$bare28a"
cli_test_mark_provisioned "$fake28a" hybrid
_write_current_manifest "$fake28a"
out28a_all="$( cd "$fake28a" && HOME="$FAKE_HOME" PATH="$SAFE_PATH" \
    _timeout 15 bash arailctl update --check --only components --json </dev/null )"
rc28a=$?
out28a_stdout="$out28a_all"
out28a_stderr="$( cd "$fake28a" && HOME="$FAKE_HOME" PATH="$SAFE_PATH" \
    _timeout 15 bash arailctl update --check --only components --json </dev/null 2>&1 1>/dev/null )"
[[ "$rc28a" == "0" ]] || fail "T28a: expected exit 0, got $rc28a — stdout:\n$out28a_stdout"
echo "$out28a_stderr" | grep -qi "alias for 'install'" || fail "T28a: no alias notice on stderr — stderr:\n$out28a_stderr"
printf '%s' "$out28a_stdout" | "$REAL_VENV/bin/python" -c 'import json,sys; json.load(sys.stdin)' \
    || fail "T28a: stdout under --json is not valid JSON — stdout:\n$out28a_stdout"
ok_scenario

fake28b="$WORK/repo28b"
make_fake_repo "$fake28b" >/dev/null
# NOT LAB_MODE: this scenario deliberately drives the OLD interactive
# update.sh path (via --component), which this WP leaves untouched —
# including its pre-existing ARAIL_MODE-only (no LAB_MODE) mode read.
printf 'ARAIL_MODE=hybrid\n' > "$fake28b/.env"
_write_current_manifest "$fake28b"
out28b="$(_run_ctl "$fake28b" update --component ttyd)"
rc28b=$?
[[ "$rc28b" == "0" ]] || fail "T28b: expected exit 0, got $rc28b — output:\n$out28b"
echo "$out28b" | grep -q "Update Check" || fail "T28b: --component did not reach the OLD interactive path — output:\n$out28b"
echo "$out28b" | grep -q "install:" && fail "T28b: --component wrongly reached install.sh — output:\n$out28b"
ok_scenario

fake28c="$WORK/repo28c"
make_fake_repo "$fake28c" >/dev/null
out28c_tier="$(_run_ctl "$fake28c" tier)"; rc28c_tier=$?
out28c_upgrade="$(_run_ctl "$fake28c" upgrade)"; rc28c_upgrade=$?
[[ "$rc28c_tier" == "0" ]] || fail "T28c: 'tier' (no arg) expected exit 0, got $rc28c_tier — output:\n$out28c_tier"
echo "$out28c_tier" | grep -qi "Current tier" || fail "T28c: 'tier' did not print the current tier — output:\n$out28c_tier"
[[ "$rc28c_upgrade" == "0" ]] || fail "T28c: 'upgrade' (no arg) expected exit 0, got $rc28c_upgrade — output:\n$out28c_upgrade"
echo "$out28c_upgrade" | grep -qi "Current tier" || fail "T28c: 'upgrade' (no arg) did not print the current tier — output:\n$out28c_upgrade"
echo "$out28c_upgrade" | grep -qi "alias for 'tier'" || fail "T28c: 'upgrade' did not print its alias notice — output:\n$out28c_upgrade"
ok_scenario

fake28d="$WORK/repo28d"
make_fake_repo "$fake28d" >/dev/null
cat > "$fake28d/scripts/upgrade.sh" <<'EOF'
#!/usr/bin/env bash
echo "UPGRADE_STUB_CALLED: $*"
EOF
chmod +x "$fake28d/scripts/upgrade.sh"
out28d_tier="$(_run_ctl "$fake28d" tier maximus)"
out28d_upgrade="$(_run_ctl "$fake28d" upgrade maximus)"
echo "$out28d_tier" | grep -q "UPGRADE_STUB_CALLED: maximus" || fail "T28d: 'tier maximus' did not forward to scripts/upgrade.sh — output:\n$out28d_tier"
echo "$out28d_upgrade" | grep -q "UPGRADE_STUB_CALLED: maximus" || fail "T28d: 'upgrade maximus' did not forward to scripts/upgrade.sh — output:\n$out28d_upgrade"
ok_scenario

echo "OK: ${pass_count} scenario(s) passed — install verb + update/upgrade consolidation (T24-T28, F5-F7, F21, F22, F28, F32)"
