"""GoalStore — persists the user's current goal and history."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


from oglab.config import DATA_DIR

GOALS_DIR = DATA_DIR / "goals"
CURRENT_FILE = GOALS_DIR / "current.json"
HISTORY_DIR = GOALS_DIR / "history"


class GoalStore:
    """Manages the active goal and archives old ones."""

    def __init__(self) -> None:
        GOALS_DIR.mkdir(parents=True, exist_ok=True)
        HISTORY_DIR.mkdir(parents=True, exist_ok=True)

    def set_goal(self, parsed_goal: Dict[str, Any]) -> Dict[str, Any]:
        """Set a new active goal.  Archives the previous one."""
        # Archive current if exists
        current = self.get_current()
        if current:
            self._archive(current)

        goal_record: Dict[str, Any] = {
            "id": uuid.uuid4().hex[:8],
            "goal_text": parsed_goal.get("goal", ""),
            "parsed": parsed_goal,
            "created_at": _now(),
            "status": "active",
            "experiments": [],       # linked experiment IDs
            "findings": [],          # research findings
            "report": None,          # final researcher report
            "progress": 0.0,
        }
        self._save_current(goal_record)
        return goal_record

    def get_current(self) -> Optional[Dict[str, Any]]:
        if not CURRENT_FILE.exists():
            return None
        try:
            return json.loads(CURRENT_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            return None

    def update_current(self, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        current = self.get_current()
        if not current:
            return None
        current.update(updates)
        current["updated_at"] = _now()
        self._save_current(current)
        return current

    def link_experiment(self, exp_id: str) -> None:
        current = self.get_current()
        if current and exp_id not in current["experiments"]:
            current["experiments"].append(exp_id)
            current["updated_at"] = _now()
            self._save_current(current)

    def add_finding(self, finding: Dict[str, Any]) -> None:
        current = self.get_current()
        if current:
            current["findings"].append({
                **finding,
                "found_at": _now(),
            })
            current["updated_at"] = _now()
            self._save_current(current)

    def set_report(self, report: str) -> None:
        current = self.get_current()
        if current:
            current["report"] = report
            current["updated_at"] = _now()
            self._save_current(current)

    def update_progress(self, progress: float) -> None:
        current = self.get_current()
        if current:
            current["progress"] = round(min(1.0, max(0.0, progress)), 2)
            current["updated_at"] = _now()
            self._save_current(current)

    def list_history(self) -> List[Dict[str, Any]]:
        history = []
        for f in sorted(HISTORY_DIR.glob("*.json"), reverse=True):
            try:
                history.append(json.loads(f.read_text()))
            except (json.JSONDecodeError, OSError):
                continue
        return history

    # -- internal --

    def _save_current(self, record: Dict[str, Any]) -> None:
        CURRENT_FILE.write_text(json.dumps(record, indent=2, default=str))

    def _archive(self, record: Dict[str, Any]) -> None:
        record["status"] = "archived"
        record["archived_at"] = _now()
        path = HISTORY_DIR / f"{record['id']}.json"
        path.write_text(json.dumps(record, indent=2, default=str))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
