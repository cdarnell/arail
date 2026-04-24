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
# Both tiers now declare airllm, so we always re-run pip install to make
# sure the deep backend is present.
pip install -q -e ".[${TIER}]" || die "pip install failed for tier ${TIER}"

# Persist tier + tier-sized AIRLLM_MODEL default to .env. Reads the
# canonical model names from pyproject.toml so this stays in lockstep
# with [tool.arail.models].
python3 - "$TIER" <<'PY'
import pathlib, sys
try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

tier = sys.argv[1]
data = tomllib.loads(pathlib.Path("pyproject.toml").read_text())
models = data.get("tool", {}).get("arail", {}).get("models", {})
tier_model_key = f"airllm_{tier}"
airllm_model = models.get(tier_model_key) or models.get("airllm", "")

p = pathlib.Path(".env")
lines = p.read_text().splitlines() if p.exists() else []

def upsert(out, key, value):
    seen = False
    new = []
    for line in out:
        if line.lstrip("# ").startswith(f"{key}="):
            new.append(f"{key}={value}")
            seen = True
        else:
            new.append(line)
    if not seen:
        if new and new[-1] != "":
            new.append("")
        new.append(f"{key}={value}")
    return new

lines = upsert(lines, "LAB_TIER", tier)
if airllm_model:
    lines = upsert(lines, "AIRLLM_MODEL", airllm_model)
p.write_text("\n".join(lines) + "\n")
print(f"LAB_TIER={tier}")
if airllm_model:
    print(f"AIRLLM_MODEL={airllm_model}")
PY

info "Tier is now ${BOLD}${TIER}${RESET}. Restart the lab to apply:"
echo ""
echo "    ./arail restart"
echo ""
