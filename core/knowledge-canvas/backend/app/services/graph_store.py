"""
Source-aware graph store. LanceDB for vectors, Neo4j for typed edges.

Why both:
  - LanceDB gets us fast hybrid search (vector + SQL filters in one query)
    and ships embedded — no separate container.
  - Neo4j holds typed relationships we can't express well in a vector
    store: wikilinks, "discovered_from", "motivates_experiment", etc.

Why source-aware (vs. the Obsidian-only store in the earlier prototype):
  - Every node is a Source record, not a markdown file. That means an
    arXiv paper, a USDA API pull, and a user note all live in the same
    graph, uniformly queryable.
"""
import os
from pathlib import Path
from typing import Any

import lancedb
import numpy as np
import pyarrow as pa
from neo4j import AsyncGraphDatabase

from app.models.source import Source
from app.services.embeddings import get_embedder

TABLE = "lab_sources"
VECTOR_DIM = 1536


def _schema() -> pa.Schema:
    return pa.schema([
        pa.field("id", pa.string()),
        pa.field("kind", pa.string()),
        pa.field("title", pa.string()),
        pa.field("uri", pa.string()),
        pa.field("body_excerpt", pa.string()),
        pa.field("tags", pa.list_(pa.string())),
        pa.field("year", pa.int32()),
        pa.field("author", pa.string()),
        pa.field("domain", pa.string()),
        pa.field("ingested_by", pa.string()),
        pa.field("created_at", pa.string()),    # ISO8601
        pa.field("vector", pa.list_(pa.float32(), VECTOR_DIM)),
    ])


class GraphStore:
    def __init__(self, lance_path: str, neo4j_uri: str, neo4j_auth: tuple[str, str]):
        self.lance_path = lance_path
        self.n = AsyncGraphDatabase.driver(neo4j_uri, auth=neo4j_auth)
        self.embed = get_embedder()
        self._db: lancedb.DBConnection | None = None
        self._table: Any = None

    async def init(self):
        os.makedirs(self.lance_path, exist_ok=True)
        self._db = lancedb.connect(self.lance_path)
        if TABLE in self._db.table_names():
            self._table = self._db.open_table(TABLE)
        else:
            self._table = self._db.create_table(TABLE, schema=_schema())

        async with self.n.session() as s:
            await s.run(
                "CREATE CONSTRAINT source_id IF NOT EXISTS "
                "FOR (n:Source) REQUIRE n.id IS UNIQUE"
            )
            await s.run(
                "CREATE CONSTRAINT goal_id IF NOT EXISTS "
                "FOR (n:Goal) REQUIRE n.id IS UNIQUE"
            )
            await s.run(
                "CREATE CONSTRAINT subobjective_id IF NOT EXISTS "
                "FOR (n:SubObjective) REQUIRE n.id IS UNIQUE"
            )

    async def close(self):
        await self.n.close()

    # ------------------------------------------------------------------
    async def upsert(self, source: Source) -> Source:
        """Idempotent. Same id = update, not duplicate."""
        vec = await self.embed(f"{source.title}\n\n{source.body_excerpt}")

        self._table.delete(f"id = '{source.id}'")
        self._table.add([{
            "id": source.id,
            "kind": source.kind,
            "title": source.title,
            "uri": source.uri,
            "body_excerpt": source.body_excerpt,
            "tags": source.tags,
            "year": source.year or 0,
            "author": source.author or "",
            "domain": source.domain or "",
            "ingested_by": source.ingested_by,
            "created_at": source.created_at.isoformat(),
            "vector": np.array(vec, dtype=np.float32),
        }])

        async with self.n.session() as s:
            await s.run(
                """
                MERGE (n:Source {id:$id})
                SET n.kind=$kind, n.title=$title, n.uri=$uri,
                    n.tags=$tags, n.year=$year, n.domain=$domain,
                    n.ingested_by=$ingested_by, n.triage_state=$triage_state
                """,
                id=source.id, kind=source.kind, title=source.title,
                uri=source.uri, tags=source.tags, year=source.year or 0,
                domain=source.domain or "", ingested_by=source.ingested_by,
                triage_state=source.triage_state,
            )
        return source

    async def remove(self, source_id: str) -> bool:
        self._table.delete(f"id = '{source_id}'")
        async with self.n.session() as s:
            await s.run("MATCH (n:Source {id:$id}) DETACH DELETE n", id=source_id)
        return True

    # ------------------------------------------------------------------
    async def link(
        self,
        src_id: str,
        dst_id: str,
        rel: str,
        props: dict | None = None,
        src_label: str = "Source",
        dst_label: str = "Source",
    ):
        """
        Create a typed edge. `rel` is one of:
          LINKS_TO, DISCOVERED_FROM, MOTIVATES, CITES, DERIVED_FROM, SUGGESTED, ADDRESSES
        Optional src_label / dst_label support cross-type edges
        (e.g. Goal -[:MOTIVATES]-> Source, SubObjective -[:ADDRESSES]-> Source).
        """
        props = props or {}
        async with self.n.session() as s:
            await s.run(
                f"MATCH (a:{src_label} {{id:$src}}), (b:{dst_label} {{id:$dst}}) "
                f"MERGE (a)-[r:{rel}]->(b) SET r += $props",
                src=src_id, dst=dst_id, props=props,
            )

    async def unlink(
        self,
        src_id: str,
        dst_id: str,
        rel: str,
        src_label: str = "Source",
        dst_label: str = "Source",
    ):
        async with self.n.session() as s:
            await s.run(
                f"MATCH (a:{src_label} {{id:$src}})-[r:{rel}]->(b:{dst_label} {{id:$dst}}) DELETE r",
                src=src_id, dst=dst_id,
            )

    # ------------------------------------------------------------------
    # Goal & SubObjective nodes
    # ------------------------------------------------------------------
    async def upsert_goal(self, goal: dict) -> dict:
        """Idempotent. Writes a Goal node + child SubObjective nodes.

        Expects goal dict with id, text, domain, status, created_at,
        sub_objectives: [{id, text, slot}].
        """
        sub_objs = goal.get("sub_objectives") or []
        async with self.n.session() as s:
            await s.run(
                """
                MERGE (g:Goal {id:$id})
                SET g.text=$text, g.domain=$domain, g.status=$status,
                    g.created_at=$created_at,
                    g.sub_objective_texts=$sub_obj_texts
                """,
                id=goal["id"], text=goal.get("text", ""),
                domain=goal.get("domain", "") or "",
                status=goal.get("status", "active"),
                created_at=goal.get("created_at", ""),
                sub_obj_texts=[so.get("text", "") for so in sub_objs],
            )
            for so in sub_objs:
                await s.run(
                    """
                    MERGE (so:SubObjective {id:$id})
                    SET so.goal_id=$goal_id, so.text=$text, so.slot=$slot
                    WITH so
                    MATCH (g:Goal {id:$goal_id})
                    MERGE (g)-[:HAS_SUB_OBJECTIVE]->(so)
                    """,
                    id=so["id"], goal_id=goal["id"],
                    text=so.get("text", ""), slot=so.get("slot", 0),
                )
        return goal

    async def archive_goal(self, goal_id: str) -> None:
        async with self.n.session() as s:
            await s.run(
                "MATCH (g:Goal {id:$id}) SET g.status='archived'",
                id=goal_id,
            )

    async def get_active_goal(self) -> dict | None:
        async with self.n.session() as s:
            result = await s.run(
                """
                MATCH (g:Goal {status:'active'})
                OPTIONAL MATCH (g)-[:HAS_SUB_OBJECTIVE]->(so:SubObjective)
                RETURN g.id AS id, g.text AS text, g.domain AS domain,
                       g.status AS status, g.created_at AS created_at,
                       collect(DISTINCT {id: so.id, text: so.text, slot: so.slot}) AS sub_objectives
                LIMIT 1
                """
            )
            row = await result.single()
            if not row:
                return None
            data = dict(row)
            data["sub_objectives"] = [s for s in data["sub_objectives"] if s.get("id")]
            return data

    async def goals_for_source(self, source_id: str) -> dict[str, float]:
        """Return {goal_id: relevance} for every Goal that MOTIVATES this source."""
        async with self.n.session() as s:
            result = await s.run(
                """
                MATCH (g:Goal)-[r:MOTIVATES]->(n:Source {id:$id})
                RETURN g.id AS goal_id, coalesce(r.relevance, 0.0) AS relevance
                """,
                id=source_id,
            )
            return {row["goal_id"]: float(row["relevance"]) async for row in result}

    # ------------------------------------------------------------------
    async def get(self, source_id: str) -> dict | None:
        rows = self._table.search().where(f"id = '{source_id}'").limit(1).to_list()
        if not rows:
            return None
        r = rows[0]
        r.pop("vector", None)
        return r

    async def all_sources(self) -> list[dict]:
        rows = self._table.search().limit(100000).to_list()
        for r in rows:
            r.pop("vector", None)
        return rows

    async def neighborhood(self, source_id: str, depth: int = 2, limit: int = 20):
        async with self.n.session() as s:
            result = await s.run(
                f"""
                MATCH (n:Source {{id:$id}})-[*1..{depth}]-(m:Source)
                RETURN DISTINCT m.id AS id, m.title AS title,
                  m.kind AS kind, m.tags AS tags, m.domain AS domain
                LIMIT $limit
                """,
                id=source_id, limit=limit,
            )
            return [dict(r) async for r in result]

    async def semantic_neighbors(self, source_id: str, k: int = 10):
        rows = self._table.search().where(f"id = '{source_id}'").limit(1).to_list()
        if not rows:
            return []
        vec = rows[0]["vector"]
        hits = (
            self._table.search(vec)
            .where(f"id != '{source_id}'")
            .limit(k)
            .to_list()
        )
        for h in hits:
            h.pop("vector", None)
        return [
            {**h, "score": max(0.0, 1.0 - float(h.get("_distance", 1.0)))}
            for h in hits
        ]

    async def orphans(self, limit: int = 50):
        async with self.n.session() as s:
            result = await s.run(
                """
                MATCH (n:Source)
                WHERE NOT (n)-[]-()
                RETURN n.id AS id, n.title AS title, n.kind AS kind,
                  n.tags AS tags, n.domain AS domain
                LIMIT $limit
                """,
                limit=limit,
            )
            return [dict(r) async for r in result]

    async def full_graph(self) -> dict:
        async with self.n.session() as s:
            src_q = await s.run(
                "MATCH (n:Source) RETURN n.id AS id, n.title AS title, "
                "n.kind AS kind, n.tags AS tags, n.domain AS domain, "
                "n.ingested_by AS ingested_by, n.year AS year, "
                "coalesce(n.triage_state, 'manual') AS triage_state"
            )
            nodes = [{**dict(r), "node_type": "Source"} async for r in src_q]

            goal_q = await s.run(
                "MATCH (g:Goal) RETURN g.id AS id, g.text AS title, "
                "g.domain AS domain, g.status AS status, "
                "g.created_at AS created_at, "
                "coalesce(g.sub_objective_texts, []) AS sub_objective_texts"
            )
            goals = [
                {
                    **dict(r),
                    "node_type": "Goal",
                    "kind": "goal",
                    "tags": ["goal"],
                    "ingested_by": "user",
                }
                async for r in goal_q
            ]
            nodes.extend(goals)

            so_q = await s.run(
                "MATCH (so:SubObjective) "
                "RETURN so.id AS id, so.text AS title, so.goal_id AS goal_id, "
                "so.slot AS slot"
            )
            subs = [
                {
                    **dict(r),
                    "node_type": "SubObjective",
                    "kind": "sub_objective",
                    "tags": ["sub_objective"],
                    "ingested_by": "user",
                }
                async for r in so_q
            ]
            nodes.extend(subs)

            links_q = await s.run(
                "MATCH (a)-[r]->(b) "
                "WHERE (a:Source OR a:Goal OR a:SubObjective) "
                "  AND (b:Source OR b:Goal OR b:SubObjective) "
                "RETURN a.id AS source, b.id AS target, type(r) AS rel, "
                "coalesce(r.confidence, r.relevance, 1.0) AS confidence"
            )
            links = [
                {**dict(r), "kind": _edge_kind_from_rel(r["rel"])}
                async for r in links_q
            ]
        # Mark orphans for visual differentiation (Source nodes only)
        linked_ids = {l["source"] for l in links} | {l["target"] for l in links}
        for n in nodes:
            if n.get("node_type") == "Source":
                n["orphan"] = n["id"] not in linked_ids
        return {"nodes": nodes, "links": links}

    # ------------------------------------------------------------------
    # Hybrid search — the main entry point for other lab skills
    # ------------------------------------------------------------------
    async def query(
        self,
        semantic: str | None = None,
        must_tags: list[str] | None = None,
        must_not_tags: list[str] | None = None,
        kinds: list[str] | None = None,
        domain: str | None = None,
        year_from: int | None = None,
        year_to: int | None = None,
        k: int = 20,
    ) -> list[dict]:
        # Build SQL-ish filter clause
        clauses = []
        if kinds:
            kind_list = ", ".join(f"'{k}'" for k in kinds)
            clauses.append(f"kind IN ({kind_list})")
        if domain:
            clauses.append(f"domain = '{domain}'")
        if year_from:
            clauses.append(f"year >= {int(year_from)}")
        if year_to:
            clauses.append(f"year <= {int(year_to)}")
        where = " AND ".join(clauses) if clauses else None

        if semantic:
            vec = await self.embed(semantic)
            q = self._table.search(vec)
        else:
            q = self._table.search()
        if where:
            q = q.where(where)

        hits = q.limit(k * 3 if (must_tags or must_not_tags) else k).to_list()

        # Tag filters post-hoc (LanceDB list-contains is backend-version dependent;
        # Python filter is simpler and fast at these cardinalities)
        if must_tags:
            hits = [h for h in hits if all(t in (h.get("tags") or []) for t in must_tags)]
        if must_not_tags:
            hits = [h for h in hits if not any(t in (h.get("tags") or []) for t in must_not_tags)]

        for h in hits[:k]:
            h.pop("vector", None)
            if "_distance" in h:
                h["score"] = max(0.0, 1.0 - float(h["_distance"]))
        return hits[:k]


def _edge_kind_from_rel(rel: str) -> str:
    """Map Neo4j relationship type to frontend edge kind for styling."""
    return {
        "LINKS_TO": "wikilink",
        "DISCOVERED_FROM": "discovered",
        "MOTIVATES": "motivates",
        "CITES": "cites",
        "DERIVED_FROM": "derived",
        "SUGGESTED": "suggested",
        "ADDRESSES": "addresses",
        "HAS_SUB_OBJECTIVE": "has_sub_objective",
    }.get(rel, "wikilink")
