"""HTTP client for the qukaizen-nucleus SSDP orchestrator + trainer + synthesizer.

Endpoints (nucleus PORTS.md): orchestrator :8000, synthesizer :8005, trainer
:8006. All localhost — the egress guard always allows local hosts. The
orchestrator's default port collides with arail's vLLM/LOCAL_API_PORT
convention, so the URL is configurable and health() SHAPE-CHECKS the
response: a vLLM answering :8000 is reported as "something else is on this
port", not as nucleus.

Auth: mutations need NUCLEUS_API_KEY (X-API-Key header); reads are open.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class NucleusHealth:
    up: bool
    url: str
    latency_ms: Optional[float] = None
    detail: str = ""


class NucleusClient:
    def __init__(self,
                 orchestrator_url: Optional[str] = None,
                 trainer_url: Optional[str] = None,
                 synthesizer_url: Optional[str] = None,
                 api_key: Optional[str] = None,
                 timeout: float = 5.0) -> None:
        self.orchestrator_url = (orchestrator_url
                                 or os.getenv("NUCLEUS_ORCHESTRATOR_URL",
                                              "http://127.0.0.1:8000")).rstrip("/")
        self.trainer_url = (trainer_url
                            or os.getenv("NUCLEUS_TRAINER_URL",
                                         "http://127.0.0.1:8006")).rstrip("/")
        self.synthesizer_url = (synthesizer_url
                                or os.getenv("NUCLEUS_SYNTHESIZER_URL",
                                             "http://127.0.0.1:8005")).rstrip("/")
        self.api_key = api_key or os.getenv("NUCLEUS_API_KEY", "")
        self.timeout = timeout
        import requests
        self._session = requests.Session()

    # ── plumbing ────────────────────────────────────────────────────
    def _headers(self, *, auth: bool) -> Dict[str, str]:
        h = {"Content-Type": "application/json"}
        if auth and self.api_key:
            h["X-API-Key"] = self.api_key
        return h

    def _get(self, path: str, base: Optional[str] = None) -> Any:
        r = self._session.get(f"{base or self.orchestrator_url}{path}",
                              headers=self._headers(auth=False),
                              timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def _post(self, path: str, body: Optional[Dict[str, Any]] = None,
             base: Optional[str] = None, timeout: Optional[float] = None) -> Any:
        r = self._session.post(f"{base or self.orchestrator_url}{path}",
                               headers=self._headers(auth=True),
                               json=body or {},
                               timeout=timeout if timeout is not None else self.timeout)
        r.raise_for_status()
        return r.json()

    # ── health ──────────────────────────────────────────────────────
    def health(self) -> NucleusHealth:
        import time
        start = time.monotonic()
        try:
            data = self._get("/pipeline/list")
        except Exception as exc:  # noqa: BLE001
            return NucleusHealth(
                up=False, url=self.orchestrator_url,
                latency_ms=(time.monotonic() - start) * 1000,
                detail=f"{type(exc).__name__}: {str(exc)[:160]}")
        latency = (time.monotonic() - start) * 1000
        # Shape check — nucleus returns a runs collection; vLLM's /v1-less
        # 404 handler or another service would not.
        looks_like_nucleus = isinstance(data, (list, dict)) and (
            isinstance(data, list)
            or any(k in data for k in ("runs", "pipelines", "items")))
        if not looks_like_nucleus:
            return NucleusHealth(
                up=False, url=self.orchestrator_url, latency_ms=latency,
                detail="port answered but response is not the nucleus "
                       "orchestrator — is another service on this port?")
        return NucleusHealth(up=True, url=self.orchestrator_url,
                             latency_ms=latency)

    # ── pipeline control ────────────────────────────────────────────
    def start(self, run_id: str, manifest_path: str,
              dry_run: bool = False) -> Dict[str, Any]:
        return self._post("/pipeline/start", {
            "run_id": run_id,
            "superskill_manifest_path": manifest_path,
            "dry_run": dry_run,
        })

    def status(self, run_id: str) -> Dict[str, Any]:
        try:
            return self._get(f"/pipeline/{run_id}")
        except Exception as exc:  # noqa: BLE001
            # A 404 means nucleus no longer knows the run (its in-memory
            # registry lost it — e.g. an orchestrator restart). Surface a
            # typed status so callers can mark the job "lost" instead of
            # freezing at the last-known phase.
            resp = getattr(exc, "response", None)
            if getattr(resp, "status_code", None) == 404 or "404" in str(exc):
                return {"status": "not_found"}
            raise

    def list(self) -> Any:
        return self._get("/pipeline/list")

    def pause(self) -> Any:
        return self._post("/pipeline/pause")

    def resume(self) -> Any:
        return self._post("/pipeline/resume")

    def stop(self, run_id: str) -> Any:
        return self._post(f"/pipeline/{run_id}/stop")

    def abort(self, run_id: str) -> Any:
        return self._post(f"/pipeline/{run_id}/abort")

    def events(self, run_id: str) -> List[Dict[str, Any]]:
        data = self._get(f"/pipeline/{run_id}/events")
        return data if isinstance(data, list) else data.get("events", [])

    def graduation(self, run_id: str) -> Dict[str, Any]:
        return self._get(f"/pipeline/{run_id}/graduation")

    def seal(self, run_id: str) -> Dict[str, Any]:
        return self._get(f"/seal/by-run/{run_id}")

    # ── trainer telemetry (:8006) ───────────────────────────────────
    def trainer_progress(self) -> Optional[Dict[str, Any]]:
        """epoch/step/total_steps/loss/tokens_per_sec, or None when down."""
        try:
            return self._get("/status", base=self.trainer_url)
        except Exception:  # noqa: BLE001
            return None

    # ── direct synthesizer/trainer calls (World-corpus path) ─────────
    # These bypass the orchestrator entirely — used when the corpus is
    # already-curated World content (see arail.build.world_corpus), so
    # KICE's heuristic re-tagging would only downgrade it. /synthesize is a
    # long, fully sequential, per-example call (no parallelism on the
    # nucleus side) — pass a generous timeout, not the client default.
    def synthesize(self, examples: List[Dict[str, Any]],
                   corpus_version: int = 0, *,
                   timeout: float = 600.0) -> Dict[str, Any]:
        """POST {synthesizer_url}/synthesize. Response's `training_records`
        is already trainer-ready {"messages": [...]} chat format."""
        return self._post("/synthesize",
                          {"examples": examples, "corpus_version": corpus_version},
                          base=self.synthesizer_url, timeout=timeout)

    def train_direct(self, dataset: List[Dict[str, Any]], *,
                     run_id: str = "",
                     config_overrides: Optional[Dict[str, Any]] = None,
                     timeout: float = 30.0) -> Dict[str, Any]:
        """POST {trainer_url}/train with an INLINE dataset (not dataset_path
        — TRAINER_ALLOWED_DATASET_ROOTS would never include an ARAIL-written
        path; the orchestrator's own node_train already sends data inline
        for the same host-native-trainer reachability reason). /train just
        launches a background task and returns immediately — poll
        trainer_progress() for status, not this call's response."""
        return self._post("/train",
                          {"dataset": dataset, "run_id": run_id,
                           "config_overrides": config_overrides or {}},
                          base=self.trainer_url, timeout=timeout)
