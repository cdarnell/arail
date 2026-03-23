from fastapi import APIRouter, HTTPException
from typing import Any, Dict
import json
import os
from pathlib import Path

router = APIRouter(prefix="/api/kibd")

@router.post("/run-suite")
async def run_kibd_suite() -> Dict[str, Any]:
    """Run the KibD checks suite and return results.

    This implementation reads the checks from `core/kibd/checks.json` and
    returns a simulated run result for each check. In a real deployment this
    route should execute the probes using kube API / Prometheus / HTTP checks.
    """
    base = Path(__file__).resolve().parent.parent.parent
    checks_path = base / "core" / "kibd" / "checks.json"
    if not checks_path.exists():
        raise HTTPException(status_code=500, detail=f"checks.json not found at {checks_path}")

    try:
        with open(checks_path, "r", encoding="utf-8") as fh:
            checks = json.load(fh)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    # Simulate running each check: mark as 'pass' but include probe info.
    results = []
    for c in checks:
        results.append({
            "id": c.get("id"),
            "name": c.get("name"),
            "severity": c.get("severity"),
            "status": "pass",
            "note": "simulated-run (implement real probes in gateway)",
            "probe": c.get("probe", {}),
        })

    overall = "pass" if all(r["status"] == "pass" for r in results) else "fail"
    return {"overall": overall, "results": results}
