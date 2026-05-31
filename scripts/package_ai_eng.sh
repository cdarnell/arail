#!/usr/bin/env bash
# package_ai_eng.sh — DEPRECATED. Consolidated into build_ai_eng.sh.
# Retained as a thin shim so old call sites keep working. Use:
#   ./scripts/build_ai_eng.sh publish --yes-i-have-read-bench --license Apache-2.0
set -euo pipefail
echo "[package_ai_eng] DEPRECATED: this scaffold was consolidated into build_ai_eng.sh." >&2
echo "[package_ai_eng] Forwarding to: scripts/build_ai_eng.sh publish $*" >&2
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "${SCRIPT_DIR}/build_ai_eng.sh" publish "$@"
