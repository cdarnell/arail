#!/usr/bin/env bash
# =============================================================================
# upgrade.sh — switch install tier (min / max) without re-running setup.
#
# Usage:
#   ./arail upgrade max
#   ./arail upgrade min   (downgrade — does not uninstall packages, just
#                          hides the extra tabs until you upgrade again)
#
# The 'med' tier from the earlier three-tier blueprint is retired. Passing
# it rolls forward to 'max' with a warning.
# =============================================================================
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

GREEN="\033[0;32m"; YELLOW="\033[0;33m"; RED="\033[0;31m"; BOLD="\033[1m"; RESET="\033[0m"
info()  { echo -e "${GREEN}[arail]${RESET} $*"; }
warn()  { echo -e "${YELLOW}[arail]${RESET} $*"; }
die()   { echo -e "${RED}[arail]${RESET} $*" >&2; exit 1; }

RAW="${1:-}"
case "$RAW" in
    min|max) TIER="$RAW" ;;
    med)     warn "Tier 'med' retired — rolling forward to 'max' (it owned a subset of max)."
             TIER="max" ;;
    "")      die "usage: ./arail upgrade <min|max>" ;;
    *)       die "unknown tier '$RAW' — valid: min | max" ;;
esac

[[ -d .venv ]] || die "no .venv — run ./arail setup first"
# shellcheck disable=SC1091
source .venv/bin/activate

info "Switching install tier to ${BOLD}${TIER}${RESET}…"

# pip is idempotent — already-installed packages are no-ops. For downgrades
# we intentionally do not uninstall; the tabs just hide in the nav and the
# operator can upgrade back later without re-downloading wheels.
if [[ "$TIER" != "min" ]]; then
    pip install -q -e ".[${TIER}]" || die "pip install failed for tier ${TIER}"
fi

# Persist to .env.
python3 - "$TIER" <<'PY'
import pathlib, sys
tier = sys.argv[1]
p = pathlib.Path(".env")
lines = p.read_text().splitlines() if p.exists() else []
out, replaced = [], False
for line in lines:
    if line.lstrip("# ").startswith("LAB_TIER="):
        out.append(f"LAB_TIER={tier}")
        replaced = True
    else:
        out.append(line)
if not replaced:
    if out and out[-1] != "":
        out.append("")
    out.append(f"LAB_TIER={tier}")
p.write_text("\n".join(out) + "\n")
PY

info "Tier is now ${BOLD}${TIER}${RESET}. Restart the lab to apply:"
echo ""
echo "    ./arail restart"
echo ""
