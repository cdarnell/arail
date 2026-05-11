#!/usr/bin/env bash
# =============================================================================
# disable_compare.sh — turn off the dual chat-box Compare feature.
#
# Inverse of scripts/enable_compare.sh. Flips ARAIL_COMPARE_ENABLED=0 in
# .env so the portal hides the "+ Compare" button. Idempotent.
# =============================================================================
set -euo pipefail

# REPO_ROOT honors an external override (used by tests). Without one,
# resolve from this script's location.
REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
ENV_FILE="$REPO_ROOT/.env"

GREEN="\033[0;32m"; YELLOW="\033[0;33m"; RED="\033[0;31m"; BOLD="\033[1m"; RESET="\033[0m"
info() { echo -e "${GREEN}[arail]${RESET} $*"; }
warn() { echo -e "${YELLOW}[arail]${RESET} $*"; }
die()  { echo -e "${RED}[arail]${RESET} $*" >&2; exit 1; }

[[ -f "$ENV_FILE" ]] || die "no .env at ${ENV_FILE} — run ./arailctl setup first"

python3 - "$ENV_FILE" <<'PY'
import sys
from pathlib import Path

env_path = Path(sys.argv[1])
lines = env_path.read_text().splitlines()
out, found = [], False
for ln in lines:
    if ln.lstrip("# ").startswith("ARAIL_COMPARE_ENABLED="):
        out.append("ARAIL_COMPARE_ENABLED=0")
        found = True
    else:
        out.append(ln)
if not found:
    if out and out[-1] != "":
        out.append("")
    out.append("ARAIL_COMPARE_ENABLED=0")
env_path.write_text("\n".join(out) + "\n")
PY

info "Compare mode disabled (${BOLD}ARAIL_COMPARE_ENABLED=0${RESET} in .env)."
info "Restart the portal to apply: ./arailctl restart"
