#!/usr/bin/env python3
"""
One-shot migration: ensure every Goal in lab/data/goals/ has a matching
Goal + SubObjective node in the Knowledge Canvas graph.

Idempotent — safe to re-run. Walks both `current.json` and
`history/*.json` and upserts each through GoalGraphService. No-op if the
graph already has the node (MERGE semantics).

Usage:
    python scripts/migrate_goals_to_graph.py

Exits 0 on success (including "nothing to do"), 1 on any unrecoverable
failure connecting to the graph.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path


def _load_canvas_modules():
    """Add canvas backend to sys.path and import GraphStore + GoalGraphService."""
    repo_root = Path(__file__).resolve().parents[1]
    canvas_backend = repo_root / "core" / "knowledge-canvas" / "backend"
    if not canvas_backend.exists():
        print(f"error: canvas backend not found at {canvas_backend}", file=sys.stderr)
        sys.exit(1)
    sys.path.insert(0, str(canvas_backend))
    from app.services.graph_store import GraphStore  # type: ignore
    from app.services.goal_graph import GoalGraphService  # type: ignore
    return GraphStore, GoalGraphService


def _iter_goal_records(goals_dir: Path):
    """Yield (record_dict, source_label) for current + every history file."""
    current = goals_dir / "current.json"
    if current.exists():
        try:
            yield json.loads(current.read_text()), "current"
        except (json.JSONDecodeError, OSError) as e:
            print(f"warn: failed to read {current}: {e}", file=sys.stderr)

    history_dir = goals_dir / "history"
    if history_dir.exists():
        for f in sorted(history_dir.glob("*.json")):
            try:
                yield json.loads(f.read_text()), f"history/{f.name}"
            except (json.JSONDecodeError, OSError) as e:
                print(f"warn: failed to read {f}: {e}", file=sys.stderr)


async def _migrate():
    GraphStore, GoalGraphService = _load_canvas_modules()
    from arail.config import DATA_DIR  # type: ignore

    goals_dir = DATA_DIR / "goals"
    if not goals_dir.exists():
        print(f"no goals directory at {goals_dir} — nothing to migrate.")
        return

    store = GraphStore(
        lance_path=os.getenv("LANCE_PATH", "./data/lance"),
        neo4j_uri=os.getenv("NEO4J_URI", "bolt://localhost:7687"),
        neo4j_auth=(
            os.getenv("NEO4J_USER", "neo4j"),
            os.getenv("NEO4J_PASSWORD", "changeme-please"),
        ),
    )
    try:
        await store.init()
    except Exception as e:
        print(f"error: graph init failed: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)

    svc = GoalGraphService(store)
    upserted = 0
    skipped = 0
    try:
        for record, label in _iter_goal_records(goals_dir):
            goal_id = record.get("id")
            if not goal_id:
                print(f"skip {label}: no id field")
                skipped += 1
                continue
            # Don't archive others when migrating history — only the
            # explicit `current.json` should remain active.
            archive_others = (label == "current")
            await svc.upsert_goal(record, archive_others=archive_others)
            print(f"upserted {label}: id={goal_id} status={record.get('status')}")
            upserted += 1
    finally:
        await store.close()

    print(f"\ndone. upserted={upserted} skipped={skipped}")


if __name__ == "__main__":
    asyncio.run(_migrate())
