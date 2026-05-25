#!/usr/bin/env bash
# build-aerollm.sh — install ARAIL's 2nd (deep) inference, aerollm_api.
#
# Two install channels:
#   • DEV (local sibling repo present): build from source via cargo so your
#     in-progress aerollm changes flow straight into the lab.
#   • RELEASE (no sibling): pip install the published wheel from the
#     self-hosted index (https://pypi.qukaizen.com/simple/), with public PyPI
#     as a fallback. Wheels are macOS-arm64-only; off-Mac pip reports
#     "no matching distribution" (expected — there's no Linux/CUDA build yet).
#
# Modes:
#   auto    (default)  sibling present → cargo build; else → pip from index
#   build              force a local cargo build from $ARAIL_AEROLLM_REPO
#   update             pip install --upgrade from the index (release channel)
#   status             report importability, version, resolved paths
#
# IMPORTANT: the source build uses `cargo build`, NOT `maturin develop`. maturin
# perturbs the cargo fingerprint (PYO3_ENVIRONMENT_SIGNATURE /
# CARGO_ENCODED_RUSTFLAGS), forcing a fresh Metal kernel compile that fails on
# macOS arm64 (mlx-sys program-scope device variables, Metal Toolchain cryptexd).
set -euo pipefail

MODE="${1:-auto}"

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
# Release channel — setup.sh overrides these from pyproject
# [tool.arail.package-sources] (aerollm = pin, aerollm_index = URL).
AEROLLM_INDEX_URL="${AEROLLM_INDEX_URL:-https://pypi.qukaizen.com/simple/}"
AEROLLM_PIP_SPEC="${AEROLLM_PIP_SPEC:-aerollm-api}"

site_dir()  { "$PY" -c "import sysconfig; print(sysconfig.get_path('platlib'))"; }
import_ok() { "$PY" -c "import aerollm_api" >/dev/null 2>&1; }
aerollm_version() {
    "$PY" -c "import aerollm_api; print(getattr(aerollm_api,'__version__','unknown'))" 2>/dev/null || echo "unknown"
}

clone_hint() {
    err "No aerollm sibling repo at ${BOLD}${AEROLLM_REPO}${RST}."
    warn "For a source (dev) build, either:"
    warn "  1) clone it next to arail:"
    warn "       git clone https://github.com/cdarnell/aerollm \"${AEROLLM_REPO}\""
    warn "  2) or point ARAIL_AEROLLM_REPO at your checkout."
    warn "Or install the published wheel instead: ./arailctl deep update"
}

cargo_build() {
    if [[ ! -d "$CRATE_DIR" ]]; then clone_hint; exit 1; fi
    if ! command -v cargo >/dev/null 2>&1; then
        err "cargo not found — install the Rust toolchain (https://rustup.rs) and retry."
        exit 1
    fi
    info "Building aerollm_api from ${BOLD}${AEROLLM_REPO}${RST} (cargo --release)…"
    ( cd "$AEROLLM_REPO" && cargo build --release -p aerollm-api --features extension-module )
    local built=""
    for cand in \
        "$AEROLLM_REPO/target/release/libaerollm_api.dylib" \
        "$AEROLLM_REPO/target/release/libaerollm_api.so"; do
        [[ -f "$cand" ]] && built="$cand" && break
    done
    if [[ -z "$built" ]]; then
        err "cargo build succeeded but no libaerollm_api.{dylib,so} under target/release."
        exit 1
    fi
    local dest; dest="$(site_dir)/aerollm_api.abi3.so"
    info "Installing → ${dest}"
    cp -f "$built" "$dest"
    verify_or_die
    info "${GRN}AeroLLM ready${RST} (source build) — the deep-mode 2nd inference."
}

pip_install() {  # $* = extra pip args (e.g. --upgrade)
    info "Installing aerollm_api from index ${BOLD}${AEROLLM_INDEX_URL}${RST}…"
    if ! "$PY" -m pip install "$@" \
            --index-url "$AEROLLM_INDEX_URL" \
            --extra-index-url "https://pypi.org/simple/" \
            "$AEROLLM_PIP_SPEC"; then
        err "pip could not install ${AEROLLM_PIP_SPEC} from the index."
        warn "AeroLLM wheels are macOS-arm64-only; on other platforms there's no"
        warn "matching wheel yet (CUDA backend pending). The lab runs without the"
        warn "2nd inference until then."
        exit 1
    fi
    verify_or_die
    info "${GRN}AeroLLM ready${RST} (release wheel $(aerollm_version)) — the 2nd inference."
}

verify_or_die() {
    if ! import_ok; then
        err "Installed the extension but \`import aerollm_api\` still fails."
        warn "Check that $PY is the same interpreter ARAIL runs (venv mismatch?)."
        exit 1
    fi
}

case "$MODE" in
    status)
        info "AeroLLM (2nd inference) status"
        printf '    repo:         %s\n' "$AEROLLM_REPO"
        if [[ -d "$CRATE_DIR" ]]; then
            printf '    crate:        %s (found → source/dev channel)\n' "$CRATE_DIR"
        else
            printf '    crate:        %s %s(missing → release channel)%s\n' "$CRATE_DIR" "$YLW" "$RST"
        fi
        printf '    index:        %s\n' "$AEROLLM_INDEX_URL"
        printf '    site-packages:%s\n' " $(site_dir 2>/dev/null || echo '?')"
        if import_ok; then
            printf '    aerollm_api:  %simportable ✓%s (version %s)\n' "$GRN" "$RST" "$(aerollm_version)"
        else
            printf '    aerollm_api:  %snot installed — run: ./arailctl deep rebuild (or: deep update)%s\n' "$YLW" "$RST"
        fi
        printf '    bg pressure:  %s\n' "${ARAIL_AEROLLM_BG_PRESSURE_PCT:-0.60 (default)}"
        exit 0
        ;;
    build)
        cargo_build
        ;;
    update)
        pip_install --upgrade
        ;;
    auto)
        if [[ -d "$CRATE_DIR" ]]; then
            info "Local sibling repo found → building from source (dev channel)."
            cargo_build
        else
            info "No sibling repo → installing the published wheel (release channel)."
            pip_install
        fi
        ;;
    *)
        err "mode must be one of: auto | build | update | status"
        exit 2
        ;;
esac
