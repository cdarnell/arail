#!/usr/bin/env bash
# =============================================================================
#  ${LAB_NAME} Reset — Clean wipe / selective reset
# =============================================================================
set -euo pipefail

BOLD="\033[1m"
RED="\033[0;31m"
GREEN="\033[0;32m"
YELLOW="\033[0;33m"
RESET="\033[0m"

info()  { echo -e "  ${GREEN}✓${RESET} $*"; }
warn()  { echo -e "  ${YELLOW}⚠${RESET} $*"; }
error() { echo -e "  ${RED}✗${RESET} $*"; }

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AUTO_CONFIRM="false"
DESTROY_LOG="/tmp/arail-destroy.log"
cd "$REPO_ROOT"

# scripts/lib/instances.sh is the single source of truth for daemon
# liveness (ARCHITECTURE.md §2.6). Optional here (not required): reset.sh
# is unit-tested via a sandboxed copy of THIS file alone
# (tests/test_reset_paths.py, tests/test_world_reset.py), so the source
# must degrade gracefully when the sibling file isn't present.
# shellcheck disable=SC1091
[[ -f "$REPO_ROOT/scripts/lib/instances.sh" ]] && source "$REPO_ROOT/scripts/lib/instances.sh"

# shellcheck disable=SC1091
[[ -f .env ]] && set -a && source .env && set +a
# lab.conf holds the ports setup.sh actually picked (possibly auto-bumped
# off the .env/default values, e.g. when 8080 was taken at setup time —
# setup.sh:1637-1646 writes the RESOLVED ports here). stop_services()
# below builds its kill patterns from these same PORTAL_PORT/LANCE_PORT/
# MLX_OPENAI_PORT variables; without sourcing lab.conf, `./arailctl stop`
# matches the .env/default port instead of the port the lab is actually
# running on and silently stops nothing on any machine where a port was
# bumped (REVIEW.md B1 — a silent regression: before this sprint the kill
# patterns were port-agnostic and worked regardless of lab.conf).
# shellcheck disable=SC1091
[[ -f lab.conf ]] && set -a && source lab.conf && set +a
LAB_NAME="${LAB_NAME:-Arail}"

# ── Runtime paths — mirror src/arail/config.py ───────────────────────
# The portal decides where the knowledge base actually lives; reset MUST
# target that same tree. Hardcoding lab/pkb here made `./arailctl reset pkb`
# report success while a LAB_PKB-relocated KB survived untouched — which
# silently breaks the privacy contract in docs/agents.md ("Wiping memory is
# always one command") and Buddy's "wipe the PKB wipes Buddy's memory".
#
# Precedence, identical to config.py:
#   pkb    : LAB_PKB → legacy LAB_PKM → $LAB_ROOT/pkb
#   data   : ARAIL_DATA_DIR   → $LAB_ROOT/data
#   models : ARAIL_MODELS_DIR → $LAB_ROOT/models
# with LAB_ROOT defaulting to "lab". Paths are tilde-expanded, matching
# config.py's Path(...).expanduser() (leading ~ / ~/ only; ~user is not
# supported here).
#
# These resolvers are pure: stdout is the path and nothing else, so they
# are safe inside $(...). tests/test_reset_paths.py pins them against the
# real Python resolver so the two cannot drift.
_expand_tilde() {
    local p="${1-}"
    case "$p" in
        "~")     printf '%s' "$HOME" ;;
        "~/"*)   printf '%s%s' "$HOME" "${p#\~}" ;;
        *)       printf '%s' "$p" ;;
    esac
}

_resolve_lab_root() {
    local r
    r="$(_expand_tilde "${LAB_ROOT:-lab}")"
    # Drop a trailing slash so callers can always append "/<name>" cleanly.
    # "/" collapses to "" and yields "/pkb", matching Python's Path("/")/"pkb".
    r="${r%/}"
    printf '%s' "$r"
}

_resolve_pkb_root() {
    if [[ -n "${LAB_PKB:-}" ]]; then
        _expand_tilde "$LAB_PKB"
    elif [[ -n "${LAB_PKM:-}" ]]; then
        _expand_tilde "$LAB_PKM"
    else
        printf '%s/pkb' "$(_resolve_lab_root)"
    fi
}

_resolve_data_dir() {
    if [[ -n "${ARAIL_DATA_DIR:-}" ]]; then
        _expand_tilde "$ARAIL_DATA_DIR"
    else
        printf '%s/data' "$(_resolve_lab_root)"
    fi
}

_resolve_models_dir() {
    if [[ -n "${ARAIL_MODELS_DIR:-}" ]]; then
        _expand_tilde "$ARAIL_MODELS_DIR"
    else
        printf '%s/models' "$(_resolve_lab_root)"
    fi
}

PKB_DIR="$(_resolve_pkb_root)"
DATA_DIR="$(_resolve_data_dir)"
MODELS_DIR="$(_resolve_models_dir)"

# config.py logs a deprecation warning for LAB_PKM; mirror it here so the
# CLI tells the same story. Kept out of the resolver — it must stay pure.
if [[ -z "${LAB_PKB:-}" && -n "${LAB_PKM:-}" ]]; then
    warn "LAB_PKM is deprecated — rename to LAB_PKB in your .env. The old name still works for now."
fi

# ── Stop running services ────────────────────────────────────────────
# stop_services — stops the ROOT lab only. Patterns are ARAIL-SCOPED
# (module paths) AND, for the uvicorn processes, PORT-scoped
# (ARCHITECTURE.md §4.2 "Fixing reset.sh's kill-everything"): a bare
# "uvicorn.*arail\.portal\.app" pattern matches ANY portal on the box, so
# the moment a second World instance exists, an un-scoped root-lab stop
# would silently kill it mid-write (F15). Appending the root lab's own
# PORTAL_PORT/LANCE_PORT/MLX_OPENAI_PORT to the pattern means this
# function only ever touches the root lab's own processes; instance
# processes are stopped exclusively via stop_instance() below, using
# registry-verified PIDs.
stop_services() {
    info "Stopping ${LAB_NAME} services..."
    # QA-11: these patterns used to be port-scoped only, not checkout-
    # scoped. Two ARAIL checkouts on one machine both default to
    # 8080/7414, so `./arailctl stop` in checkout A killed checkout B's
    # root-lab services — the BRIEF's motivating incident, reproduced live
    # during QA. uvicorn's argv carries no checkout path by default; start.sh
    # now passes `--app-dir "$REPO_ROOT"` explicitly (functionally a no-op —
    # uvicorn already defaults --app-dir to cwd, which start.sh already `cd`s
    # to REPO_ROOT before spawning) SPECIFICALLY so this pattern has
    # something checkout-scoped to match against. The instance path
    # (stop_instance, below) never pattern-matches at all — only the legacy
    # root-lab path needed this.
    local patterns=(
        "uvicorn.*arail\.portal\.app.*--app-dir ${REPO_ROOT}.*--port ${PORTAL_PORT:-8080}"
        "uvicorn.*arail\.memory_service.*--app-dir ${REPO_ROOT}.*--port ${LANCE_PORT:-7414}"
        "uvicorn.*arail\.mlx_openai_server.*--app-dir ${REPO_ROOT}.*--port ${MLX_OPENAI_PORT:-11435}"
        "ttyd.*${TERMINAL_PORT:-7681}"
        "jupyter-lab.*${NOTEBOOK_PORT:-8888}"
        "code-server.*${IDE_PORT:-8443}"
    )
    local pids=()
    for pattern in "${patterns[@]}"; do
        local p
        p=$(pgrep -f "$pattern" 2>/dev/null || true)
        [[ -n "$p" ]] && pids+=($p)
    done
    # Ollama is a shared, machine-wide service (only one instance can
    # bind :11434), not ARAIL's own code — unlike the patterns above, we
    # never pattern-match for it. We only ever stop the specific PID
    # start.sh recorded when IT was the one that launched Ollama; one the
    # user runs independently (brew services, another project, manually)
    # is left completely alone, pidfile absent, nothing touched.
    local ollama_pid
    ollama_pid="$(_ollama_pid_if_we_started_it)"
    [[ -n "$ollama_pid" ]] && pids+=("$ollama_pid")
    if (( ${#pids[@]} > 0 )); then
        kill "${pids[@]}" 2>/dev/null || true
        # SIGTERM → up to 2s grace → SIGKILL stragglers (opencode shape).
        local waited=0
        while (( waited < 20 )); do
            local alive=""
            for pid in "${pids[@]}"; do
                kill -0 "$pid" 2>/dev/null && alive="1"
            done
            [[ -z "$alive" ]] && break
            sleep 0.1; waited=$((waited + 1))
        done
        for pid in "${pids[@]}"; do
            kill -0 "$pid" 2>/dev/null && kill -9 "$pid" 2>/dev/null || true
        done
        info "Stopped ${#pids[@]} process(es)."
    else
        info "No running services found."
    fi
    rm -f "${DATA_DIR}/.ollama-started-by-arail.pid"
    # daemon_active() (scripts/lib/instances.sh) is the single liveness
    # predicate; when the sibling file isn't sourced (sandboxed test copies
    # of this file alone) the NOTE below is skipped, not wrongly printed —
    # it is purely informational and no test asserts on it.
    if command -v daemon_active >/dev/null 2>&1 && daemon_active; then
        info "NOTE: launchd agents are loaded — use ./arailctl stop to keep the lab down."
    fi
}

# stop_instance <slug> — instance-scoped kill (ARCHITECTURE.md §4.2).
# Only ever kills a PID that VERIFIES against the registry record (module +
# port for portal/memory, "start.sh ... <slug>" for the launcher). An
# unverified PID (F3: reused by an unrelated process) is skipped and
# reported — never killed. Removes the registry record only; NEVER touches
# lab/instances/<slug>/ data. Requires scripts/lib/instances.sh to be
# sourced (guarded by the caller — this function is only invoked when
# `command -v inst_read_record` succeeds).
stop_instance() {
    local slug="$1"
    local rec rc
    if rec="$(inst_read_record "$slug" 2>/dev/null)"; then
        rc=0
    else
        rc=$?
    fi
    if (( rc != 0 )); then
        warn "No (readable) registry record for '${slug}' — nothing to stop."
        return 0
    fi

    local portal_pid memory_pid launcher_pid portal_port lance_port
    portal_pid="$(inst_record_field "$rec" portal_pid)"
    memory_pid="$(inst_record_field "$rec" memory_pid)"
    launcher_pid="$(inst_record_field "$rec" launcher_pid)"
    portal_port="$(inst_record_field "$rec" portal_port)"
    lance_port="$(inst_record_field "$rec" lance_port)"

    info "Stopping World instance '${slug}'..."

    local verified_pids=()
    local cmd

    if [[ -n "$portal_pid" ]]; then
        cmd="$(ps -p "$portal_pid" -o command= 2>/dev/null || true)"
        if [[ -n "$cmd" && "$cmd" =~ uvicorn.*arail\.portal\.app ]] \
           && { [[ "$cmd" == *"--port $portal_port"* ]] || [[ "$cmd" == *"--port=$portal_port"* ]]; }; then
            verified_pids+=("$portal_pid")
        else
            warn "  portal pid ${portal_pid} did not verify (module/port mismatch) — skipped, not killed."
        fi
    fi

    if [[ -n "$memory_pid" ]]; then
        cmd="$(ps -p "$memory_pid" -o command= 2>/dev/null || true)"
        if [[ -n "$cmd" && "$cmd" =~ uvicorn.*arail\.memory_service ]] \
           && { [[ "$cmd" == *"--port $lance_port"* ]] || [[ "$cmd" == *"--port=$lance_port"* ]]; }; then
            verified_pids+=("$memory_pid")
        else
            warn "  memory pid ${memory_pid} did not verify (module/port mismatch) — skipped, not killed."
        fi
    fi

    if [[ -n "$launcher_pid" ]]; then
        cmd="$(ps -p "$launcher_pid" -o command= 2>/dev/null || true)"
        # REVIEW.md M2: a bare "*start.sh* && *$slug*" substring test matches
        # ANY ARAIL start.sh process whose checkout PATH happens to contain
        # the slug as a substring — e.g. slug "ai" is a substring of "arail"
        # itself, so every start.sh launcher on the box would verify. Require
        # the exact "--world <slug>" (or "--world=<slug>") token instead of a
        # bare substring, matching the mechanism the record's own --world
        # flag was launched with.
        if [[ -n "$cmd" && "$cmd" == *"scripts/start.sh"* ]] \
           && { [[ "$cmd" == *"--world $slug"* ]] || [[ "$cmd" == *"--world=$slug"* ]]; }; then
            verified_pids+=("$launcher_pid")
        else
            warn "  launcher pid ${launcher_pid} did not verify — skipped, not killed."
        fi
    fi

    if (( ${#verified_pids[@]} > 0 )); then
        kill "${verified_pids[@]}" 2>/dev/null || true
        # SIGTERM → up to 2s grace → SIGKILL stragglers, same shape as
        # stop_services() above.
        local waited=0
        while (( waited < 20 )); do
            local alive=""
            for pid in "${verified_pids[@]}"; do
                kill -0 "$pid" 2>/dev/null && alive="1"
            done
            [[ -z "$alive" ]] && break
            sleep 0.1; waited=$((waited + 1))
        done
        for pid in "${verified_pids[@]}"; do
            kill -0 "$pid" 2>/dev/null && kill -9 "$pid" 2>/dev/null || true
        done
        info "  stopped ${#verified_pids[@]} verified process(es)."
    else
        info "  no verified processes to stop."
    fi

    # Ollama: only if THIS was the last live World instance, and only the
    # pidfile in THIS instance's own data dir (never pattern-matched, never
    # an Ollama we didn't start — same rule as the root lab).
    local remaining=0 other_slug
    while IFS= read -r other_slug; do
        [[ -n "$other_slug" && "$other_slug" != "$slug" ]] || continue
        inst_alive "$other_slug" && remaining=$((remaining + 1))
    done < <(inst_list_slugs)
    if (( remaining == 0 )); then
        local inst_data ollama_pid
        inst_data="$(inst_data_dir "$slug")"
        ollama_pid="$(_ollama_pid_if_we_started_it "$inst_data")"
        if [[ -n "$ollama_pid" ]]; then
            kill "$ollama_pid" 2>/dev/null || true
            rm -f "${inst_data}/.ollama-started-by-arail.pid"
        fi
    fi

    # Remove ONLY the registry record — never lab/instances/<slug>/ data.
    rm -f "$(inst_registry_file "$slug")"
}

# Returns the PID on stdout iff the pidfile exists AND that PID is still
# alive; empty otherwise. Never touches the pidfile — callers decide
# whether to kill the process and/or remove the file.
# Optional $1: a data dir to check instead of the root lab's $DATA_DIR —
# used by stop_instance() to check a World instance's OWN pidfile
# (ARCHITECTURE.md §4.2 step 5: "the pidfile in THAT instance's data dir").
_ollama_pid_if_we_started_it() {
    local pidfile="${1:-$DATA_DIR}/.ollama-started-by-arail.pid"
    [[ -f "$pidfile" ]] || return 0
    local pid
    pid="$(cat "$pidfile" 2>/dev/null || true)"
    # Explicit `if` + trailing `return 0`, not a bare `&&` chain: under
    # `set -e`, a stale/dead PID makes `kill -0` fail, and the caller
    # (`ollama_pid="$(_ollama_pid_if_we_started_it)"`) is a plain
    # assignment — not itself part of an if/while/&&/||, so it is NOT
    # exempt from errexit. A non-zero return here would silently abort
    # the entire reset/stop run the very first time a lab's Ollama had
    # already died on its own. This function must always return 0.
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
        printf '%s' "$pid"
    fi
    return 0
}

# ── Size report ──────────────────────────────────────────────────────
report_size() {
    local dir="$1"
    if [[ -d "$dir" ]]; then
        du -sh "$dir" 2>/dev/null | awk '{print $1}'
    else
        echo "0B"
    fi
}

# ── Reset modes ──────────────────────────────────────────────────────
reset_models() {
    local sz
    sz=$(report_size "$MODELS_DIR")
    if [[ -d "$MODELS_DIR" ]]; then
        warn "Removing ${MODELS_DIR}/ (${sz})..."
        rm -rf "$MODELS_DIR"
        info "Models removed."
    else
        info "No ${MODELS_DIR}/ directory."
    fi
}

reset_data() {
    # Stop an Ollama we started BEFORE the rm -rf below deletes its
    # pidfile out from under it — otherwise the process survives, now
    # untracked, with nothing left able to find or stop it later (the
    # same dangling-state shape C10 fixed for a lingering World mount
    # pointer). Never touches an Ollama we didn't start.
    local ollama_pid
    ollama_pid="$(_ollama_pid_if_we_started_it)"
    if [[ -n "$ollama_pid" ]]; then
        kill "$ollama_pid" 2>/dev/null || true
    fi
    if [[ -d "$DATA_DIR" ]]; then
        local sz
        sz=$(report_size "$DATA_DIR")
        warn "Removing ${DATA_DIR}/ (${sz})..."
        rm -rf "$DATA_DIR"
        info "${DATA_DIR}/ removed."
    fi
}

reset_plugins() {
    local plugins_dir="$HOME/.arail/plugins"
    if [[ -d "$plugins_dir" ]]; then
        local sz
        sz=$(report_size "$plugins_dir")
        warn "Removing ${plugins_dir} (${sz})..."
        rm -rf "$plugins_dir"
        info "Plugins removed."
    else
        info "No plugins installed."
    fi
}

reset_pkb() {
    # Wipes the central knowledge base — every user upload, agent-written
    # report, note, and seed-pack file. The wiki cache goes too so the
    # wiki rebuild starts clean. On next `./arailctl start` the starter
    # packs re-seed automatically.
    local pkb_dir="$PKB_DIR"
    local cache_dir="${PKB_DIR}/.wiki-cache"
    if [[ ! -d "$pkb_dir" ]]; then
        info "No ${pkb_dir}/ directory."
        return
    fi
    local sz
    sz=$(report_size "$pkb_dir")
    warn "Removing ${pkb_dir}/ (${sz})..."
    warn "This wipes every note, upload, agent finding, and seeded primer."
    rm -rf "$pkb_dir"
    rm -rf "$cache_dir" 2>/dev/null || true
    # Honor the ARAIL_CONVERSATIONS_DIR override: if chat memory lives OUTSIDE
    # the PKB root, wiping the PKB alone would silently leave transcripts behind
    # (breaking "wipe the PKB = forget me"). Wipe the override path too.
    local conv_override="${ARAIL_CONVERSATIONS_DIR:-}"
    if [[ -n "$conv_override" && -d "$conv_override" && "$conv_override" != "$pkb_dir"* ]]; then
        warn "Also removing ARAIL_CONVERSATIONS_DIR (${conv_override}) — chat memory."
        rm -rf "$conv_override"
    fi
    # A World's staged pages live under $PKB_DIR/sources/world-<slug>/ and were
    # just deleted; leaving lab/data/world-mount.json behind would advertise a
    # World whose knowledge base no longer exists. Drop the pointer, and re-arm
    # the one-shot World prompt so the next boot offers the picker again.
    rm -f "${DATA_DIR}/world-mount.json" 2>/dev/null || true
    rm -f "${DATA_DIR}/.world-prompt-seen" 2>/dev/null || true
    info "Knowledge base removed. Starter packs will re-seed on next ./arailctl start."
}

reset_pkb_seeds() {
    # Granular variant of reset_pkb: only wipes the seeded starter
    # primers under lab/pkb/sources/seeds/. User notes, agent writes,
    # and uploads are untouched. On next `./arailctl start` the starter
    # packs re-seed automatically — to keep them gone, also disable
    # ARAIL_AUTO_SEED in .env (TODO: not yet honored by the seeder).
    local seed_dir="${PKB_DIR}/sources/seeds"
    if [[ ! -d "$seed_dir" ]]; then
        info "No ${seed_dir}/ directory — nothing to remove."
        return
    fi
    local sz
    sz=$(report_size "$seed_dir")
    warn "Removing ${seed_dir}/ (${sz})..."
    warn "Only seed packs are removed. Your notes, uploads, and agent writes stay put."
    rm -rf "$seed_dir"
    info "Seed packs removed. They will re-install on next ./arailctl start unless disabled."
}

reset_skills() {
    # Removes installed skill-pack files (anything declared in
    # src/arail/skill_packs/manifest.yaml) from lab/pkb/skills/.
    # User-authored skills (any folder NOT in a pack) survive.
    # AGENT.md loadouts also survive — they're user-edited even
    # when seeded by ensure_default_loadouts.
    if [[ ! -d "${PKB_DIR}/skills" ]]; then
        info "No ${PKB_DIR}/skills/ — nothing to remove."
        return
    fi
    if [[ ! -f ".venv/bin/python" ]]; then
        warn "No .venv — can't read manifest. Skipping."
        return
    fi
    warn "Removing all skill-pack-installed skills (user skills survive)..."
    .venv/bin/python <<'PY'
from arail.skill_packs import list_packs, remove_pack
total = 0
for pack in list_packs():
    res = remove_pack(pack.id)
    n = len(res.get("removed", []))
    if n:
        print(f"  ✓ {pack.id}: removed {n} skill(s)")
    total += n
print(f"Done. {total} packed skill folders removed.")
PY
    info "Skill packs removed. AGENT.md loadouts and user-authored skills are intact."
}

reset_program() {
    # Wipes the system-authored "research recipe" — program.md, train.py,
    # any curated source fetches, and the autoresearch schedule. Always
    # preserves prepare.py: the validation contract is sticky on purpose
    # (changing it means the agent is grading its own homework).
    #
    # The recipe re-drafts on the next ./api/goal POST, OR via the
    # Re-draft button on the dashboard's "Lab knows" panel.
    local research_dir="${PKB_DIR}/research"
    local research_sources="${PKB_DIR}/sources/research"
    local schedule="${DATA_DIR}/autoresearch-schedule.json"
    # Note: this is the PKB index cache (pkb.py / pkb_index.py), which is a
    # different tree from wiki_vectors.py's .wiki-cache/lancedb.
    local pkb_cache="${PKB_DIR}/.cache/lancedb"

    local removed=0
    for f in "${research_dir}/program.md" "${research_dir}/train.py"; do
        if [[ -f "$f" ]]; then
            warn "Removing ${f}..."
            rm -f "$f"
            removed=$((removed + 1))
        fi
    done
    if [[ -d "$research_sources" ]]; then
        warn "Clearing ${research_sources}/ (curated source fetches)..."
        rm -rf "$research_sources"
        removed=$((removed + 1))
    fi
    if [[ -f "$schedule" ]]; then
        info "Resetting ${schedule} to paused."
        echo '{"mode": "paused", "window_start": "22:00", "window_end": "06:00"}' > "$schedule"
    fi
    # Force PKB vector index rebuild so the next semantic search reflects
    # the cleaner research dir.
    if [[ -d "$pkb_cache" ]]; then
        rm -rf "$pkb_cache"
    fi

    if (( removed == 0 )); then
        info "No research recipe files to remove."
    else
        info "Research program reset (${removed} item(s)). prepare.py left in place."
    fi
}

reset_env() {
    for f in .env lab.conf; do
        if [[ -f "$f" ]]; then
            warn "Removing ${f}..."
            rm -f "$f"
            info "${f} removed."
        fi
    done
    if [[ -d .venv ]]; then
        local sz
        sz=$(report_size ".venv")
        warn "Removing .venv/ (${sz})..."
        rm -rf .venv
        info "Virtual environment removed."
    fi
}

full_wipe() {
    stop_services
    reset_models
    reset_data
    reset_plugins
    # Per user decision (2026-04-24): `reset all` includes the research
    # program so a fresh setup starts with no leftover recipe. prepare.py
    # is preserved by reset_program itself.
    reset_program
    reset_env
    # Also clean caches
    for dir in __pycache__ .pytest_cache arail.egg-info; do
        find . -type d -name "$dir" -exec rm -rf {} + 2>/dev/null || true
    done
    find . -name "*.pyc" -delete 2>/dev/null || true
    info "Full wipe complete. Source code preserved."
    info "Run ${BOLD}./arailctl setup${RESET} to rebuild."
}

destroy_lab() {
    stop_services

    local target_dir="$REPO_ROOT"
    local helper
    helper="$(mktemp /tmp/arail-destroy.XXXXXX.sh)"

    cat > "$helper" <<EOF
#!/usr/bin/env bash
set -euo pipefail
sleep 2

rm -rf "$target_dir"
rm -rf "$HOME/.config/code-server"
rm -rf "$HOME/.local/share/code-server"
rm -rf "$HOME/.cache/code-server"
rm -rf "$HOME/.local/bin/code-server"
rm -rf "$HOME"/.local/lib/code-server-*
rm -rf "$HOME/.local/share/jupyter/runtime"
rm -rf "$HOME/.jupyter"
rm -rf /tmp/arail*
rm -f /tmp/jpserver-*.json /tmp/jupyter-*.html
rm -f "$helper"
EOF

    chmod +x "$helper"
    nohup bash "$helper" > "$DESTROY_LOG" 2>&1 < /dev/null &

    warn "Destroy scheduled. This removes the entire local lab copy and its app data."
    info "Destroy log: ${DESTROY_LOG}"
    info "Source directory scheduled for deletion: ${target_dir}"
}

# ── Usage / menu ─────────────────────────────────────────────────────
usage() {
    echo ""
    echo -e "  ${BOLD}${LAB_NAME} Reset${RESET}"
    echo ""
    echo "  Usage: ./arailctl reset [mode] [--yes]"
    echo ""
    echo "  Modes:"
    echo "    models    Remove downloaded models only"
    echo "    data      Remove experiments and data"
    echo "    pkb       Remove the knowledge base (all notes, uploads,"
    echo "              agent findings, seed packs). Re-seeds on next start."
    echo "    pkb-seeds Remove only the seeded starter primers; keep your notes."
    echo "    program   Remove the auto-drafted research recipe (program.md,"
    echo "              train.py, curated source fetches). Keeps prepare.py."
    echo "    skills    Remove installed skill packs from lab/pkb/skills/."
    echo "              User-authored skills + AGENT.md loadouts stay put."
    echo "    plugins   Remove installed plugins"
    echo "    env       Remove .venv, .env, lab.conf"
    echo "    full      Complete wipe — keeps the knowledge base safe."
    echo "              Chain with 'pkb' if you truly want everything gone."
    echo "    destroy   Delete the entire local lab copy and app data"
    echo "    stop      Just stop running services"
    echo ""
    echo "  If no mode given, interactive menu is shown."
    echo ""
}

interactive_menu() {
    echo ""
    echo -e "  ${BOLD}${LAB_NAME} Reset${RESET}"
    echo ""

    # Show sizes
    echo -e "  Current footprint:"
    for dir in "$MODELS_DIR" "$DATA_DIR" "$PKB_DIR" .venv; do
        if [[ -d "$dir" ]]; then
            echo -e "    ${dir}/  $(report_size "$dir")"
        fi
    done
    echo ""

    echo "  What do you want to reset?"
    echo ""
    echo "    1) Models only"
    echo "    2) Data & experiments"
    echo "    3) Knowledge base (notes, uploads, agent findings)"
    echo "    4) Plugins"
    echo "    5) Environment (.venv, .env, configs)"
    echo "    6) Full wipe (preserves the knowledge base)"
    echo "    7) Destroy this lab copy entirely"
    echo "    8) Just stop services"
    echo "    0) Cancel"
    echo ""
    read -rp "  Choice [0-8]: " choice

    case "${choice}" in
        1) confirm_and_run "models" reset_models ;;
        2) confirm_and_run "data & experiments" reset_data ;;
        3) confirm_and_run "KNOWLEDGE BASE" reset_pkb ;;
        4) confirm_and_run "plugins" reset_plugins ;;
        5) confirm_and_run "environment" reset_env ;;
        6) confirm_and_run "FULL WIPE" full_wipe ;;
        7) confirm_and_run "DESTROY LAB" destroy_lab ;;
        8) stop_services ;;
        0|"") echo "  Cancelled."; exit 0 ;;
        *) error "Invalid choice."; exit 1 ;;
    esac
}

confirm_and_run() {
    local label="$1"
    local fn="$2"
    if [[ "$AUTO_CONFIRM" == "true" ]]; then
        "$fn"
        return
    fi

    echo ""
    read -rp "  Confirm reset ${label}? [y/N] " yn
    case "${yn}" in
        [Yy]*) "$fn" ;;
        *)     echo "  Cancelled."; exit 0 ;;
    esac
}

# ── Entry point ──────────────────────────────────────────────────────
# --world/--all only matter to `stop` mode (ARCHITECTURE.md §4.2); a
# plain for-loop can't consume "--world <slug>" as two tokens, so this is
# a while loop now (was a for loop before this WP).
MODE=""
STOP_WORLD=""
STOP_ALL="false"
while [[ $# -gt 0 ]]; do
    case "$1" in
        --yes|-y) AUTO_CONFIRM="true"; shift ;;
        --all)    STOP_ALL="true"; shift ;;
        # m9: a plain `shift 2` errors (aborting under `set -e`) when
        # `--world` is the final token and there's no $2 to shift past.
        --world)  STOP_WORLD="${2:-}"; shift; [[ $# -gt 0 ]] && shift ;;
        --world=*) STOP_WORLD="${1#--world=}"; shift ;;
        *)
            if [[ -z "$MODE" ]]; then
                MODE="$1"
            fi
            shift
            ;;
    esac
done

# stop_all_instances — every LIVE World instance, via stop_instance()
# (registry-verified kill). No-op if instances.sh isn't sourced (sandboxed
# test copies of this file alone).
stop_all_instances() {
    command -v inst_list_slugs >/dev/null 2>&1 || return 0
    local s
    while IFS= read -r s; do
        [[ -n "$s" ]] || continue
        inst_alive "$s" && stop_instance "$s"
    done < <(inst_list_slugs)
}

case "${MODE:-}" in
    models)  confirm_and_run "models" reset_models ;;
    data)    confirm_and_run "data & experiments" reset_data ;;
    pkb)       confirm_and_run "KNOWLEDGE BASE" reset_pkb ;;
    pkb-seeds) confirm_and_run "starter pack seeds" reset_pkb_seeds ;;
    program)   confirm_and_run "research recipe (program.md + train.py)" reset_program ;;
    skills)    confirm_and_run "installed skill packs" reset_skills ;;
    plugins) confirm_and_run "plugins" reset_plugins ;;
    env)     confirm_and_run "environment" reset_env ;;
    full)    confirm_and_run "FULL WIPE" full_wipe ;;
    destroy) confirm_and_run "DESTROY LAB" destroy_lab ;;
    stop)
        # Instance-aware dispatch (ARCHITECTURE.md §4.2). Degrades to plain
        # stop_services() when scripts/lib/instances.sh isn't sourced
        # (sandboxed single-file test copies of reset.sh).
        if [[ -n "$STOP_WORLD" ]]; then
            # REVIEW.md M5: STOP_WORLD is argv, taken verbatim into
            # inst_registry_file()'s path join with no jail — unlike
            # start.sh's stage 1 (which jails --world before ever touching
            # disk), `stop --world ../../../../tmp/x` would read (and, via
            # stop_instance's `rm -f`, DELETE) an arbitrary *.json file
            # outside lab/instances/registry.d/. Jail it the same way
            # start.sh does before it ever reaches a filesystem call.
            if command -v inst_valid_slug >/dev/null 2>&1 && ! inst_valid_slug "$STOP_WORLD"; then
                error "invalid World slug: ${STOP_WORLD}"
                exit 2
            fi
            if command -v inst_read_record >/dev/null 2>&1; then
                stop_instance "$STOP_WORLD"
            else
                error "instance support unavailable in this context"; exit 1
            fi
        elif [[ "$STOP_ALL" == "true" ]]; then
            stop_all_instances
            stop_services
        elif command -v inst_list_slugs >/dev/null 2>&1; then
            LIVE_SLUGS=()
            while IFS= read -r s; do
                [[ -n "$s" ]] && inst_alive "$s" && LIVE_SLUGS+=("$s")
            done < <(inst_list_slugs)
            if (( ${#LIVE_SLUGS[@]} == 0 )); then
                stop_services
            elif (( ${#LIVE_SLUGS[@]} == 1 )); then
                info "Stopping '${LIVE_SLUGS[0]}' (the only running World instance)..."
                stop_instance "${LIVE_SLUGS[0]}"
                stop_services
            else
                error "Multiple World instances are running — specify which to stop:"
                for s in "${LIVE_SLUGS[@]}"; do
                    echo "    ./arailctl stop --world ${s}"
                done
                echo "    ./arailctl stop --all"
                exit 1
            fi
        else
            stop_services
        fi
        ;;
    -h|--help) usage; exit 0 ;;
    "")      interactive_menu ;;
    *)       usage; exit 1 ;;
esac

echo ""
info "Done."
