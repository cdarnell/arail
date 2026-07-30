#!/usr/bin/env bash
# Regression driver for the env-quoting audit (world-mount sprint), extended
# per sprints/2026-07-29-elite-cli/ARCHITECTURE.md F4 / REVIEW.md m7 to also
# cover scripts/install.sh and scripts/lib/services.sh's callers.
#
# Two distinct hazards, both under this one file's "shell source safety"
# banner:
#   - Values written to shell-sourced config files (.env, lab.conf) MUST
#     survive `set -a; source <file>` without breaking parsing or executing
#     embedded command/parameter expansions (#5, #6 below — the original
#     scope, unchanged).
#   - `source <missing-file>` MUST NOT abort a non-interactive bash 3.2
#     shell under `set -euo pipefail`, even with no `|| true` (F4; #7, #8
#     below — new).
#
# This exercises the REAL guard lines/helpers extracted verbatim from
# scripts/setup.sh, scripts/blueprint.sh, scripts/install.sh, and
# scripts/start.sh against hostile input / a missing target — never a
# reimplementation of the code under test.
#
# Exits 0 and prints "OK:" on success; non-zero with "FAIL:" otherwise.
set -uo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
SETUP="$REPO/scripts/setup.sh"
BLUEPRINT="$REPO/scripts/blueprint.sh"
INSTALL="$REPO/scripts/install.sh"
START="$REPO/scripts/start.sh"
fail() { echo "FAIL: $1" >&2; exit 1; }

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
cd "$work" || fail "cannot cd to workdir"

# ---- #5: lab.conf IDE_PASSWORD (shell-sourced by start.sh/status.sh) --------
sed -n '/^_set_env_var()/,/^}/p' "$SETUP" >  fns.sh
sed -n '/^_get_env_var()/,/^}/p' "$SETUP" >> fns.sh
# shellcheck disable=SC1091
source fns.sh
H='p @ss $(touch PWNED) `touch PWNED2` "q" ; echo bad'
_set_env_var IDE_PASSWORD "$H" lab.conf
( set -a; source lab.conf; set +a; [ "$IDE_PASSWORD" = "$H" ] ) \
    || fail "lab.conf password did not round-trip through source"
{ [ -e PWNED ] || [ -e PWNED2 ]; } && fail "sourcing lab.conf executed an embedded command"
got="$(_get_env_var IDE_PASSWORD lab.conf)"
[ "$got" = "$H" ] || fail "lab.conf password read round-trip mismatch: [$got]"

# ---- #6: blueprint per-instance .env (shell-sourced) -----------------------
mkdir -p inst
cat > inst/blueprint.toml <<'TOML'
id = "x"
label = "My $(touch PWNED3) Lab"
description = "has \"quotes\", $HOME, and `date`"
tier = "min"
goal_prompt = "Study A; rm -rf / & echo $PATH"
TOML
sed -n "/python3 - \"\$idir\" \"\$instance\" \"\$port_base\" <<'PY'/,/^PY\$/p" "$BLUEPRINT" \
    | sed '1d;$d' > render.py
python3 render.py "$work/inst" inst 9000 || fail "blueprint render failed"
( set -a; source inst/.env; set +a; [ "$LAB_INTENT" = 'Study A; rm -rf / & echo $PATH' ] ) \
    || fail "instance .env LAB_INTENT did not round-trip through source"
{ [ -e PWNED3 ] || [ -e inst/PWNED3 ]; } && fail "sourcing instance .env executed an embedded command"

# ---- #7: install.sh's guarded sources (.env, scripts/lib/instances.sh)
#          never abort under `set -euo pipefail` when the target file is
#          absent (F4, extended per REVIEW.md m7) ---------------------------
mkdir -p case7
guard_line_inst="$(grep -F '[[ -f "$REPO_ROOT/scripts/lib/instances.sh" ]] && source "$REPO_ROOT/scripts/lib/instances.sh"' "$INSTALL")" \
    || fail "install.sh's instances.sh guard line not found verbatim — extraction target moved, update this driver"
guard_line_env="$(grep -F '[[ -f .env ]] && set -a && source .env && set +a' "$INSTALL")" \
    || fail "install.sh's .env guard line not found verbatim — extraction target moved, update this driver"
out7="$(cd case7 && REPO_ROOT="$work/case7" bash -c "
set -euo pipefail
REPO_ROOT=\"\$1\"
${guard_line_inst}
${guard_line_env}
echo REACHED_END
" _ "$work/case7" 2>&1)"
rc7=$?
[ "$rc7" -eq 0 ] || fail "install.sh's guarded sources aborted under set -euo pipefail with BOTH targets absent (F4): $out7"
echo "$out7" | grep -q REACHED_END \
    || fail "install.sh's guarded-source pattern did not reach the end of the script: $out7"

# ---- #8: a scripts/lib/services.sh caller's guarded source never aborts
#          under `set -euo pipefail` when services.sh itself is absent
#          (F4, extended per REVIEW.md m7) -----------------------------------
mkdir -p case8
guard_line_svc="$(grep -F '[[ -f "$REPO_ROOT/scripts/lib/services.sh" ]] && source "$REPO_ROOT/scripts/lib/services.sh"' "$START")" \
    || fail "start.sh's services.sh guard line not found verbatim — extraction target moved, update this driver"
out8="$(cd case8 && bash -c "
set -euo pipefail
REPO_ROOT=\"\$1\"
${guard_line_svc}
echo REACHED_END
" _ "$work/case8" 2>&1)"
rc8=$?
[ "$rc8" -eq 0 ] || fail "a services.sh caller's guarded source aborted under set -euo pipefail with services.sh absent (F4): $out8"
echo "$out8" | grep -q REACHED_END \
    || fail "the services.sh guard pattern did not reach the end of the script: $out8"

echo "OK: shell-sourced config files (.env, lab.conf) are injection-safe, and install.sh/services.sh callers' guarded sources never abort on a missing file (F4)"
