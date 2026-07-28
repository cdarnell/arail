#!/usr/bin/env bash
# scripts/lib/instances.sh — the single source of truth for World-instance
# paths, the instance registry, and liveness. See:
#   sprints/2026-07-28-concurrent-worlds/ARCHITECTURE.md §1, §2, §2.6
#
# Sourced (never executed) by arailctl, scripts/start.sh, scripts/status.sh,
# scripts/install-daemon.sh. Callers must set REPO_ROOT before sourcing —
# every path helper below is derived from it, never from CWD.
#
# Rule (ARCHITECTURE.md §2.6): after this sprint, the strings
#   ~/Library/LaunchAgents/io.arail.portal.plist
#   launchctl list io.arail.portal
# appear in exactly one place each — HERE, inside daemon_active() /
# daemon_plist_installed(). No other file in this repo should re-derive
# daemon liveness.
#
# This file only defines functions/vars. It never has side effects on
# source (no directory creation, no process spawn) — WP1 scope is "no
# caller changes yet"; callers opt in explicitly by invoking a function.
set -uo pipefail 2>/dev/null || true  # tolerate being sourced under a caller's own `set`

# ── Constants ─────────────────────────────────────────────────────────────

# Slug jail — MUST match src/arail/world_mount.py:141 (_SLUG_RE), verified.
INST_SLUG_RE='^[a-z0-9][a-z0-9-]*$'

# Port layout (ARCHITECTURE.md §3.4).
INST_PORT_BASE=8090
INST_PORT_BLOCK_SIZE=10
INST_PORT_PORTAL_OFFSET=0
INST_PORT_LANCE_OFFSET=4
INST_PORT_CEILING=9100          # hard stop: refuse any allocation >= this
INST_MAX_INSTANCES_DEFAULT=3

# Claims older than this many seconds are treated as abandoned (F6).
INST_CLAIM_STALE_SECONDS=120

# ── Path helpers ──────────────────────────────────────────────────────────
# All require REPO_ROOT to already be set (absolute) by the caller.

inst_root_dir() {
    printf '%s/lab/instances\n' "$REPO_ROOT"
}

inst_registry_dir() {
    printf '%s/registry.d\n' "$(inst_root_dir)"
}

inst_instance_dir() {
    local slug="$1"
    printf '%s/%s\n' "$(inst_root_dir)" "$slug"
}

inst_env_file() {
    local slug="$1"
    printf '%s/instance.env\n' "$(inst_instance_dir "$slug")"
}

inst_data_dir() {
    printf '%s/data\n' "$(inst_instance_dir "$1")"
}

inst_pkb_dir() {
    printf '%s/pkb\n' "$(inst_instance_dir "$1")"
}

inst_log_dir() {
    printf '%s/log\n' "$(inst_instance_dir "$1")"
}

inst_registry_file() {
    local slug="$1"
    printf '%s/%s.json\n' "$(inst_registry_dir)" "$slug"
}

inst_registry_bad_file() {
    local slug="$1"
    printf '%s/%s.json.bad\n' "$(inst_registry_dir)" "$slug"
}

inst_claim_file() {
    local slug="$1"
    printf '%s/%s.claim\n' "$(inst_registry_dir)" "$slug"
}

inst_valid_slug() {
    local slug="${1-}"
    [[ "$slug" =~ $INST_SLUG_RE ]]
}

# ── Registry: write ───────────────────────────────────────────────────────
# inst_write_record <slug> <json-payload>
# <json-payload> is a JSON *object string* (schema: ARCHITECTURE.md §2.1).
# Passed as argv (not interpolated into a shell command), parsed and
# re-serialised by python3, then written via tmp + os.replace — the same
# atomic-rename technique world_mount.py:692-699 already uses. Never
# hand-rolled `echo > file` JSON (ARCHITECTURE.md §2.2).
inst_write_record() {
    local slug="$1" payload="$2"
    local dir
    dir="$(inst_registry_dir)"
    mkdir -p "$dir"
    python3 -c '
import json, os, sys

slug, payload, dest_dir = sys.argv[1], sys.argv[2], sys.argv[3]
data = json.loads(payload)
tmp = os.path.join(dest_dir, slug + ".json.tmp")
final = os.path.join(dest_dir, slug + ".json")
with open(tmp, "w", encoding="utf-8") as fh:
    json.dump(data, fh, indent=2)
    fh.write("\n")
os.replace(tmp, final)
' "$slug" "$payload" "$dir"
}

# ── Registry: read ────────────────────────────────────────────────────────
# inst_read_record <slug>
# Prints the record JSON on stdout; returns 1 (silently, no output) if the
# file is absent. Corrupt JSON is quarantined to <slug>.json.bad and this
# returns 2 — never raises, never crashes a caller (F16, mirrors
# list_available_worlds()'s never-raises contract).
inst_read_record() {
    local slug="$1"
    local f
    f="$(inst_registry_file "$slug")"
    [[ -f "$f" ]] || return 1
    local out
    if out="$(python3 -c '
import json, sys
try:
    with open(sys.argv[1], "r", encoding="utf-8") as fh:
        data = json.load(fh)
except Exception:
    sys.exit(1)
json.dump(data, sys.stdout)
' "$f" 2>/dev/null)"; then
        printf '%s' "$out"
        return 0
    fi
    # Corrupt or unparseable — quarantine, never block the caller.
    mv -f "$f" "$(inst_registry_bad_file "$slug")" 2>/dev/null || true
    return 2
}

# inst_record_field <json> <field>
# Pulls a single top-level field out of a record JSON string. Empty string
# (not an error) when the field is absent — callers already treat "" as
# "unknown" per the liveness predicate below.
inst_record_field() {
    local json="$1" field="$2"
    python3 -c '
import json, sys
try:
    data = json.loads(sys.argv[1])
except Exception:
    print("")
    sys.exit(0)
val = data.get(sys.argv[2], "")
print(val if val is not None else "")
' "$json" "$field"
}

# ── Registry: list / prune ────────────────────────────────────────────────

# inst_list_slugs — every slug with a *parseable* registry record, one per
# line. Corrupt files are quarantined as a side effect (matches
# inst_read_record's F16 contract) but are not listed.
inst_list_slugs() {
    local dir f slug
    dir="$(inst_registry_dir)"
    [[ -d "$dir" ]] || return 0
    for f in "$dir"/*.json; do
        [[ -e "$f" ]] || continue
        slug="$(basename "$f" .json)"
        inst_read_record "$slug" >/dev/null 2>&1 && echo "$slug"
    done
    return 0
}

# inst_prune <slug> — remove the registry record for <slug> iff it is
# stale (predicate steps 2/3 fail). Never touches lab/instances/<slug>/
# data (ARCHITECTURE.md §2.5). No-op, exit 0, if the record is alive or
# absent.
inst_prune() {
    local slug="$1"
    local f
    f="$(inst_registry_file "$slug")"
    [[ -f "$f" ]] || return 0
    if inst_alive "$slug"; then
        return 0
    fi
    rm -f "$f"
    return 0
}

# inst_prune_all — run inst_prune over every registered slug. Used by
# `status` (side effect of the read path) — never by `start` for a slug
# other than its own target.
inst_prune_all() {
    local slug
    while IFS= read -r slug; do
        [[ -n "$slug" ]] && inst_prune "$slug"
    done < <(inst_list_slugs)
    return 0
}

# ── Liveness predicate (ARCHITECTURE.md §2.3) ─────────────────────────────
# inst_alive <slug> [--probe]
# Returns 0 iff all of steps 1-3 hold (default), or all of 1-4 with --probe.
#   1. registry.d/<slug>.json exists and parses
#   2. kill -0 <portal_pid> succeeds
#   3. ps -p <portal_pid> -o command= matches uvicorn.*arail\.portal\.app
#      AND contains --port <portal_port>  (anti PID-reuse)
#   4. (--probe only) GET /api/instance token+checkout match the record
#      (anti wrong-checkout). Implemented as a helper other WPs (start's
#      attach check, stop's confirmation, status --probe) call explicitly —
#      kept here since it is part of the one predicate definition.
inst_alive() {
    local slug="$1" mode="${2:-}"
    local rec
    rec="$(inst_read_record "$slug" 2>/dev/null)" || return 1

    local pid port
    pid="$(inst_record_field "$rec" portal_pid)"
    port="$(inst_record_field "$rec" portal_port)"
    [[ -n "$pid" ]] || return 1

    kill -0 "$pid" 2>/dev/null || return 1

    local cmd
    cmd="$(ps -p "$pid" -o command= 2>/dev/null || true)"
    [[ -n "$cmd" ]] || return 1
    [[ "$cmd" =~ uvicorn.*arail\.portal\.app ]] || return 1
    if [[ -n "$port" ]]; then
        [[ "$cmd" == *"--port $port"* || "$cmd" == *"--port=$port"* ]] || return 1
    fi

    if [[ "$mode" == "--probe" ]]; then
        inst_probe_matches "$slug" "$rec" || return 1
    fi

    return 0
}

# inst_probe_matches <slug> <record-json> — step 4 in isolation, so start's
# attach check and status --probe can call it without paying for steps 1-3
# twice. GET /api/instance is a WP6 (portal) deliverable; until it exists
# this returns 1 (fail closed — never claim a checkout match we didn't
# verify).
inst_probe_matches() {
    local slug="$1" rec="$2"
    local bind port token checkout expect_token expect_checkout url response
    bind="$(inst_record_field "$rec" bind)"
    port="$(inst_record_field "$rec" portal_port)"
    expect_token="$(inst_record_field "$rec" token)"
    expect_checkout="$(inst_record_field "$rec" checkout)"
    [[ -n "$bind" && -n "$port" ]] || return 1
    command -v curl >/dev/null 2>&1 || return 1
    url="http://${bind}:${port}/api/instance"
    response="$(curl -sf -m 0.7 "$url" 2>/dev/null)" || return 1
    [[ -n "$response" ]] || return 1
    token="$(inst_record_field "$response" token)"
    checkout="$(inst_record_field "$response" checkout)"
    [[ -n "$token" && "$token" == "$expect_token" ]] || return 1
    [[ -n "$checkout" && "$checkout" == "$expect_checkout" ]] || return 1
    return 0
}

# inst_any_alive — prints the slug of the first live instance found (if
# any) on stdout and returns 0; returns 1 with no output when none are
# alive. Used by install-daemon.sh's refusal guard (ARCHITECTURE.md §2.6:
# "inst_any_alive() (registry-driven) || pgrep fallback for a legacy root
# lab; message names which instance blocks").
inst_any_alive() {
    local slug
    while IFS= read -r slug; do
        [[ -n "$slug" ]] || continue
        if inst_alive "$slug"; then
            printf '%s\n' "$slug"
            return 0
        fi
    done < <(inst_list_slugs)
    return 1
}

# ── Daemon-mode predicate (ARCHITECTURE.md §2.6, §4.4) ───────────────────
# daemon_plist_installed — plist FILE existence only (today's arailctl:195
# check). Kept as a separate, narrower helper because status.sh wants to
# print "installed, inactive" as distinct from "active".
daemon_plist_installed() {
    [[ -f "$HOME/Library/LaunchAgents/io.arail.portal.plist" ]]
}

# daemon_active — true iff the plist exists AND launchctl reports a live
# numeric PID for it. This is the actual liveness check; replaces the four
# disagreeing checks named in ARCHITECTURE.md §2.6's table. A loaded-but
# crash-looping agent (no PID line) is NOT active.
daemon_active() {
    [[ "$(uname -s)" == "Darwin" ]] || return 1
    daemon_plist_installed || return 1
    command -v launchctl >/dev/null 2>&1 || return 1
    local line
    line="$(launchctl list io.arail.portal 2>/dev/null | grep -E '"PID"[[:space:]]*=' || true)"
    [[ -n "$line" ]] || return 1
    # Extract the numeric value; a malformed/blank PID is not a live daemon.
    local pid
    pid="$(printf '%s' "$line" | grep -oE '[0-9]+' | head -n1 || true)"
    [[ -n "$pid" ]]
}
