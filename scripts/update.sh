#!/usr/bin/env bash
# =============================================================================
# Arail — Component Update System
#
# Reads components.json, checks for updates, shows a summary, and applies
# with user confirmation. Also provides `--version-only` for quick version
# listing.
#
# Usage:
#   ./arailctl update                  # check & apply updates
#   ./arailctl update --check          # dry-run: just check, no changes
#   ./arailctl update --yes            # skip confirmation
#   ./arailctl update --component ttyd # update a single component
#   ./arailctl version                 # show installed versions
# =============================================================================
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# shellcheck disable=SC1091
[[ -f .env ]] && set -a && source .env && set +a

# ── ANSI color gating (ARCHITECTURE.md §13 "ANSI leaks into non-tty
# output", F25) — see arailctl's identical block for the full rationale.
# $'...' (ANSI-C quoting) so the variables hold real ESC bytes.
if [[ -t 1 && "${ARAIL_COLOR:-auto}" != "never" && -z "${NO_COLOR:-}" ]] || [[ "${ARAIL_COLOR:-auto}" == "always" ]]; then
    BOLD=$'\033[1m'; GREEN=$'\033[0;32m'; CYAN=$'\033[0;36m'
    YELLOW=$'\033[0;33m'; RED=$'\033[0;31m'; DIM=$'\033[2m'; RESET=$'\033[0m'
else
    BOLD=""; GREEN=""; CYAN=""
    YELLOW=""; RED=""; DIM=""; RESET=""
fi

LAB_NAME="${LAB_NAME:-Arail}"
LAB_SHORT_NAME="${LAB_SHORT_NAME:-arail}"

info()  { echo -e "${GREEN}[${LAB_SHORT_NAME}]${RESET} $*"; }
warn()  { echo -e "${YELLOW}[${LAB_SHORT_NAME}]${RESET} $*"; }
err()   { echo -e "${RED}[${LAB_SHORT_NAME}]${RESET} $*" >&2; }

MANIFEST="$REPO_ROOT/components.json"

# ── Platform detection ───────────────────────────────────────────────
detect_platform() {
    case "$(uname -s)" in
        Darwin) PLATFORM="macos" ;;
        Linux)
            if [[ -f /etc/gentoo-release ]]; then
                PLATFORM="gentoo"
            elif grep -qi microsoft /proc/version 2>/dev/null; then
                PLATFORM="wsl"
            else
                PLATFORM="linux"
            fi
            ;;
        *) PLATFORM="unknown" ;;
    esac
}

# ── Parse components.json with Python ────────────────────────────────
# Returns one line per component: name|type|optional|version_cmd|...
read_components() {
    python3 - "$MANIFEST" "$PLATFORM" <<'PY'
import json, sys
SEP = "\x1f"  # unit separator — safe delimiter that won't appear in commands
manifest = json.load(open(sys.argv[1]))
platform = sys.argv[2]
for c in manifest["components"]:
    platforms = c.get("platforms", [])
    if platforms and platform not in platforms:
        continue
    update_cmd = c.get("update_cmd", "")
    if isinstance(update_cmd, dict):
        update_cmd = update_cmd.get(platform, "")
    check_cmd = c.get("check_cmd") or ""
    post_cmd = c.get("post_update_cmd") or ""
    desc = c.get("description", "")
    optional = "1" if c.get("optional") else "0"
    version_cmd = c.get("version_cmd") or ""
    print(SEP.join([c["name"], c["type"], optional, version_cmd, check_cmd, update_cmd, post_cmd, desc]))
PY
}

# ── Read breaking changes (only if the available version crosses the threshold) ──
check_breaking_changes() {
    local component="$1"
    local available_version="$2"
    python3 - "$MANIFEST" "$component" "$available_version" <<'PY'
import json, sys, re

manifest = json.load(open(sys.argv[1]))
name = sys.argv[2]
available = sys.argv[3] if len(sys.argv) > 3 else ""

def version_tuple(v):
    """Extract numeric version parts from a string like 'v1.8.4' or '1.0.0'."""
    nums = re.findall(r'\d+', v)
    return tuple(int(n) for n in nums) if nums else (0,)

def matches_range(available_ver, range_str):
    """Check if available_ver crosses into the breaking range.
    e.g. range 'v2' means major version 2+; 'fastapi>=1.0.0' means 1.0+."""
    range_clean = re.sub(r'^[a-zA-Z_-]*(>=?)?', '', range_str)
    avail_t = version_tuple(available_ver)
    range_t = version_tuple(range_clean)
    if not range_t or not avail_t:
        return False
    return avail_t >= range_t

def check_pip_breaking(range_str):
    """For pip components, check if the specific outdated package version
    crosses the breaking range. e.g. 'fastapi>=1.0.0' checks if the
    available fastapi version is >= 1.0.0."""
    import subprocess
    # Extract package name from range (e.g. 'fastapi>=1.0.0' → 'fastapi')
    pkg = re.match(r'^([a-zA-Z_-]+)', range_str)
    if not pkg:
        return False
    pkg_name = pkg.group(1).lower().replace('-', '_')
    try:
        r = subprocess.run(['.venv/bin/pip', 'list', '--outdated', '--format=json'],
                           capture_output=True, text=True, timeout=15)
        import json as j
        for p in j.loads(r.stdout):
            if p['name'].lower().replace('-', '_') == pkg_name:
                return matches_range(p['latest_version'], range_str)
    except Exception:
        pass
    return False

for c in manifest["components"]:
    if c["name"] == name:
        comp_type = c.get("type", "")
        for bc in c.get("breaking_changes", []):
            vr = bc.get("version_range", "")
            if comp_type == "pip":
                # For pip, check the specific package version
                if vr and not check_pip_breaking(vr):
                    continue
            elif available and vr:
                if not matches_range(available, vr):
                    continue
            elif not vr:
                continue  # no range defined — skip
            sev = bc.get("severity", "info")
            print(f"{sev}|{vr}|{bc.get('note', '')}")
        break
PY
}

# ── Get current version ──────────────────────────────────────────────
get_version() {
    local version_cmd="$1"
    if [[ -z "$version_cmd" ]]; then
        echo "—"
        return
    fi
    local ver
    ver=$(eval "$version_cmd" 2>/dev/null | head -1) || ver="not found"
    echo "${ver:-not found}"
}

# ═════════════════════════════════════════════════════════════════════
#  VERSION MODE  (./arailctl version)
# ═════════════════════════════════════════════════════════════════════
show_versions() {
    detect_platform
    echo ""
    echo -e "${BOLD}${LAB_NAME} — Component Versions${RESET}"
    echo -e "${DIM}Platform: ${PLATFORM}  |  Mode: ${ARAIL_MODE:-airgapped}${RESET}"
    echo ""
    printf "  ${BOLD}%-22s %-24s %-8s %s${RESET}\n" "Component" "Version" "Type" "Source"
    echo "  ──────────────────── ──────────────────────── ──────── ────────────────────"

    while IFS=$'\x1f' read -r name type optional version_cmd check_cmd update_cmd post_cmd desc; do
        # Skip optional components that aren't installed
        if [[ "$optional" == "1" ]]; then
            local bin_name="${name}"
            if ! command -v "$bin_name" &>/dev/null && [[ "$type" != "pip" && "$type" != "docker" && "$type" != "git" ]]; then
                printf "  ${DIM}%-22s %-24s %-8s (not installed)${RESET}\n" "$name" "—" "$type"
                continue
            fi
        fi

        local ver
        ver=$(get_version "$version_cmd")

        # Get source URL from manifest
        local source_url
        source_url=$(python3 -c "
import json
m = json.load(open('$MANIFEST'))
for c in m['components']:
    if c['name'] == '$name':
        print(c.get('source_url') or c.get('compose_file') or '—')
        break
" 2>/dev/null || echo "—")

        printf "  %-22s %-24s %-8s %s\n" "$name" "$ver" "$type" "$source_url"
    done < <(read_components)

    echo ""
}

# ═════════════════════════════════════════════════════════════════════
#  UPDATE MODE  (./arailctl update)
# ═════════════════════════════════════════════════════════════════════
run_update() {
    local dry_run=false
    local auto_yes=false
    local force=false
    local target_component=""
    # ARCHITECTURE.md §14.3 (sprints/2026-07-29-elite-cli, WP7): new,
    # additive argv mode — `update.sh --apply --non-interactive` is how
    # install.sh's components phase drives this file. The pre-existing
    # interactive path (bare `update`, `update --component X`) is
    # UNTOUCHED by this flag's presence/absence.
    local non_interactive=false

    # Parse flags
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --check|--dry-run)  dry_run=true ;;
            --yes|-y)           auto_yes=true ;;
            --apply)            dry_run=false ;;
            --non-interactive)  auto_yes=true; non_interactive=true ;;
            --force)            force=true ;;
            --component)        shift; target_component="${1:-}" ;;
            *)                  warn "Unknown flag: $1" ;;
        esac
        shift
    done

    detect_platform
    local mode
    if [[ "$non_interactive" == "true" ]]; then
        # install.sh's own preflight already resolves LAB_MODE (with
        # ARAIL_MODE as the legacy fallback — the canonical precedence
        # every other script in this repo uses). The pre-existing
        # interactive path below is left exactly as it was (ARAIL_MODE
        # only) — not touched, since this sprint's mandate is a NEW argv
        # mode, not a behavior change to the muscle-memory
        # `update --component X` path.
        mode="${LAB_MODE:-${ARAIL_MODE:-airgapped}}"
    else
        mode="${ARAIL_MODE:-airgapped}"
    fi

    if [[ "$non_interactive" != "true" ]]; then
        echo ""
        echo -e "${BOLD}${LAB_NAME} — Update Check${RESET}"
        echo -e "${DIM}Platform: ${PLATFORM}  |  Mode: ${mode}${RESET}"
        echo ""
    fi

    if [[ "$mode" == "airgapped" ]]; then
        warn "Lab is airgapped — skipping remote update checks."
        warn "Switch to Hybrid mode or use --force to update from local cache."
        if [[ "$force" != "true" ]]; then
            echo ""
            # Previously a bare `return` (implicit 0) regardless of mode —
            # §12.1's exit-code doctrine treats "refused, did nothing" as
            # degraded (3), not success. Applies to BOTH the interactive
            # and non-interactive paths: nobody currently checks this
            # exit code (§6.4's own "previously exited 0 always" note),
            # so there is nothing to silently break, and install.sh's own
            # airgap doctrine (a hard constraint of this sprint) depends
            # on this phase actually reporting "refused" rather than "ok".
            return 3
        fi
    fi

    # §14.3: "1 (manifest unreadable)" — only meaningfully distinguishable
    # from "0 updates available" when this run actually needed the
    # manifest, i.e. the non-interactive contract. Gated to that mode so
    # the pre-existing interactive path's behavior on a missing manifest
    # (today: the while-loop below silently sees nothing) is unchanged.
    if [[ "$non_interactive" == "true" && ! -f "$MANIFEST" ]]; then
        err "components manifest not found: $MANIFEST"
        return 1
    fi

    local updates_available=0
    local update_list=""
    local apply_failed_count=0

    while IFS=$'\x1f' read -r name type optional version_cmd check_cmd update_cmd post_cmd desc; do
        # Filter to target component if specified
        if [[ -n "$target_component" && "$name" != "$target_component" ]]; then
            continue
        fi

        # Skip optional components that aren't installed
        if [[ "$optional" == "1" && "$type" == "system" ]]; then
            if ! command -v "$name" &>/dev/null; then
                continue
            fi
        fi
        if [[ "$optional" == "1" && "$type" == "npm" ]]; then
            if ! command -v "$name" &>/dev/null; then
                continue
            fi
        fi

        local ver
        ver=$(get_version "$version_cmd")

        # Check for updates — capture the remote/available version
        local status="current"
        local available=""
        if [[ -n "$check_cmd" && "$mode" != "airgapped" ]]; then
            local check_output
            check_output=$(eval "$check_cmd" 2>&1) || true
            if [[ -n "$check_output" && "$check_output" != *"up to date"* && "$check_output" != *"not found"* ]]; then
                status="update-available"
                available="$check_output"
                updates_available=$((updates_available + 1))
                update_list="${update_list}${name}$(printf '\x1f')${type}$(printf '\x1f')${ver}$(printf '\x1f')${update_cmd}$(printf '\x1f')${post_cmd}$(printf '\x1f')${desc}$(printf '\x1f')${available}\n"
            fi
        fi

        if [[ "$status" == "update-available" ]]; then
            # Show current → available for core components
            local avail_short
            avail_short=$(echo "$available" | head -1 | cut -c1-60)
            echo -e "  ${YELLOW}↑${RESET} ${BOLD}${name}${RESET} (${type})"
            echo -e "    current:   ${DIM}${ver}${RESET}"
            echo -e "    available: ${CYAN}${avail_short}${RESET}"
        else
            echo -e "  ${GREEN}✓${RESET} ${name} (${type}) — ${DIM}${ver}${RESET}"
        fi

    done < <(read_components)

    echo ""

    if [[ $updates_available -eq 0 ]]; then
        info "All components are up to date."
        return 0
    fi

    info "${updates_available} update(s) available."

    if [[ "$dry_run" == "true" ]]; then
        info "Dry run — no changes applied."
        # §6.4 (sprints/2026-07-29-elite-cli): `update --check` previously
        # exited 0 always — an intentional, documented behavior change.
        # `install --check` (§5.1) needs exactly this signal to report its
        # own "pending changes" degraded verdict; applies to the
        # interactive path too (same rationale as the airgap-refusal
        # return above — nobody currently depends on this being 0).
        return 3
    fi

    # Check for breaking changes (only if the available version actually crosses the threshold)
    local has_major=false
    while IFS=$'\x1f' read -r name type ver update_cmd post_cmd desc avail_ver; do
        [[ -z "$name" ]] && continue
        # For pip components, extract the specific package version from the check output
        # For other types, clean the available version string
        local avail_clean=""
        if [[ "$type" == "pip" ]]; then
            # pip available is like "13 outdated: anthropic, fastapi, ..."
            # We need to check each breaking change's package specifically
            # Pass empty string — the Python check will skip if no clean version
            avail_clean=""
        else
            avail_clean=$(echo "$avail_ver" | head -1 | grep -oE '[0-9]+\.[0-9]+[0-9.]*' | head -1)
        fi
        while IFS='|' read -r severity range note; do
            [[ -z "$severity" ]] && continue
            if [[ "$severity" == "major" ]]; then
                echo -e "  ${RED}⚠ BREAKING${RESET} ${BOLD}${name}${RESET}: ${note}"
                has_major=true
            elif [[ "$severity" == "minor" ]]; then
                echo -e "  ${YELLOW}⚠${RESET} ${name}: ${note}"
            fi
        done < <(check_breaking_changes "$name" "$avail_clean")
    done < <(echo -e "$update_list")

    if [[ "$has_major" == "true" && "$force" != "true" ]]; then
        echo ""
        warn "Major breaking changes detected. Use --force to apply anyway."
        return 1
    fi

    # Confirmation
    if [[ "$auto_yes" != "true" ]]; then
        echo ""
        read -rp "  Apply ${updates_available} update(s)? [y/N] " confirm
        if [[ ! "$confirm" =~ ^[Yy] ]]; then
            info "Cancelled."
            return
        fi
    fi

    echo ""
    info "Applying updates…"

    # Apply updates in order: git → pip → npm/system → docker
    local order=("git" "pip" "npm" "system" "docker")
    for target_type in "${order[@]}"; do
        while IFS=$'\x1f' read -r name type ver update_cmd post_cmd desc avail_ver; do
            [[ -z "$name" || "$type" != "$target_type" ]] && continue
            info "Updating ${name} (${type})…"

            if eval "$update_cmd" 2>&1 | tail -5; then
                info "${name} updated."
            else
                warn "${name} update failed — continuing."
                apply_failed_count=$((apply_failed_count + 1))
                continue
            fi

            if [[ -n "$post_cmd" ]]; then
                info "Running post-update for ${name}…"
                eval "$post_cmd" 2>&1 | tail -3 || warn "Post-update for ${name} had warnings."
            fi
        done < <(echo -e "$update_list")
    done

    # Write updated versions back to manifest
    info "Refreshing component versions in components.json…"
    python3 - "$MANIFEST" <<'PY'
import json, subprocess, sys
path = sys.argv[1]
manifest = json.load(open(path))
for c in manifest["components"]:
    cmd = c.get("version_cmd")
    if not cmd:
        continue
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
        ver = result.stdout.strip().split("\n")[0] if result.returncode == 0 else None
        if ver and len(ver) < 100:
            c["current_version"] = ver
    except Exception:
        pass
with open(path, "w") as f:
    json.dump(manifest, f, indent=2)
    f.write("\n")
PY

    echo ""
    info "Update complete. Run ${BOLD}./arailctl restart${RESET} to pick up changes."
    echo ""

    # §14.3's apply-mode exit contract — gated to the new argv mode only
    # (the pre-existing interactive path falls through exactly as before:
    # whatever the last command above returned, historically always 0).
    if [[ "$non_interactive" == "true" ]]; then
        if (( apply_failed_count > 0 )); then
            return 3
        fi
        return 0
    fi
}

# ═════════════════════════════════════════════════════════════════════
#  Entrypoint
# ═════════════════════════════════════════════════════════════════════
if [[ "${1:-}" == "--version-only" ]]; then
    show_versions
else
    run_update "$@"
fi
