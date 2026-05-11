#!/usr/bin/env bash
# =============================================================================
# enable_compare.sh — turn on the dual chat-box Compare feature.
#
# Min ships single-pane. Run this to flip ARAIL_COMPARE_ENABLED=1 in .env
# so the portal renders the "+ Compare" button. Idempotent. The inverse
# is scripts/disable_compare.sh.
#
# Compare picks Model B from "deep backends" when one is installed (AeroLLM,
# or AirLLM on the operator-gated non-arm64 path). With no local deep
# backend, Model B falls back to cloud providers — needs LAB_MODE=hybrid
# and a configured cloud key. See docs/CERTIFIED_MODELS.md.
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
        out.append("ARAIL_COMPARE_ENABLED=1")
        found = True
    else:
        out.append(ln)
if not found:
    if out and out[-1] != "":
        out.append("")
    out.append("ARAIL_COMPARE_ENABLED=1")
env_path.write_text("\n".join(out) + "\n")
PY

info "Compare mode enabled (${BOLD}ARAIL_COMPARE_ENABLED=1${RESET} in .env)."
info "Restart the portal to apply:"
echo ""
echo "    ./arailctl restart"
echo ""
