#!/usr/bin/env bash
# build-aerollm.sh — build the aerollm_api PyO3 wheel from the LOCAL sibling
# repo and install it into the active Python environment.
#
# AeroLLM is ARAIL's 2nd (deep) inference. We deliberately build from the
# local sibling checkout ($ARAIL_AEROLLM_REPO, default ~/ProJects/aerollm)
# rather than pip — the repo is actively improving, and building from source
# means your in-progress aerollm changes flow straight into the lab. Re-run
# this after editing aerollm (`./arailctl deep rebuild`).
#
# Modes:
#   build  (default)  cargo build + copy the extension into site-packages
#   status            report whether aerollm_api imports + the resolved paths
#
# IMPORTANT: we use `cargo build`, NOT `maturin develop`. maturin perturbs the
# cargo fingerprint (PYO3_ENVIRONMENT_SIGNATURE / CARGO_ENCODED_RUSTFLAGS),
# which forces a fresh Metal kernel compile that fails on macOS arm64 due to
# mlx-sys program-scope device variables (Metal Toolchain cryptexd v32023.883+).
set -euo pipefail

MODE="${1:-build}"

# ── minimal logging (no dep on setup.sh's helpers) ───────────────────────────
if [[ -t 1 && -z "${NO_COLOR:-}" ]]; then
    BOLD=$'\033[1m'; RED=$'\033[31m'; GRN=$'\033[32m'; YLW=$'\033[33m'; RST=$'\033[0m'
else
    BOLD=""; RED=""; GRN=""; YLW=""; RST=""
fi
info() { printf '%s\n' "${GRN}•${RST} $*"; }
warn() { printf '%s\n' "${YLW}!${RST} $*" >&2; }
err()  { printf '%s\n' "${RED}✗${RST} $*" >&2; }

AEROLLM_REPO="${ARAIL_AEROLLM_REPO:-$HOME/ProJects/aerollm}"
CRATE_DIR="$AEROLLM_REPO/crates/aerollm-api"
PY="${PYTHON:-python3}"

# Resolve the platform extension-module dir (works in venvs and base envs).
site_dir() { "$PY" -c "import sysconfig; print(sysconfig.get_path('platlib'))"; }
import_ok() { "$PY" -c "import aerollm_api" >/dev/null 2>&1; }

clone_hint() {
    err "No aerollm sibling repo at ${BOLD}${AEROLLM_REPO}${RST}."
    warn "AeroLLM is built from the local sibling repo (not pip). Either:"
    warn "  1) clone it next to arail:"
    warn "       git clone https://github.com/cdarnell/aerollm \"${AEROLLM_REPO}\""
    warn "  2) or point ARAIL_AEROLLM_REPO at your checkout, then re-run."
}

if [[ "$MODE" == "status" ]]; then
    info "AeroLLM (2nd inference) status"
    printf '    repo:         %s\n' "$AEROLLM_REPO"
    if [[ -d "$CRATE_DIR" ]]; then
        printf '    crate:        %s (found)\n' "$CRATE_DIR"
    else
        printf '    crate:        %s %s(missing)%s\n' "$CRATE_DIR" "$RED" "$RST"
    fi
    printf '    site-packages:%s\n' " $(site_dir 2>/dev/null || echo '?')"
    if import_ok; then
        printf '    aerollm_api:  %simportable ✓%s\n' "$GRN" "$RST"
    else
        printf '    aerollm_api:  %snot importable — run: ./arailctl deep rebuild%s\n' "$YLW" "$RST"
    fi
    printf '    bg pressure:  %s\n' "${ARAIL_AEROLLM_BG_PRESSURE_PCT:-0.60 (default)}"
    exit 0
fi

# ── build mode ───────────────────────────────────────────────────────────────
if [[ ! -d "$CRATE_DIR" ]]; then
    clone_hint
    exit 1
fi
if ! command -v cargo >/dev/null 2>&1; then
    err "cargo not found — install the Rust toolchain (https://rustup.rs) and retry."
    exit 1
fi

info "Building aerollm_api from ${BOLD}${AEROLLM_REPO}${RST} (cargo --release)…"
( cd "$AEROLLM_REPO" && cargo build --release -p aerollm-api --features extension-module )

# Locate the freshly built extension (.dylib on macOS, .so on Linux).
BUILT=""
for cand in \
    "$AEROLLM_REPO/target/release/libaerollm_api.dylib" \
    "$AEROLLM_REPO/target/release/libaerollm_api.so"; do
    [[ -f "$cand" ]] && BUILT="$cand" && break
done
if [[ -z "$BUILT" ]]; then
    err "cargo build succeeded but no libaerollm_api.{dylib,so} under target/release."
    exit 1
fi

DEST_DIR="$(site_dir)"
DEST="$DEST_DIR/aerollm_api.abi3.so"
info "Installing → ${DEST}"
cp -f "$BUILT" "$DEST"

if import_ok; then
    info "${GRN}AeroLLM ready${RST} — it's the deep-mode default 2nd inference."
else
    err "Copied the extension but \`import aerollm_api\` still fails."
    warn "Check that $PY is the same interpreter ARAIL runs (venv mismatch?)."
    exit 1
fi
