"""Model Building — ARAIL's client-side of the qukaizen-nucleus SSDP pipeline.

- preflight:      pure resource/time estimator (works with nucleus offline)
- nucleus_client: HTTP client for the orchestrator (:8000) + trainer (:8006)
- manifest:       superskill manifest generation into the nucleus configs tree
- jobs:           local job ledger (lab/data/build_jobs.json)
"""
