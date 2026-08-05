#!/usr/bin/env bash
# package-aerollm-bundle.sh — maintainer-only producer for the BUNDLED
# install channel (scripts/build-aerollm.sh bundle).
#
# Builds aerollm_api from the local sibling source repo, then packages a
# verbatim copy of the compiled extension plus the Apache-2.0 compliance
# material into a tarball + sha256 sidecar, ready for
# `gh release upload <arail-tag> dist/aerollm-bundle/*.tar.gz{,.sha256}`.
#
# This script is NEVER run in CI (see ARCHITECTURE.md §10 — CI has no
# access to the private aeroLLM source). It is a manual, documented
# maintainer step, run from ~/ProJects/arail against a sibling checkout of
# ~/ProJects/qukaizen-aerollm.
#
# Usage:
#   bash scripts/package-aerollm-bundle.sh
#   ALLOW_DIRTY=1 bash scripts/package-aerollm-bundle.sh   # dirty worktree override
#
# Env:
#   ARAIL_AEROLLM_REPO   sibling aeroLLM checkout (default ~/ProJects/qukaizen-aerollm)
#   ARAIL_RELEASE_TAG    the ARAIL tag this bundle is built for (default: unset →
#                         MANIFEST.json.arail_release is "unreleased")
#   ALLOW_DIRTY          "1" to package from a dirty aeroLLM worktree anyway;
#                         MANIFEST.json.aerollm_dirty is stamped true and a
#                         modification note is appended.
set -euo pipefail

if [[ -t 1 && -z "${NO_COLOR:-}" ]]; then
    BOLD=$'\033[1m'; RED=$'\033[31m'; GRN=$'\033[32m'; YLW=$'\033[33m'; RST=$'\033[0m'
else
    BOLD=""; RED=""; GRN=""; YLW=""; RST=""
fi
info() { printf '%s\n' "${GRN}•${RST} $*"; }
warn() { printf '%s\n' "${YLW}!${RST} $*" >&2; }
err()  { printf '%s\n' "${RED}✗${RST} $*" >&2; }

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AEROLLM_REPO="${ARAIL_AEROLLM_REPO:-$HOME/ProJects/qukaizen-aerollm}"
CRATE_DIR="$AEROLLM_REPO/crates/aerollm-api"
OUT_DIR="$REPO_ROOT/dist/aerollm-bundle"
PY="${PYTHON:-python3}"

if [[ ! -d "$CRATE_DIR" ]]; then
    err "No aerollm sibling repo at ${BOLD}${AEROLLM_REPO}${RST} — this is a maintainer-only script."
    exit 1
fi
if ! command -v cargo >/dev/null 2>&1; then
    err "cargo not found — install the Rust toolchain (https://rustup.rs) and retry."
    exit 1
fi

# ── dirty-worktree refusal (§4.3, F11) — an unattributable build is a
# licence problem, not just a hygiene one. Apache-2.0 §4(b) requires ARAIL
# to state any modifications; "verbatim build of commit X" is only true if
# X is exactly what's on disk.
cd "$AEROLLM_REPO"
DIRTY="false"
if [[ -n "$(git status --porcelain)" ]]; then
    if [[ "${ALLOW_DIRTY:-0}" != "1" ]]; then
        err "aeroLLM worktree at ${BOLD}${AEROLLM_REPO}${RST} is dirty."
        warn "A dirty bundle can't honestly claim 'verbatim build of commit X'."
        warn "Commit or stash first, or override with ALLOW_DIRTY=1 (stamps aerollm_dirty: true)."
        exit 1
    fi
    warn "Worktree is dirty — packaging anyway (ALLOW_DIRTY=1). MANIFEST.json.aerollm_dirty=true."
    DIRTY="true"
fi
COMMIT="$(git rev-parse HEAD)"
SHORT_COMMIT="$(git rev-parse --short HEAD)"
cd "$REPO_ROOT"

info "Building aerollm_api from ${BOLD}${AEROLLM_REPO}${RST} @ ${SHORT_COMMIT} (cargo --release)…"
( cd "$AEROLLM_REPO" && cargo build --release -p aerollm-api --features extension-module )

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

# aeroLLM's own workspace version (Cargo.toml [workspace.package] version).
AEROLLM_VERSION="$("$PY" - "$AEROLLM_REPO/Cargo.toml" <<'PYEOF'
import re, sys
text = open(sys.argv[1]).read()
m = re.search(r'(?m)^version\s*=\s*"([^"]+)"', text)
print(m.group(1) if m else "unknown")
PYEOF
)"

rm -rf "$OUT_DIR"
mkdir -p "$OUT_DIR/stage"
STAGE="$OUT_DIR/stage"

cp -f "$BUILT" "$STAGE/aerollm_api.abi3.so"
cp -f "$AEROLLM_REPO/LICENSE" "$STAGE/LICENSE"
cp -f "$AEROLLM_REPO/NOTICE" "$STAGE/NOTICE"

SHA256="$(shasum -a 256 "$STAGE/aerollm_api.abi3.so" | awk '{print $1}')"
BUILT_AT="$("$PY" -c 'import datetime; print(datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))')"
ARAIL_RELEASE="${ARAIL_RELEASE_TAG:-unreleased}"
MODIFICATIONS="none — verbatim cargo --release build of the named commit"
if [[ "$DIRTY" == "true" ]]; then
    MODIFICATIONS="worktree was dirty at build time (ALLOW_DIRTY=1) — not a strictly verbatim build of the named commit; see aerollm_commit for the base"
fi

cat > "$STAGE/MANIFEST.json" <<JSONEOF
{
  "schema": "arail.aerollm-bundle/v1",
  "aerollm_version": "${AEROLLM_VERSION}",
  "aerollm_commit": "${COMMIT}",
  "aerollm_dirty": ${DIRTY},
  "built_at": "${BUILT_AT}",
  "built_by": "scripts/package-aerollm-bundle.sh",
  "platform": "macos-arm64",
  "python_abi": "abi3-cp39",
  "sha256": "${SHA256}",
  "license": "Apache-2.0",
  "modifications": "${MODIFICATIONS}",
  "arail_release": "${ARAIL_RELEASE}"
}
JSONEOF

VER_SLUG="${AEROLLM_VERSION}-${SHORT_COMMIT}"
TARBALL="$OUT_DIR/aerollm-api-${VER_SLUG}-macos-arm64.tar.gz"
( cd "$STAGE" && tar czf "$TARBALL" aerollm_api.abi3.so MANIFEST.json LICENSE NOTICE )
shasum -a 256 "$TARBALL" | awk -v f="$(basename "$TARBALL")" '{print $1"  "f}' > "${TARBALL}.sha256"

info "${GRN}Bundle packaged${RST}: ${TARBALL}"
info "  sha256:  $(cat "${TARBALL}.sha256")"
info "  commit:  ${COMMIT} (dirty=${DIRTY})"
info "Next: gh release upload <arail-tag> ${TARBALL} ${TARBALL}.sha256"
