#!/usr/bin/env bash
# tests/cli/qa_edge_driver.sh — QA pass for the 2026-07-29-elite-cli sprint
# (sprints/2026-07-29-elite-cli/TEST_REPORT.md). These are the cases the
# sprint's own drivers do NOT cover, in the repo CLAUDE.md's arail
# allocation for this sprint (45% setup-and-lifecycle / 20% security /
# 20% regression / 15% happy path).
#
# Every scenario here PASSES against the shipped code. The product defects
# this QA pass found are pinned separately, as strict-xfail tests, in
# tests/test_cli_qa_edge.py (Q1-Q6) — a driver that asserts buggy
# behaviour would go green the day the bug is fixed, which is backwards.
#
# Idioms are inherited wholesale from the sprint's own harness
# (tests/cli/lib.sh): real scripts/ copied into a throwaway repo, isolated
# HOME, portable `_timeout`, and F26/F27 randomized ports >= 18000 that are
# NEVER 8080/8090 (a wrong port here could reach a developer's real lab
# through reset.sh's port-only fallback — load-bearing safety, not just
# isolation).
#
# Scenarios:
#   QA-1  fresh clone (no .env / .venv / lab.conf): every verb fails
#         helpfully, never crashes, exits per docs/cli.md          [setup]
#   QA-2  fresh clone: `status --json` is still a valid document    [setup]
#   QA-3  setup.sh's --yes/-y/--quiet flag surface, WITHOUT running
#         any provisioning                                         [setup]
#   QA-4  `status --json` survives every hostile registry state     [edge]
#   QA-5  a World display_name full of control characters cannot
#         break the JSON document                              [security]
#   QA-6  install's git phase: --force does NOT unlock the dirty-tree
#         or detached-HEAD refusals                             [security]
#   QA-7  REAL end-to-end root boot (the real uvicorn + the real
#         arail.portal.app, not the stub): readiness gate, status in
#         all three output modes, install --check refusal against a
#         genuinely live lab, scoped stop, port released     [happy path]
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

# ── A fresh CLONE, not a fresh fake repo: make_fake_repo writes a .env,
# which is exactly the file a just-cloned checkout does not have. Copy the
# tracked-file shape a `git clone` leaves behind (scripts/, arailctl,
# components.json, docs/cli.md) and nothing else — no .env, no lab.conf,
# no .venv, no lab/.
_qa_fresh_clone() {
    local dest="$1"
    mkdir -p "$dest/docs"
    cp -R "$CLI_TEST_REPO/scripts" "$dest/scripts"
    cp "$CLI_TEST_REPO/arailctl" "$dest/arailctl"
    cp "$CLI_TEST_REPO/components.json" "$dest/components.json"
    cp "$CLI_TEST_REPO/docs/cli.md" "$dest/docs/cli.md"
}

# _qa_run <repo> <args...> — non-tty (stdin </dev/null, stdout captured),
# hard-timeout'd, isolated HOME and PATH. Sets OUT and RC.
_qa_run() {
    local repo="$1"; shift
    OUT="$( cd "$repo" && HOME="$FAKE_HOME" PATH="$SAFE_PATH" _timeout 60 bash arailctl "$@" </dev/null 2>&1 )"
    RC=$?
}

# ---------------------------------------------------------------------------
# QA-1 — fresh clone: every verb fails HELPFULLY and never crashes. arail's
# #1 ship gate is setup-on-a-clean-machine; the CLI is the first thing a
# new user touches, and on a fresh clone every one of these runs before
# `setup` has ever been executed. Asserts the exit code from docs/cli.md's
# contract AND that the message names the recovery command.
# ---------------------------------------------------------------------------
fresh="$WORK/fresh-clone"
_qa_fresh_clone "$fresh"

_qa_run "$fresh" help
[[ "$RC" == "0" ]] || fail "QA-1 help: expected exit 0 on a fresh clone, got $RC — output:\n$OUT"
echo "$OUT" | grep -q "setup" || fail "QA-1 help: usage does not mention setup — output:\n$OUT"

_qa_run "$fresh" status
[[ "$RC" == "4" ]] || fail "QA-1 status: expected exit 4 (nothing running), got $RC — output:\n$OUT"
echo "$OUT" | grep -q "./arailctl setup" || fail "QA-1 status: no './arailctl setup' guidance on an unprovisioned clone — output:\n$OUT"
echo "$OUT" | grep -qi "traceback" && fail "QA-1 status: a Python traceback reached the user — output:\n$OUT"

_qa_run "$fresh" doctor
[[ "$RC" == "1" ]] || fail "QA-1 doctor: expected exit 1 (broken — no .venv), got $RC — output:\n$OUT"
echo "$OUT" | grep -q "./arailctl setup" || fail "QA-1 doctor: no setup guidance — output:\n$OUT"

_qa_run "$fresh" start
[[ "$RC" == "1" ]] || fail "QA-1 start: expected exit 1, got $RC — output:\n$OUT"
echo "$OUT" | grep -q "./arailctl setup" || fail "QA-1 start: no setup guidance — output:\n$OUT"

_qa_run "$fresh" start --root --no-browser
[[ "$RC" == "1" ]] || fail "QA-1 start --root: expected exit 1, got $RC — output:\n$OUT"
echo "$OUT" | grep -q "./arailctl setup" || fail "QA-1 start --root: no setup guidance — output:\n$OUT"

_qa_run "$fresh" install
[[ "$RC" == "1" ]] || fail "QA-1 install: expected exit 1 (not provisioned), got $RC — output:\n$OUT"
echo "$OUT" | grep -q "./arailctl setup" || fail "QA-1 install: refusal did not name ./arailctl setup — output:\n$OUT"

_qa_run "$fresh" install --check
[[ "$RC" == "1" ]] || fail "QA-1 install --check: expected exit 1 (not provisioned), got $RC — output:\n$OUT"

_qa_run "$fresh" stop
[[ "$RC" == "0" ]] || fail "QA-1 stop: a stop verb's contract is the post-condition — expected exit 0, got $RC — output:\n$OUT"

_qa_run "$fresh" stop --root
[[ "$RC" == "0" ]] || fail "QA-1 stop --root: expected exit 0, got $RC — output:\n$OUT"

# F4/A2: `source <missing-file>` aborts a non-interactive bash 3.2 shell
# even under `|| true`. A fresh clone has no .env and no lab.conf — the
# exact landmine. Nothing above may die with a bash-internal error.
for _qa_v in status start install stop doctor; do
    _qa_run "$fresh" "$_qa_v"
    echo "$OUT" | grep -qE "unbound variable|No such file or directory: .*(\.env|lab\.conf)|syntax error" \
        && fail "QA-1 F4: '$_qa_v' on a fresh clone hit a shell-internal error — output:\n$OUT"
done
unset _qa_v
ok_scenario

# ---------------------------------------------------------------------------
# QA-2 — fresh clone: `status --json` is STILL one valid document (F18),
# reports provisioned:false, and carries no ANSI escape on stdout.
# ---------------------------------------------------------------------------
OUT="$( cd "$fresh" && HOME="$FAKE_HOME" PATH="$SAFE_PATH" _timeout 30 bash arailctl status --json </dev/null 2>/dev/null )"
RC=$?
[[ "$RC" == "4" ]] || fail "QA-2: status --json on a fresh clone expected exit 4, got $RC — output:\n$OUT"
printf '%s' "$OUT" | python3 -m json.tool >/dev/null 2>&1 \
    || fail "QA-2/F18: status --json on a fresh clone is not valid JSON — output:\n$OUT"
printf '%s' "$OUT" | python3 -c '
import json, sys
d = json.load(sys.stdin)
assert d["schema"] == "arail.status/v2", d["schema"]
assert d["provisioned"] is False, d["provisioned"]
assert d["instances"] == [], d["instances"]
assert d["verdict"]["code"] == 4, d["verdict"]
' || fail "QA-2: status --json document is wrong on a fresh clone — output:\n$OUT"
printf '%s' "$OUT" | grep -q $'\033' && fail "QA-2: ANSI escape leaked into piped --json output"
OUT="$( cd "$fresh" && HOME="$FAKE_HOME" PATH="$SAFE_PATH" _timeout 30 bash arailctl status --json=instances </dev/null 2>/dev/null )"
RC=$?
[[ "$RC" == "4" ]] || fail "QA-2: --json=instances expected exit 4, got $RC"
printf '%s' "$OUT" | python3 -c 'import json,sys; assert json.load(sys.stdin) == []' \
    || fail "QA-2: --json=instances is not an empty array on a fresh clone — output:\n$OUT"
ok_scenario

# ---------------------------------------------------------------------------
# QA-3 — setup's new flag surface (WP1) WITHOUT running any provisioning.
# setup.sh installs OS packages and rewrites .env; it must never actually
# run in a test. Its argv loop is the first thing main() does and exits 2
# on the first unknown flag, so pairing a known flag with a bogus one
# proves the known one parsed (the error names the bogus one, not it) and
# proves nothing was provisioned (no .env written).
# ---------------------------------------------------------------------------
setup_repo="$WORK/setup-flags"
mkdir -p "$setup_repo"
cp "$CLI_TEST_REPO/scripts/setup.sh" "$setup_repo/setup.sh"
for _qa_known in "--yes" "-y" "--quiet" "--with-coder" "--no-coder"; do
    OUT="$( cd "$setup_repo" && HOME="$FAKE_HOME" _timeout 30 bash setup.sh "$_qa_known" --zzz-bogus </dev/null 2>&1 )"
    RC=$?
    [[ "$RC" == "2" ]] || fail "QA-3: setup.sh $_qa_known --zzz-bogus expected exit 2, got $RC — output:\n$OUT"
    echo "$OUT" | grep -q -- "--zzz-bogus" || fail "QA-3: setup.sh did not name the unknown flag — output:\n$OUT"
    echo "$OUT" | grep -q -- "unknown flag: ${_qa_known}$" \
        && fail "QA-3: setup.sh rejected the KNOWN flag $_qa_known — output:\n$OUT"
    [[ ! -e "$setup_repo/.env" ]] || fail "QA-3: setup.sh wrote .env before finishing flag parsing"
done
unset _qa_known
ok_scenario

# ---------------------------------------------------------------------------
# QA-4 — `status --json` survives every hostile registry state (F18: the
# document is ALWAYS emitted, whatever the collector hits). status_driver
# covers the corrupt-record and unreadable-dir cases; these are the ones it
# does not: a record that is valid JSON but not an object, a record with a
# huge field, and one whose fields are the wrong TYPE (string where an int
# is expected) — each a plausible shape for a half-written or
# hand-edited registry file.
# ---------------------------------------------------------------------------
_qa_json_state() {
    # _qa_json_state <name> <record-body> — writes the body as a registry
    # record and asserts status --json stays parseable on stdout alone.
    local name="$1" body="$2" repo="$WORK/json-$1"
    make_fake_repo "$repo" >/dev/null
    make_fake_venv "$repo"
    mkdir -p "$repo/lab/instances/registry.d"
    printf '%s' "$body" > "$repo/lab/instances/registry.d/rec.json"
    local out rc
    out="$( cd "$repo" && HOME="$FAKE_HOME" PATH="$SAFE_PATH" _timeout 30 bash arailctl status --json </dev/null 2>/dev/null )"
    rc=$?
    printf '%s' "$out" | python3 -m json.tool >/dev/null 2>&1 \
        || fail "QA-4 ($name): status --json emitted a non-JSON stdout — rc=$rc output:\n$out"
    case "$rc" in
        0|1|3|4) : ;;
        *) fail "QA-4 ($name): status --json exited $rc, outside the documented 0/1/3/4 set" ;;
    esac
    # And the human renderer must not crash on the same input.
    out="$( cd "$repo" && HOME="$FAKE_HOME" PATH="$SAFE_PATH" _timeout 30 bash arailctl status </dev/null 2>&1 )"
    echo "$out" | grep -qi "Traceback (most recent call last)" \
        && fail "QA-4 ($name): human status leaked a Python traceback — output:\n$out"
    return 0
}
_qa_json_state notobject '[1, 2, 3]'
_qa_json_state jsonnull 'null'
_qa_json_state scalar '"just a string"'
_qa_json_state emptyobj '{}'
_qa_json_state wrongtypes '{"schema":"arail.instance-registry/v1","slug":"x","portal_port":"not-an-int","portal_pid":"nope","display_name":"x","checkout":"/tmp"}'
_qa_json_state truncated '{"schema":"arail.instance-registry/v1","slug":"x",'
ok_scenario

# unreadable registry directory: T8 pins "valid JSON + 1"; re-assert it
# here because this driver's whole point is that the JSON contract holds
# in states nobody planned for.
qa_unreadable="$WORK/json-unreadable"
make_fake_repo "$qa_unreadable" >/dev/null
make_fake_venv "$qa_unreadable"
mkdir -p "$qa_unreadable/lab/instances/registry.d"
printf '{"slug":"x"}' > "$qa_unreadable/lab/instances/registry.d/x.json"
chmod 000 "$qa_unreadable/lab/instances/registry.d"
OUT="$( cd "$qa_unreadable" && HOME="$FAKE_HOME" PATH="$SAFE_PATH" _timeout 30 bash arailctl status --json </dev/null 2>/dev/null )"
RC=$?
chmod 755 "$qa_unreadable/lab/instances/registry.d"
printf '%s' "$OUT" | python3 -m json.tool >/dev/null 2>&1 \
    || fail "QA-4 (unreadable dir): status --json is not valid JSON — output:\n$OUT"
[[ "$RC" == "1" ]] || fail "QA-4 (unreadable dir): expected exit 1, got $RC — output:\n$OUT"
ok_scenario

# ---------------------------------------------------------------------------
# QA-5 (security) — a World bundle's display_name is NOT trusted input:
# Worlds are made to be shared (world-forge / world-mount), so the
# manifest's display_name arrives from whoever built the bundle and lands
# verbatim in the registry record. It must not be able to break the
# machine-readable document. (The HUMAN renderer does pass control bytes
# through — filed as Q5 in TEST_REPORT.md and pinned as a strict-xfail in
# tests/test_cli_qa_edge.py, so this scenario deliberately asserts only
# the JSON half, which is correct today.)
# ---------------------------------------------------------------------------
qa_evil="$WORK/evil-name"
make_fake_repo "$qa_evil" >/dev/null
make_fake_venv "$qa_evil"
QA_EVIL_PORT="$(cli_test_random_port)"
cli_test_assert_port_safe "$QA_EVIL_PORT"
write_lab_conf "$qa_evil" "$QA_EVIL_PORT" "$((QA_EVIL_PORT + 1))" "$((QA_EVIL_PORT + 2))" "$((QA_EVIL_PORT + 3))" "$((QA_EVIL_PORT + 4))"
mkdir -p "$qa_evil/lab/instances/registry.d"
"$REAL_VENV/bin/python" - "$qa_evil" "$((QA_EVIL_PORT + 1))" <<'PY'
import json, sys
fake, port = sys.argv[1], int(sys.argv[2])
# Every shape that can rewrite a terminal or forge a row: CSI clear-screen,
# a colour set, a carriage return, a newline, a NUL-adjacent control byte,
# a JSON metacharacter, and a non-BMP codepoint.
evil = ('\x1b[2J\x1b[1;31mPWNED\r  ● root       Real Lab   :8080  pid 1\n'
        '"},{"slug":"forged","state":"live"}\x07\U0001f4a3')
rec = {
    "schema": "arail.instance-registry/v1", "slug": "evil", "display_name": evil,
    "checkout": fake, "instance_root": fake + "/lab/instances/evil",
    "data_dir": fake + "/lab/instances/evil/data",
    "pkb_root": fake + "/lab/instances/evil/pkb",
    "bind": "127.0.0.1", "portal_port": port, "lance_port": port + 4,
    "launcher_pid": 1, "portal_pid": 1, "memory_pid": 1, "token": "t",
    "started_at": "2026-01-01T00:00:00Z", "arailctl_version": "test",
}
with open(fake + "/lab/instances/registry.d/evil.json", "w", encoding="utf-8") as fh:
    json.dump(rec, fh)
PY
OUT="$( cd "$qa_evil" && HOME="$FAKE_HOME" PATH="$SAFE_PATH" _timeout 30 bash arailctl status --json </dev/null 2>/dev/null )"
printf '%s' "$OUT" | python3 -m json.tool >/dev/null 2>&1 \
    || fail "QA-5: a hostile display_name broke status --json — output:\n$OUT"
printf '%s' "$OUT" | grep -q $'\033' \
    && fail "QA-5: a raw ESC byte from display_name reached --json stdout (JSON must escape it as \\u001b)"
printf '%s' "$OUT" | python3 -c '
import json, sys
d = json.load(sys.stdin)
rows = d["instances"]
# The forged '"'"'},{"slug":"forged"'"'"' fragment must NOT have become a row.
assert [r.get("slug") for r in rows] == ["evil"], [r.get("slug") for r in rows]
' || fail "QA-5: display_name forged an extra instance row in --json — output:\n$OUT"
# ...and the same input on the instances-only form.
OUT="$( cd "$qa_evil" && HOME="$FAKE_HOME" PATH="$SAFE_PATH" _timeout 30 bash arailctl status --json=instances </dev/null 2>/dev/null )"
printf '%s' "$OUT" | python3 -m json.tool >/dev/null 2>&1 \
    || fail "QA-5: a hostile display_name broke status --json=instances — output:\n$OUT"
ok_scenario

# ---------------------------------------------------------------------------
# QA-6 (security) — install's source phase: `--force` exists ONLY to
# override the airgap refusal (§6.3). It must NOT unlock the refusals that
# protect an operator's local work. install_driver's T25 proves the
# refusals without --force; this proves --force cannot buy past them, on
# a repo that IS genuinely behind its remote (so a pull WOULD move HEAD if
# anything let it).
# ---------------------------------------------------------------------------
qa_git="$WORK/git-force"
qa_bare="$WORK/git-force-bare.git"
cli_test_make_git_install_repo "$qa_git" "$qa_bare" main
cli_test_mark_provisioned "$qa_git" hybrid
cli_test_publish_git_change "$qa_bare" main "UPSTREAM.md" "an upstream commit" >/dev/null
printf 'QA LOCAL EDIT\n' >> "$qa_git/arailctl"
qa_head_before="$(git -C "$qa_git" rev-parse HEAD)"
for _qa_flags in "--force" "--force --yes" "--force --models"; do
    # shellcheck disable=SC2086
    OUT="$( cd "$qa_git" && HOME="$FAKE_HOME" PATH="$SAFE_PATH" _timeout 60 bash arailctl install --only source $_qa_flags </dev/null 2>&1 )"
    RC=$?
    [[ "$RC" == "3" ]] || fail "QA-6 (dirty + $_qa_flags): expected exit 3 (degraded, phase refused), got $RC — output:\n$OUT"
    echo "$OUT" | grep -qi "dirty" || fail "QA-6 (dirty + $_qa_flags): refusal did not name the dirty worktree — output:\n$OUT"
    [[ "$(git -C "$qa_git" rev-parse HEAD)" == "$qa_head_before" ]] \
        || fail "QA-6 (dirty + $_qa_flags): HEAD MOVED despite the refusal"
    grep -q "QA LOCAL EDIT" "$qa_git/arailctl" \
        || fail "QA-6 (dirty + $_qa_flags): the local edit was destroyed — install must never stash/reset/clean"
done
unset _qa_flags
# Detached HEAD, also with --force.
git -C "$qa_git" checkout --quiet -- arailctl
git -C "$qa_git" checkout --quiet --detach HEAD
qa_head_before="$(git -C "$qa_git" rev-parse HEAD)"
OUT="$( cd "$qa_git" && HOME="$FAKE_HOME" PATH="$SAFE_PATH" _timeout 60 bash arailctl install --only source --force </dev/null 2>&1 )"
RC=$?
[[ "$RC" == "3" ]] || fail "QA-6 (detached + --force): expected exit 3, got $RC — output:\n$OUT"
echo "$OUT" | grep -qi "detached" || fail "QA-6 (detached + --force): refusal did not name the detached HEAD — output:\n$OUT"
[[ "$(git -C "$qa_git" rev-parse HEAD)" == "$qa_head_before" ]] \
    || fail "QA-6 (detached + --force): HEAD MOVED despite the refusal"
ok_scenario

# ---------------------------------------------------------------------------
# QA-7 (happy path) — a REAL end-to-end root boot. Every other scenario in
# tests/cli/ drives a stub uvicorn; this one drives the REAL uvicorn and
# the REAL arail.portal.app (readiness probe, /api/instance identity gate,
# memory service and all), just sandboxed: a throwaway repo, an isolated
# HOME, and F26/F27 randomized ports >= 18000. That combination is what
# makes it safe to run on a developer's own machine.
#
# start and status run under the SAME restricted PATH on purpose: the
# "expected" set for terminal/notebook/ide is computed from whichever
# PATH the asking process has (§7.1), so a start that could not see ttyd
# and a status that could would legitimately disagree.
# ---------------------------------------------------------------------------
qa_boot="$WORK/real-boot"
make_fake_repo "$qa_boot" >/dev/null
make_fake_venv "$qa_boot"
link_real_uvicorn "$qa_boot" || fail "QA-7: could not link the real uvicorn into the fake venv"
QA_BOOT_PORT="$(cli_test_random_port)"
cli_test_assert_port_safe "$QA_BOOT_PORT"
write_lab_conf "$qa_boot" "$QA_BOOT_PORT" "$((QA_BOOT_PORT + 1))" "$((QA_BOOT_PORT + 2))" "$((QA_BOOT_PORT + 3))" "$((QA_BOOT_PORT + 4))"
printf 'LAB_NAME="QA Real Boot"\nLAB_SHORT_NAME=qa-real\nLAB_MODE=airgapped\n' > "$qa_boot/.env"

cat > "$WORK/qa7_start.sh" <<EOF
#!/usr/bin/env bash
cd "$qa_boot"
export HOME="$FAKE_HOME" PATH="$SAFE_PATH" ARAIL_NO_BROWSER=1
exec bash arailctl start --root --no-browser
EOF
chmod +x "$WORK/qa7_start.sh"

_qa7_wait() {
    local log="$1" marker="$2" i
    for i in $(seq 1 900); do
        grep -qE "$marker" "$log" 2>/dev/null && return 0
        sleep 0.1
    done
    return 1
}
_qa7_ctl() { ( cd "$qa_boot" && HOME="$FAKE_HOME" PATH="$SAFE_PATH" _timeout 60 bash arailctl "$@" </dev/null 2>&1 ); }

"$WORK/qa7_start.sh" > "$WORK/qa7_start.log" 2>&1 &
qa7_pid=$!
if ! _qa7_wait "$WORK/qa7_start.log" '✓ Portal'; then
    kill "$qa7_pid" 2>/dev/null; wait "$qa7_pid" 2>/dev/null
    cli_test_kill_port_listener "$QA_BOOT_PORT"
    fail "QA-7: the real root lab never passed its readiness gate — log:\n$(cat "$WORK/qa7_start.log")"
fi
qa7_log="$(cat "$WORK/qa7_start.log")"
echo "$qa7_log" | grep -q "Readiness:" || fail "QA-7: no Readiness section in a real boot — log:\n$qa7_log"
echo "$qa7_log" | grep -q "All services running." \
    || fail "QA-7: honest banner missing on a fully-up real boot — log:\n$qa7_log"
echo "$qa7_log" | grep -q "http://127.0.0.1:${QA_BOOT_PORT}" \
    || fail "QA-7: the URL block never named the actual portal port — log:\n$qa7_log"

# The readiness gate's own claim, verified independently of the CLI.
qa7_body="$(curl -s -m 3 "http://127.0.0.1:${QA_BOOT_PORT}/api/instance" 2>/dev/null || true)"
printf '%s' "$qa7_body" | python3 -c '
import json, sys
b = json.load(sys.stdin)
assert b["slug"] == "root", b["slug"]
assert b["token"] is None, "the root lab must not mint an instance token"
' || fail "QA-7: /api/instance did not self-report as the root lab — body:\n$qa7_body"

OUT="$(_qa7_ctl status)"; RC=$?
[[ "$RC" == "0" ]] || fail "QA-7: status against a fully-up real lab expected exit 0, got $RC — output:\n$OUT"
echo "$OUT" | grep -q "http://127.0.0.1:${QA_BOOT_PORT}" \
    || fail "QA-7: status did not print the portal URL that actually answers — output:\n$OUT"

OUT="$( cd "$qa_boot" && HOME="$FAKE_HOME" PATH="$SAFE_PATH" _timeout 30 bash arailctl status --json </dev/null 2>/dev/null )"
RC=$?
[[ "$RC" == "0" ]] || fail "QA-7: status --json expected exit 0, got $RC — output:\n$OUT"
printf '%s' "$OUT" | python3 -c '
import json, sys
d = json.load(sys.stdin)
assert d["root"]["state"] == "up", d["root"]["state"]
svc = {s["name"]: s for s in d["root"]["services"]}
assert svc["portal"]["listening"] is True, svc["portal"]
assert svc["portal"]["url"], "a listening service must carry its URL"
for name, s in svc.items():
    if not s["listening"]:
        assert s["url"] is None, (name, s["url"])
' || fail "QA-7: the --json document disagrees with the live lab — output:\n$OUT"

OUT="$( cd "$qa_boot" && HOME="$FAKE_HOME" PATH="$SAFE_PATH" _timeout 30 bash arailctl status --json=instances </dev/null 2>/dev/null )"
RC=$?
[[ "$RC" == "0" ]] || fail "QA-7: --json=instances expected exit 0 (the exit code applies to every status form), got $RC"
printf '%s' "$OUT" | python3 -c 'import json,sys; assert json.load(sys.stdin) == []' \
    || fail "QA-7: --json=instances should be [] with only the root lab up — output:\n$OUT"

# F21/F22 against a GENUINELY live root lab — install_driver's T26 only
# ever fabricates a live World-instance record, so this half of the
# preflight (the root portal answering) has had no coverage at all.
OUT="$(_qa7_ctl install --check)"; RC=$?
[[ "$RC" == "1" ]] || fail "QA-7/F21: install --check against a live root lab expected exit 1, got $RC — output:\n$OUT"
echo "$OUT" | grep -qi "stop it first" || fail "QA-7/F21: refusal did not name the stop command — output:\n$OUT"
[[ -d "$qa_boot/.venv" ]] || fail "QA-7/F21: .venv disappeared during a refused install"

OUT="$(_qa7_ctl stop --root)"; RC=$?
[[ "$RC" == "0" ]] || fail "QA-7: stop --root expected exit 0, got $RC — output:\n$OUT"
sleep 0.5
OUT="$(_qa7_ctl status)"; RC=$?
[[ "$RC" == "4" ]] || fail "QA-7: status after stop --root expected exit 4, got $RC — output:\n$OUT"
if lsof -tiTCP:"$QA_BOOT_PORT" -sTCP:LISTEN >/dev/null 2>&1; then
    cli_test_kill_port_listener "$QA_BOOT_PORT"
    fail "QA-7: the portal port is still listening after stop --root"
fi
kill "$qa7_pid" 2>/dev/null || true
wait "$qa7_pid" 2>/dev/null || true
cli_test_kill_port_listener "$QA_BOOT_PORT"
cli_test_kill_port_listener "$((QA_BOOT_PORT + 1))"
ok_scenario

# ---------------------------------------------------------------------------
# QA-8 (regression) — ANSI gating for the three scripts color_driver.sh
# does not reach. §13 applied the gating conditional to EIGHT scripts;
# color_driver.sh covers five (arailctl, start.sh, status.sh, reset.sh,
# setup.sh). install.sh (new this sprint), update.sh and upgrade.sh have
# the same block and no gate on it. Every invocation below is
# side-effect-free: a usage banner, an unknown-flag rejection, and an
# airgapped refusal that never reaches the network.
# ---------------------------------------------------------------------------
qa_color="$WORK/color"
make_fake_repo "$qa_color" >/dev/null
printf 'LAB_MODE=airgapped\nLAB_TIER=minimalist\n' > "$qa_color/.env"

_qa_has_esc() {
    printf '%s' "$1" | grep -q "$(printf '\033')" 2>/dev/null
}
_qa_color_gate() {
    # _qa_color_gate <label> <requires_color:0|1> <script-relpath> [args...]
    local label="$1" requires_color="$2"; shift 2
    local out
    out="$( cd "$qa_color" && HOME="$FAKE_HOME" PATH="$SAFE_PATH" _timeout 60 bash "$@" </dev/null 2>&1 )"
    _qa_has_esc "$out" && fail "QA-8 $label: default piped invocation leaked ANSI codes"
    out="$( cd "$qa_color" && HOME="$FAKE_HOME" PATH="$SAFE_PATH" NO_COLOR=1 _timeout 60 bash "$@" </dev/null 2>&1 )"
    _qa_has_esc "$out" && fail "QA-8 $label: NO_COLOR=1 leaked ANSI codes"
    out="$( cd "$qa_color" && HOME="$FAKE_HOME" PATH="$SAFE_PATH" ARAIL_COLOR=never _timeout 60 bash "$@" </dev/null 2>&1 )"
    _qa_has_esc "$out" && fail "QA-8 $label: ARAIL_COLOR=never leaked ANSI codes"
    if [[ "$requires_color" == "1" ]]; then
        out="$( cd "$qa_color" && HOME="$FAKE_HOME" PATH="$SAFE_PATH" ARAIL_COLOR=always _timeout 60 bash "$@" </dev/null 2>&1 )"
        _qa_has_esc "$out" || fail "QA-8 $label: ARAIL_COLOR=always produced no ANSI codes at all — is the gating block wired backwards?"
    fi
    return 0
}
_qa_color_gate "install.sh --help"     0 scripts/install.sh --help
_qa_color_gate "install.sh unknown"    0 scripts/install.sh --zzz-bogus
_qa_color_gate "upgrade.sh usage"      1 scripts/upgrade.sh
_qa_color_gate "update.sh airgapped"   1 scripts/update.sh --check --non-interactive
ok_scenario

# ---------------------------------------------------------------------------
# QA-9 (setup) — the TTY-ish half. Every other scenario in tests/cli/ runs
# non-tty (that is the CI/daemon contract, F8), which means the OTHER
# direction of the §13/F25 gating — "colors DO appear on a real terminal"
# — has never been exercised, and neither has "no verb blocks on a prompt
# when a tty IS present but the lab is unprovisioned". Both matter for
# arail's first-impression gate: a new user's first command runs on a
# terminal, not a pipe.
#
# Guarded on BSD `script` (macOS): the util-linux spelling takes different
# arguments, so a box without the BSD form skips rather than false-fails.
# Exit codes are deliberately NOT asserted through the pty — BSD `script`
# does not propagate the child's status reliably; the non-tty scenarios
# above own the exit-code contract.
# ---------------------------------------------------------------------------
if script -q /dev/null true >/dev/null 2>&1; then
    _qa_pty() {
        ( cd "$fresh" && HOME="$FAKE_HOME" PATH="$SAFE_PATH" \
            _timeout 60 script -q /dev/null bash arailctl "$@" </dev/null 2>&1 )
    }
    qa_pty_out="$(_qa_pty status)"
    [[ $? == 124 ]] && fail "QA-9: 'status' HUNG on a tty (a prompt with nothing to answer it)"
    _qa_has_esc "$qa_pty_out" \
        || fail "QA-9: status produced no ANSI on a real tty — the gating conditional may be inverted"
    echo "$qa_pty_out" | grep -q "./arailctl setup" \
        || fail "QA-9: status on a tty lost the setup guidance — output:\n$qa_pty_out"

    for _qa_pty_verb in install start restart doctor; do
        qa_pty_out="$(_qa_pty "$_qa_pty_verb")"
        [[ $? == 124 ]] && fail "QA-9: '$_qa_pty_verb' HUNG on a tty — no verb may block on a prompt an unprovisioned lab cannot answer"
        echo "$qa_pty_out" | grep -qiE "setup|not provisioned" \
            || fail "QA-9: '$_qa_pty_verb' on a tty gave no recovery guidance — output:\n$qa_pty_out"
    done
    unset _qa_pty_verb
    ok_scenario
else
    echo "note: QA-9 skipped — no BSD-style script(1) for a pty harness"
fi

echo "OK: ${pass_count} scenario(s) passed — QA edge/setup/security/happy pass (QA-1..QA-9)"
