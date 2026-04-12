"""Experiment Tracker — hypothesis → test → result lifecycle."""

from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


class ExperimentTracker:
    def __init__(self, experiments_dir: str | Path | None = None) -> None:
        if experiments_dir is None:
            from oglab.config import EXPERIMENTS_DIR
            self.base_dir = EXPERIMENTS_DIR
        else:
            self.base_dir = Path(experiments_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    def create(
        self,
        hypothesis: str,
        methodology: str,
        variables: Dict[str, Any],
        duration_days: Optional[int] = None,
        metrics: Optional[List[str]] = None,
        domain: str = "general",
    ) -> Dict[str, Any]:
        exp_id = uuid.uuid4().hex[:8]
        exp: Dict[str, Any] = {
            "id": exp_id,
            "domain": domain,
            "created_at": _now(),
            "status": "planning",
            "hypothesis": hypothesis,
            "methodology": methodology,
            "variables": variables,
            "expected_duration_days": duration_days,
            "metrics": metrics or [],
            "start_date": None,
            "end_date": None,
            "observations": [],
            "results": None,
            "conclusion": None,
        }
        self._save(exp)
        return exp

    def start(self, exp_id: str) -> Dict[str, Any]:
        exp = self._load(exp_id)
        exp["status"] = "in_progress"
        exp["start_date"] = _today()
        self._save(exp)
        return exp

    def observe(self, exp_id: str, observation: str,
                data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        exp = self._load(exp_id)
        exp["observations"].append({
            "date": _today(),
            "observation": observation,
            "data": data or {},
            "logged_at": _now(),
        })
        self._save(exp)
        return exp

    def complete(self, exp_id: str, results: Dict[str, Any],
                 conclusion: str, success: bool) -> Dict[str, Any]:
        exp = self._load(exp_id)
        exp["status"] = "completed"
        exp["end_date"] = _today()
        exp["results"] = results
        exp["conclusion"] = conclusion
        exp["hypothesis_supported"] = success
        self._save(exp)
        return exp

    def list_all(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        exps = []
        for f in self.base_dir.rglob("*.json"):
            exp = json.loads(f.read_text())
            if status and exp.get("status") != status:
                continue
            exps.append(exp)
        return sorted(exps, key=lambda x: x["created_at"], reverse=True)

    # ------------------------------------------------------------------
    def _path(self, exp_id: str) -> Path:
        return self.base_dir / f"{exp_id}.json"

    def _save(self, exp: Dict[str, Any]) -> None:
        self._path(exp["id"]).write_text(
            json.dumps(exp, indent=2, default=str)
        )

    def _load(self, exp_id: str) -> Dict[str, Any]:
        p = self._path(exp_id)
        if not p.exists():
            raise FileNotFoundError(f"Experiment {exp_id} not found")
        return json.loads(p.read_text())


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

def _today() -> str:
    return date.today().isoformat()
