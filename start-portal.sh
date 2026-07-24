#!/bin/bash
# Start the Arail portal server with correct PYTHONPATH from the workspace root
cd "$(dirname "$0")"
export PYTHONPATH=src
. .venv/bin/activate
# --reload re-runs the whole startup event on any file touch (amplifying every
# boot-time task). It's a dev convenience, off by default — set ARAIL_DEV=1
# (or ARAIL_RELOAD=1) to enable it.
RELOAD_FLAG=""
if [[ "${ARAIL_DEV:-0}" == "1" || "${ARAIL_RELOAD:-0}" == "1" ]]; then
    RELOAD_FLAG="--reload"
fi
exec python -m uvicorn arail.portal.app:app $RELOAD_FLAG --port 8080
