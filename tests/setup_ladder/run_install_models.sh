#!/usr/bin/env bash
# QA harness: exercise install_models() from scripts/setup.sh in isolation
# with every network/ollama/curl/sha256sum call stubbed.
#
# OOM-SAFETY: this NEVER runs real ollama, curl, or downloads. All external
# commands are PATH shims under $STUB_BIN. The harness sources setup.sh with
# its final `main "$@"` line stripped so nothing actually executes at source.
#
# Usage:
#   STUB_BIN=<dir-with-stubs> run_install_models.sh
# The caller sets up $STUB_BIN with stub `ollama`/`curl`/`sha256sum` and any
# ARAIL_* env vars, then runs this. Stdout/stderr is the install_models log;
# exit code is install_models' return (we force a clean 0 unless it aborts).

set -uo pipefail

REPO_ROOT="${REPO_ROOT:?REPO_ROOT must be set}"
STUB_BIN="${STUB_BIN:?STUB_BIN must be set}"

# Prepend stubs so they win over any real binaries.
export PATH="${STUB_BIN}:${PATH}"

# Make a trimmed copy of setup.sh without the trailing `main "$@"` invocation.
SRC="${REPO_ROOT}/scripts/setup.sh"
TRIMMED="$(mktemp "${TMPDIR:-/tmp}/setup_trimmed.XXXXXX.sh")"
trap 'rm -f "$TRIMMED"' EXIT

# Strip the standalone `main "$@"` call (last executable line).
grep -v -E '^main "\$@"$' "$SRC" > "$TRIMMED"

# setup.sh has `set -euo pipefail`; we relax -e here so a non-zero from a
# stubbed branch doesn't kill the harness before the ai-eng ladder returns.
# shellcheck disable=SC1090
source "$TRIMMED"
set +e

# The ai-eng self-hosted fetch ladder lives in the back half of
# install_services(). To exercise ONLY that ladder (not ttyd/tmux/node
# bootstrapping), we force the Ollama branch and short-circuit the
# pre-ai-eng system-package work:
#   - PLATFORM=test so the package-manager cases fall through to no-ops
#   - ARAIL_ENABLE_OLLAMA=1 so the Ollama block runs on any platform
#   - step()/ensure_node()/ollama_default_enabled() neutered
#   - ttyd/tmux/agent-browser are stubbed-present in $STUB_BIN
export PLATFORM="${PLATFORM:-test}"
export ARAIL_ENABLE_OLLAMA=1
step() { :; }
ensure_node() { return 1; }            # skip npm/agent-browser bootstrap
ollama_default_enabled() { return 0; } # don't skip Ollama on this "platform"

install_services
echo "__INSTALL_MODELS_EXIT__=$?"
