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
            from arail.config import EXPERIMENTS_DIR
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

    def search(
        self,
        query: str,
        *,
        k: int = 5,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Semantic search over hypothesis + conclusion + methodology.

        Uses the shared LanceDB index so questions like *"have we tried
        KV-cache quantization on a 70B?"* surface relevant historical
        experiments without exact-keyword overlap. The index is rebuilt
        on every write (see ``_rebuild_index``), so results always
        reflect the current corpus.

        When LanceDB is missing or the index is empty, we degrade to a
        substring scan over the same fields — never silently empty.
        """
        from arail.vector_index import VectorIndex, available

        all_exps = self.list_all(status=status) if status else self.list_all()
        by_id = {e.get("id"): e for e in all_exps if e.get("id")}

        # Vector path.
        if available():
            idx = VectorIndex(name="experiments", db_path=self._index_dir())
            if idx.count() == 0:
                self._rebuild_index()
            hits = idx.search(query, k=max(k * 2, k))
            ranked: List[Dict[str, Any]] = []
            for h in hits:
                exp = by_id.get(h.get("id"))
                if not exp:
                    continue
                if status and exp.get("status") != status:
                    continue
                enriched = dict(exp)
                enriched["score"] = h.get("score", 0.0)
                enriched["match_source"] = "semantic"
                ranked.append(enriched)
                if len(ranked) >= k:
                    break
            if ranked:
                return ranked

        # Substring fallback — case-insensitive across the same fields.
        needle = query.lower().strip()
        if not needle:
            return []
        out: List[Dict[str, Any]] = []
        for exp in all_exps:
            haystack = " ".join([
                str(exp.get("hypothesis", "")),
                str(exp.get("methodology", "")),
                str(exp.get("conclusion", "") or ""),
                str(exp.get("domain", "")),
            ]).lower()
            if needle in haystack:
                exp = dict(exp)
                exp["match_source"] = "keyword"
                out.append(exp)
                if len(out) >= k:
                    break
        return out

    # ------------------------------------------------------------------
    def _path(self, exp_id: str) -> Path:
        return self.base_dir / f"{exp_id}.json"

    def _index_dir(self) -> Path:
        return self.base_dir / ".cache" / "lancedb"

    def _rebuild_index(self) -> int:
        """Rebuild the LanceDB experiments index. Returns row count.

        Called after every write so search results never lag behind the
        on-disk JSONs. The vector input combines the fields a researcher
        actually queries by — hypothesis, conclusion, methodology, and
        the structured domain tag.
        """
        from arail.vector_index import VectorIndex, hash_embedding, available

        if not available():
            return 0
        rows: List[Dict[str, Any]] = []
        for exp in self.list_all():
            text = " ".join([
                str(exp.get("hypothesis", "")),
                str(exp.get("methodology", "")),
                str(exp.get("conclusion", "") or ""),
                str(exp.get("domain", "")),
            ])
            rows.append({
                "id": exp.get("id"),
                "domain": exp.get("domain", "general"),
                "status": exp.get("status", "unknown"),
                "vector": hash_embedding(text),
            })
        idx = VectorIndex(name="experiments", db_path=self._index_dir())
        return idx.replace(rows)

    def _save(self, exp: Dict[str, Any]) -> None:
        self._path(exp["id"]).write_text(
            json.dumps(exp, indent=2, default=str)
        )
        # Refresh the vector index so the next search() sees this write.
        # Best-effort — never block a save on indexing failure.
        try:
            self._rebuild_index()
        except Exception:
            pass

    def _load(self, exp_id: str) -> Dict[str, Any]:
        p = self._path(exp_id)
        if not p.exists():
            raise FileNotFoundError(f"Experiment {exp_id} not found")
        return json.loads(p.read_text())


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

def _today() -> str:
    return date.today().isoformat()
