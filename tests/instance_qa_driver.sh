#!/usr/bin/env bash
# QA driver for scripts/start.sh — the scenarios the WP4 driver did not cover.
# Sprint: sprints/2026-07-28-concurrent-worlds/ (QA pass, post-WEAK_PASS).
#
# Same contract and harness shape as tests/instance_start_driver.sh: drives the
# REAL scripts/start.sh inside a throwaway fake repo with a symlinked .venv and
# stub uvicorn/ollama/open binaries on PATH. Exits 0 printing
# "OK: <n> scenario(s)"; non-zero with "FAIL: <reason>".
#
# Scenarios here target the `--port` override, which the WP4 driver never
# exercises at all, plus the unwritable-registry diagnosis. Where a scenario
# documents a CURRENTLY-OPEN defect it asserts the observed (wrong) behaviour
# and prints "XFAIL: <id>" so the driver stays green while the bug is pinned;
# the pytest wrapper asserts every expected XFAIL id is present, so a fix
# cannot land silently.
set -uo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
REAL_VENV="${ARAIL_TEST_VENV:-$REPO/.venv}"
if [[ ! -x "$REAL_VENV/bin/python" ]]; then
    REAL_VENV="$(cd "$REPO/.." 2>/dev/null && pwd)/.venv"
fi
if [[ ! -x "$REAL_VENV/bin/python" ]]; then
    echo "SKIP: no usable .venv found — cannot import arail.*"
    exit 0
fi

fail() { echo "FAIL: $1" >&2; exit 1; }
pass_count=0
ok_scenario() { pass_count=$((pass_count + 1)); }
xfail() { echo "XFAIL: $1"; }

_timeout() {
    local secs="$1"; shift
    "$REAL_VENV/bin/python" -c '
import os, signal, subprocess, sys
secs = float(sys.argv[1]); cmd = sys.argv[2:]
p = subprocess.Popen(cmd, start_new_session=True)
try:
    sys.exit(p.wait(timeout=secs))
except subprocess.TimeoutExpired:
    try: os.killpg(os.getpgid(p.pid), signal.SIGKILL)
    except Exception: pass
    sys.exit(124)
' "$secs" "$@"
}

WORK="$(mktemp -d)"
cleanup() { chmod -R u+w "$WORK" 2>/dev/null; rm -rf "$WORK"; }
trap cleanup EXIT

FAKE_HOME="$WORK/home"
mkdir -p "$FAKE_HOME"

_make_stub_bin() {
    local bin="$WORK/stubbin"
    mkdir -p "$bin"
    # uvicorn dies instantly — never binds, never answers /api/instance, so
    # stage [6/8]'s readiness poll fails fast on child death instead of
    # burning the 60s cap.
    printf '#!/usr/bin/env bash\nexit 1\n' > "$bin/uvicorn"
    for b in ollama open xdg-open; do printf '#!/usr/bin/env bash\nexit 0\n' > "$bin/$b"; done
    chmod +x "$bin"/*
    printf '%s' "$bin"
}
STUB_BIN="$(_make_stub_bin)"

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

_make_world() {
    PYTHONPATH="$REPO/tests" "$REAL_VENV/bin/python" -c "
from pathlib import Path
from world_bundle_builder import make_bundle
make_bundle(Path('$1/lab/worlds'), slug='$2', display_name='$3')
"
}

# Pre-seed a pinned env pack so a scenario can exercise the RE-BOOT branch of
# stage [4/8] without paying for a full first boot (LanceDB init is slow).
_seed_pack() {
    local fake="$1"
    local slug="$2"
    local portal="$3"
    local lance="$4"
    local root="$fake/lab/instances/$slug"
    mkdir -p "$root/data" "$root/pkb/sources" "$root/pkb/notes" "$root/log"
    cat > "$root/instance.env" <<EOF
ARAIL_INSTANCE=$slug
ARAIL_ENV_FILE=$root/instance.env
LAB_ROOT=$root
ARAIL_DATA_DIR=$root/data
LAB_PKB=$root/pkb
ARAIL_EXPERIMENTS_DIR=$root/data/experiments
ARAIL_MODELS_DIR=$fake/lab/models
ARAIL_WORLDS_DIR=$fake/lab/worlds
PORTAL_PORT=$portal
LANCE_PORT=$lance
BIND_ADDR=127.0.0.1
LAB_NAME="Seeded World"
LAB_SHORT_NAME=$slug
LAB_THEME=
LAB_INTENT=$slug
EOF
}

_run_start() {
    local fake="$1"; shift
    ( cd "$fake" && PATH="$STUB_BIN:$PATH" HOME="$FAKE_HOME" ARAIL_NO_BROWSER=1 \
        _timeout 45 bash scripts/start.sh "$@" ) 2>&1
}

_pack_port() {
    grep -E "^$2=" "$1/lab/instances/$3/instance.env" 2>/dev/null | head -n1 | cut -d= -f2-
}

# ---------------------------------------------------------------------------
# 1) QA-1 (FIXED) — `--port` on the RE-BOOT path used to skip the
#    reserved-port exclusion list. First boot correctly refuses `--port
#    8888` (jupyter). A second invocation, once instance.env exists, now
#    goes through the SAME _instance_validate_port_override check and is
#    refused identically — the pack must stay pinned at its original ports.
# ---------------------------------------------------------------------------
F1="$(_make_fake_repo r1)"
_make_world "$F1" ai "AI World" || fail "s1: could not build fixture World"

out="$(_run_start "$F1" --world ai --port 8888)"
[[ "$out" == *"collides with a reserved port"* ]] \
    || fail "s1a: FIRST boot must refuse a reserved --port; got: $out"
[[ ! -f "$F1/lab/instances/ai/instance.env" ]] \
    || fail "s1a: a refused first boot must not leave an env pack behind"
ok_scenario

_seed_pack "$F1" ai 8090 8094
out="$(_run_start "$F1" --world ai --port 8888)"
p="$(_pack_port "$F1" PORTAL_PORT ai)"
[[ "$out" == *"collides with a reserved port"* ]] \
    || fail "s1b: QA-1 — reboot --port must be refused too: $out"
[[ "$p" == "8090" ]] \
    || fail "s1b: QA-1 — a refused reboot --port must not repin the pack (got $p)"
ok_scenario

# ---------------------------------------------------------------------------
# 2) QA-2 (FIXED) — `--port` used to accept values outside the valid TCP
#    range. `--port 0` used to pin PORTAL_PORT=0 / LANCE_PORT=4 (a
#    privileged port) into the pack permanently; `--port 70000` used to
#    pass the bind check vacuously. Both are now rejected at argv-parse
#    time, before any World is resolved or instance root created.
# ---------------------------------------------------------------------------
F2="$(_make_fake_repo r2)"
_make_world "$F2" ai "AI World" || fail "s2: could not build fixture World"
out="$(_run_start "$F2" --world ai --port 0)"
[[ "$out" == *"not a valid port"* ]] \
    || fail "s2: QA-2 — --port 0 must be refused: $out"
[[ ! -f "$F2/lab/instances/ai/instance.env" ]] \
    || fail "s2: QA-2 — a refused --port must not leave an env pack behind"
ok_scenario

out="$(_run_start "$F2" --world ai --port 70000)"
[[ "$out" == *"not a valid port"* ]] \
    || fail "s2b: QA-2 — --port 70000 must be refused: $out"
[[ ! -f "$F2/lab/instances/ai/instance.env" ]] \
    || fail "s2b: QA-2 — a refused --port must not leave an env pack behind"
ok_scenario

# ---------------------------------------------------------------------------
# 3) QA-5 (FIXED) — `--port` used to skip the registry-collision check
#    `inst_allocate_ports` itself performs. Pin World B to the exact ports
#    an existing (registered but not live) record already owns — must
#    now refuse, and the pre-existing record must be untouched.
# ---------------------------------------------------------------------------
F3="$(_make_fake_repo r3)"
_make_world "$F3" ai "AI World" || fail "s3: could not build fixture World"
mkdir -p "$F3/lab/instances/registry.d"
cat > "$F3/lab/instances/registry.d/fin.json" <<'EOF'
{"schema":"arail.instance-registry/v1","slug":"fin","display_name":"Fin",
 "portal_port":8090,"lance_port":8094,"portal_pid":999999,"memory_pid":999999,
 "launcher_pid":999999,"bind":"127.0.0.1","data_dir":"/nope","checkout":"/nope",
 "token":"t","started_at":"2026-07-28T00:00:00Z"}
EOF
out="$(_run_start "$F3" --world ai --port 8090)"
[[ "$out" == *"already registered to another World instance"* ]] \
    || fail "s3: QA-5 — --port collision with an existing record must be refused: $out"
grep -q '"portal_port": *8090' "$F3/lab/instances/registry.d/fin.json" \
    || fail "s3: the pre-existing record was mutated — it must not be"
[[ ! -f "$F3/lab/instances/ai/instance.env" ]] \
    || fail "s3: QA-5 — a refused --port must not leave an env pack behind"
ok_scenario

# ---------------------------------------------------------------------------
# 4) QA-3 (FIXED) — an UNWRITABLE registry.d used to make stage [3/8] blame
#    a phantom concurrent start. `( set -o noclobber; echo > file )` fails
#    identically for EEXIST and EACCES, so a permissions problem used to be
#    reported as "another start for 'ai' is in progress (pid ?)". A
#    writability check now runs BEFORE the claim attempt and names the
#    real cause.
# ---------------------------------------------------------------------------
F4="$(_make_fake_repo r4)"
_make_world "$F4" ai "AI World" || fail "s4: could not build fixture World"
mkdir -p "$F4/lab/instances/registry.d"
chmod 0500 "$F4/lab/instances/registry.d"
out="$(_run_start "$F4" --world ai)"
chmod 0700 "$F4/lab/instances/registry.d"
[[ "$out" == *"not writable"* ]] \
    || fail "s4: QA-3 — unwritable registry.d must name the real cause: $out"
[[ "$out" != *"another start for 'ai' is in progress"* ]] \
    || fail "s4: QA-3 — still misdiagnosed as a concurrent start: $out"
[[ ! -f "$F4/lab/instances/registry.d/ai.json" ]] \
    || fail "s4: no record may be written when the claim failed"
ok_scenario

# ---------------------------------------------------------------------------
# 5) Happy-path / correctness: a World directory removed AFTER the catalog is
#    built must produce a named exit-2 refusal at stage [2/8], never a
#    half-built instance root. (F5 applied to the delete-between-render-and-
#    -selection race the picker can hit.)
# ---------------------------------------------------------------------------
F5="$(_make_fake_repo r5)"
_make_world "$F5" ai "AI World" || fail "s5: could not build fixture World"
_make_world "$F5" fin "Fin World" || fail "s5: could not build fixture World"
rm -rf "$F5/lab/worlds/fin"
( cd "$F5" && PATH="$STUB_BIN:$PATH" HOME="$FAKE_HOME" ARAIL_NO_BROWSER=1 \
    _timeout 45 bash scripts/start.sh --world fin >"$WORK/s5.out" 2>&1 )
rc=$?
out="$(cat "$WORK/s5.out")"
[[ "$rc" == "2" ]] || fail "s5: expected exit 2 for a vanished World, got $rc: $out"
[[ "$out" == *"no such World: fin"* ]] || fail "s5: refusal must name the slug: $out"
[[ "$out" == *"Known Worlds:"* && "$out" == *"ai"* ]] \
    || fail "s5: refusal must list the surviving slugs: $out"
[[ ! -d "$F5/lab/instances/fin" ]] \
    || fail "s5: a refused resolve must not create an instance root"
[[ ! -f "$F5/lab/instances/registry.d/fin.claim" ]] \
    || fail "s5: a refused resolve must not leak a claim"
ok_scenario

# ---------------------------------------------------------------------------
# 6) Security: `--world` with a traversal payload must be refused BEFORE any
#    directory is created, and must not read outside lab/worlds/. Extends the
#    WP4 driver's single '../../etc' case across the traversal alphabet.
# ---------------------------------------------------------------------------
F6="$(_make_fake_repo r6)"
_make_world "$F6" ai "AI World" || fail "s6: could not build fixture World"
mkdir -p "$WORK/outside"
printf 'secret\n' > "$WORK/outside/loot.txt"
for payload in "../outside" "../../outside" "/etc" "ai/../../outside" \
               "ai;id" '$(id)' '`id`' "AI" "-ai" ".." "."; do
    ( cd "$F6" && PATH="$STUB_BIN:$PATH" HOME="$FAKE_HOME" ARAIL_NO_BROWSER=1 \
        _timeout 45 bash scripts/start.sh --world "$payload" >"$WORK/s6.out" 2>&1 )
    rc=$?
    out="$(cat "$WORK/s6.out")"
    [[ "$rc" == "2" ]] \
        || fail "s6: --world '$payload' must exit 2, got $rc: $out"
    [[ "$out" != *"uid="* ]] \
        || fail "s6: --world '$payload' executed a command: $out"
    [[ "$out" != *"secret"* ]] \
        || fail "s6: --world '$payload' read outside the Worlds jail"
    [[ ! -d "$F6/lab/instances/$payload" ]] \
        || fail "s6: --world '$payload' created an instance root"
done
# Nothing outside the fake repo may have been created or removed.
[[ -f "$WORK/outside/loot.txt" ]] || fail "s6: a payload deleted a file outside the jail"
ok_scenario

# ---------------------------------------------------------------------------
# 7) `--list` and `--help` remain side-effect-free even with a hostile argv
#    following them, and unknown flags never reach a spawn.
# ---------------------------------------------------------------------------
F7="$(_make_fake_repo r7)"
_make_world "$F7" ai "AI World" || fail "s7: could not build fixture World"
out="$(_run_start "$F7" --list)"
[[ "$out" == *"ai"* ]] || fail "s7: --list must list ai: $out"
[[ ! -d "$F7/lab/instances" ]] || fail "s7: --list created lab/instances/"

( cd "$F7" && PATH="$STUB_BIN:$PATH" HOME="$FAKE_HOME" ARAIL_NO_BROWSER=1 \
    _timeout 30 bash scripts/start.sh --world >"$WORK/s7.out" 2>&1 ); rc=$?
[[ "$rc" == "2" ]] || fail "s7: a bare trailing --world must exit 2, got $rc"
grep -q "requires a slug" "$WORK/s7.out" || fail "s7: --world with no value must say so"

( cd "$F7" && PATH="$STUB_BIN:$PATH" HOME="$FAKE_HOME" ARAIL_NO_BROWSER=1 \
    _timeout 30 bash scripts/start.sh --port >"$WORK/s7b.out" 2>&1 ); rc=$?
[[ "$rc" == "2" ]] || fail "s7: a bare trailing --port must exit 2, got $rc"

( cd "$F7" && PATH="$STUB_BIN:$PATH" HOME="$FAKE_HOME" ARAIL_NO_BROWSER=1 \
    _timeout 30 bash scripts/start.sh --port abc --world ai >"$WORK/s7c.out" 2>&1 ); rc=$?
[[ "$rc" == "2" ]] || fail "s7: a non-numeric --port must exit 2, got $rc"
[[ ! -d "$F7/lab/instances" ]] || fail "s7: a rejected argv created lab/instances/"
ok_scenario

# ---------------------------------------------------------------------------
# 8) Secrets: no value from the root lab's secrets.env may appear on stdout,
#    on stderr, in the env pack, or in any instance log during a start.
# ---------------------------------------------------------------------------
F8="$(_make_fake_repo r8)"
_make_world "$F8" ai "AI World" || fail "s8: could not build fixture World"
printf 'ANTHROPIC_API_KEY=sk-qa-CANARY-9c1f0\nOPENROUTER_API_KEY=or-qa-CANARY-2b7\n' \
    > "$F8/lab/data/secrets.env"
chmod 0600 "$F8/lab/data/secrets.env"
out="$(_run_start "$F8" --world ai)"
[[ "$out" != *"CANARY"* ]] \
    || fail "s8: a secret value reached start's stdout/stderr: $out"
[[ "$out" == *"Provider keys are per-instance"* ]] \
    || fail "s8: the per-instance-keys notice must be printed when a root secrets.env exists"
if [[ -f "$F8/lab/instances/ai/instance.env" ]]; then
    grep -q CANARY "$F8/lab/instances/ai/instance.env" \
        && fail "s8: a secret value reached the env pack"
fi
if [[ -d "$F8/lab/instances/ai/log" ]]; then
    grep -rq CANARY "$F8/lab/instances/ai/log" 2>/dev/null \
        && fail "s8: a secret value reached an instance log"
fi
[[ ! -e "$F8/lab/instances/ai/data/secrets.env" ]] \
    || fail "s8: the root lab's secrets.env was copied/symlinked into the instance"
ok_scenario

echo "OK: $pass_count scenario(s)"
exit 0
