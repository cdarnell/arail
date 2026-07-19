"""Local build-job ledger — lab/data/build_jobs.json (atomic writes).

The nucleus orchestrator is the run manager; this ledger keeps arail-side
context the orchestrator doesn't know: the preflight snapshot, a recorded
red-override, the chosen build mode, and eventual registry registration.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


def _jobs_file() -> Path:
    override = os.getenv("ARAIL_BUILD_JOBS_FILE", "").strip()
    if override:
        return Path(override)
    try:
        from arail.config import DATA_DIR
        return Path(DATA_DIR) / "build_jobs.json"
    except Exception:  # noqa: BLE001
        return Path("lab/data/build_jobs.json")


class BuildJobStore:
    def _load(self) -> Dict[str, Dict[str, Any]]:
        path = _jobs_file()
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text())
        except Exception:  # noqa: BLE001
            return {}

    def _save(self, jobs: Dict[str, Dict[str, Any]]) -> None:
        path = _jobs_file()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=str(path.parent),
                                       prefix=".build_jobs.", suffix=".tmp")
            with os.fdopen(fd, "w") as f:
                json.dump(jobs, f, indent=2, default=str)
            os.replace(tmp, path)
        except OSError:
            pass

    def create(self, run_id: str, *, mode: str, manifest_path: str,
               preflight: Optional[Dict[str, Any]],
               override_red: bool, dry_run: bool) -> Dict[str, Any]:
        jobs = self._load()
        job = {
            "run_id": run_id,
            "mode": mode,
            "dry_run": dry_run,
            "manifest_path": manifest_path,
            "preflight": preflight,
            "override_red": override_red,
            "created_at": time.time(),
            "phase": "submitted",
            "last_nucleus_status": None,
            "registered_entry_id": None,
        }
        jobs[run_id] = job
        self._save(jobs)
        return job

    def update(self, run_id: str, **fields: Any) -> Optional[Dict[str, Any]]:
        jobs = self._load()
        job = jobs.get(run_id)
        if job is None:
            return None
        job.update(fields)
        self._save(jobs)
        return job

    def get(self, run_id: str) -> Optional[Dict[str, Any]]:
        return self._load().get(run_id)

    def list(self) -> List[Dict[str, Any]]:
        return sorted(self._load().values(),
                      key=lambda j: j.get("created_at", 0), reverse=True)
