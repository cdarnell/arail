"""
GoalGraphService — goal-aware operations on top of GraphStore.

Bridges between ARAIL's GoalStore record shape (parsed goal dicts from
src/arail/goals.py) and the graph's Goal/SubObjective node model.

Goal record (input to upsert_goal) shape:
  {
    "id": str,
    "goal_text": str,
    "parsed": {
      "domain": str | None,
      "primary_objective": str | None,
      "sub_objectives": [str, ...],
      ...
    },
    "created_at": str (ISO8601),
    "status": "active" | "archived" | ...,
  }
"""
from __future__ import annotations

import hashlib
from typing import Any

from app.services.graph_store import GraphStore


def _sub_objective_id(goal_id: str, slot: int) -> str:
    return f"{goal_id}::so::{slot}"


def _normalize_goal_record(record: dict[str, Any]) -> dict[str, Any]:
    """Convert a GoalStore record to the shape GraphStore.upsert_goal expects."""
    parsed = record.get("parsed") or {}
    raw_subs = parsed.get("sub_objectives") or []
    sub_objectives = []
    for slot, text in enumerate(raw_subs):
        text_str = str(text or "").strip()
        if not text_str:
            continue
        sub_objectives.append({
            "id": _sub_objective_id(record["id"], slot),
            "text": text_str,
            "slot": slot,
        })
    return {
        "id": record["id"],
        "text": record.get("goal_text", "") or parsed.get("primary_objective", ""),
        "domain": parsed.get("domain"),
        "status": record.get("status", "active"),
        "created_at": record.get("created_at", ""),
        "sub_objectives": sub_objectives,
    }


class GoalGraphService:
    """Wraps GraphStore with goal-aware operations.

    The graph is the source of truth for Goal ↔ Source linkage; this
    service provides a domain-friendly API on top of raw graph ops.
    """

    def __init__(self, store: GraphStore):
        self.store = store

    async def upsert_goal(
        self,
        record: dict[str, Any],
        *,
        archive_others: bool = True,
    ) -> dict[str, Any]:
        """Create/update a Goal + its SubObjective children.

        If archive_others is True (default), every other active Goal is
        flipped to archived. The GoalStore allows only one active goal.
        """
        normalized = _normalize_goal_record(record)
        if archive_others and normalized.get("status", "active") == "active":
            await self._archive_other_active_goals(normalized["id"])
        return await self.store.upsert_goal(normalized)

    async def archive_goal(self, goal_id: str) -> None:
        await self.store.archive_goal(goal_id)

    async def link_source_to_goal(
        self,
        source_id: str,
        goal_id: str,
        *,
        sub_objective_id: str | None = None,
        relevance: float | None = None,
    ) -> None:
        """Write Goal -[:MOTIVATES]-> Source and optional SubObjective -[:ADDRESSES]-> Source."""
        props: dict[str, Any] = {}
        if relevance is not None:
            props["relevance"] = float(relevance)
        await self.store.link(
            goal_id, source_id, "MOTIVATES", props,
            src_label="Goal", dst_label="Source",
        )
        if sub_objective_id:
            await self.store.link(
                sub_objective_id, source_id, "ADDRESSES", props,
                src_label="SubObjective", dst_label="Source",
            )

    async def unlink_source_from_goal(
        self,
        source_id: str,
        goal_id: str,
        *,
        sub_objective_id: str | None = None,
    ) -> None:
        await self.store.unlink(
            goal_id, source_id, "MOTIVATES",
            src_label="Goal", dst_label="Source",
        )
        if sub_objective_id:
            await self.store.unlink(
                sub_objective_id, source_id, "ADDRESSES",
                src_label="SubObjective", dst_label="Source",
            )

    async def coverage(self, goal_id: str) -> dict[str, Any]:
        """Return coverage stats for the gauge.

        Shape:
          {
            "goal_id": str,
            "total_sources": int,
            "sub_objectives": [
              {"id", "text", "slot", "source_count", "top_sources": [{"id","title"}]}
            ],
            "gaps": [sub_objective_id, ...],   # sub-objectives with 0 sources
            "last_added_at": str | None,
          }
        """
        async with self.store.n.session() as s:
            sub_q = await s.run(
                """
                MATCH (g:Goal {id:$gid})-[:HAS_SUB_OBJECTIVE]->(so:SubObjective)
                OPTIONAL MATCH (so)-[:ADDRESSES]->(src:Source)
                WITH so, collect(src) AS srcs
                RETURN so.id AS id, so.text AS text, so.slot AS slot,
                       size(srcs) AS source_count,
                       [s IN srcs | {id: s.id, title: s.title}][..3] AS top_sources
                ORDER BY so.slot
                """,
                gid=goal_id,
            )
            sub_objectives = [dict(r) async for r in sub_q]

            total_q = await s.run(
                """
                MATCH (g:Goal {id:$gid})-[:MOTIVATES]->(src:Source)
                RETURN count(DISTINCT src) AS total
                """,
                gid=goal_id,
            )
            total_row = await total_q.single()
            total_sources = int(total_row["total"]) if total_row else 0

        gaps = [so["id"] for so in sub_objectives if so["source_count"] == 0]
        return {
            "goal_id": goal_id,
            "total_sources": total_sources,
            "sub_objectives": sub_objectives,
            "gaps": gaps,
            "last_added_at": None,  # populated in Phase 2 when triage timestamps land
        }

    async def sources_for_goal(self, goal_id: str) -> list[dict[str, Any]]:
        """All sources MOTIVATED by this goal, sorted by relevance desc."""
        async with self.store.n.session() as s:
            result = await s.run(
                """
                MATCH (g:Goal {id:$gid})-[r:MOTIVATES]->(src:Source)
                RETURN src.id AS id, src.title AS title, src.kind AS kind,
                       src.domain AS domain, src.tags AS tags,
                       coalesce(r.relevance, 0.0) AS relevance
                ORDER BY relevance DESC
                """,
                gid=goal_id,
            )
            return [dict(r) async for r in result]

    # ------------------------------------------------------------------
    async def _archive_other_active_goals(self, keep_id: str) -> None:
        async with self.store.n.session() as s:
            await s.run(
                "MATCH (g:Goal {status:'active'}) WHERE g.id <> $keep "
                "SET g.status='archived'",
                keep=keep_id,
            )
