#!/usr/bin/env bash
# check_ai_eng_artifact.sh — probe whether the self-hosted ai-eng GGUF is live.
#
# Used as the gate for follow-up ticket 2b (delete Modelfile.preview + preview
# net once this script returns 0). Also used by QA tests to document the
# deferral of preview-net removal.
#
# Exit 0  → at least one self-hosted host has the GGUF live (HF or GitHub).
# Exit 1  → artifact not yet uploaded / unreachable. Not an error — the
#            preview net keeps setup working in this state.
#
# Usage:
#   scripts/check_ai_eng_artifact.sh
#   ARAIL_AI_ENG_HF_REPO=myorg/myrepo ARAIL_AI_ENG_QUANT=Q4_K_M \
#     scripts/check_ai_eng_artifact.sh
#
# All env vars default to the same __PLACEHOLDER__ values as setup.sh;
# if the repo/url is still a placeholder this script always exits 1
# (the artifact is definitely not yet uploaded).

set -euo pipefail

HF_REPO="${ARAIL_AI_ENG_HF_REPO:-qukaizen/ai-eng-1.5b-gguf}"  # __PLACEHOLDER__
QUANT="${ARAIL_AI_ENG_QUANT:-Q4_K_M}"                          # __PLACEHOLDER__
GH_URL="${ARAIL_AI_ENG_GH_URL:-https://github.com/qukaizen/arail/releases/download/ai-eng-1.5b/ai-eng-1.5b-Q4_K_M.gguf}"  # __PLACEHOLDER__

TIMEOUT=8

# Derive the expected GGUF filename from quant tag.
GGUF_FILE="ai-eng-1.5b-${QUANT}.gguf"

# ── 1. Probe HuggingFace via the /resolve/ redirect endpoint ─────────────────
# A 200 (or 302 with Location) means the blob exists; a 404 means it doesn't.
# We use -I (HEAD) to avoid downloading the blob.
HF_URL="https://huggingface.co/${HF_REPO}/resolve/main/${GGUF_FILE}"

echo "Checking HuggingFace: ${HF_URL}" >&2
if curl -fsSL -I -m "${TIMEOUT}" -o /dev/null "${HF_URL}" 2>/dev/null; then
    echo "LIVE: ai-eng GGUF found on HuggingFace (${HF_URL})" >&2
    exit 0
fi

# ── 2. Probe GitHub Release asset ────────────────────────────────────────────
echo "HuggingFace probe failed — checking GitHub Release: ${GH_URL}" >&2
if curl -fsSL -I -m "${TIMEOUT}" -o /dev/null "${GH_URL}" 2>/dev/null; then
    echo "LIVE: ai-eng GGUF found on GitHub Release (${GH_URL})" >&2
    exit 0
fi

# ── Artifact not yet reachable ───────────────────────────────────────────────
echo "NOT LIVE: self-hosted ai-eng GGUF not found on HuggingFace or GitHub." >&2
echo "This is expected until the user runs scripts/build_ai_eng.sh publish and uploads." >&2
echo "The preview net (Modelfile.preview) keeps setup working in the meantime." >&2
echo "Run this script again after uploading to confirm live status (exit 0)." >&2
exit 1
