#!/bin/bash
# Start the Arail portal server with correct PYTHONPATH from the workspace root
cd "$(dirname "$0")"
export PYTHONPATH=src
. .venv/bin/activate
exec python -m uvicorn arail.portal.app:app --reload --port 8080
