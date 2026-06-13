#!/usr/bin/env bash
# Regression driver for the env-quoting audit (world-mount sprint).
#
# Values written to shell-sourced config files (.env, lab.conf) MUST survive
# `set -a; source <file>` without breaking parsing or executing embedded
# command/parameter expansions. This exercises the REAL helpers extracted from
# scripts/setup.sh and scripts/blueprint.sh against hostile input.
#
# Exits 0 and prints "OK:" on success; non-zero with "FAIL:" otherwise.
set -uo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
SETUP="$REPO/scripts/setup.sh"
BLUEPRINT="$REPO/scripts/blueprint.sh"
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

echo "OK: shell-sourced config files (.env, lab.conf) are injection-safe"
