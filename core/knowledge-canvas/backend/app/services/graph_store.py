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
                    n.ingested_by=$ingested_by
                """,
                id=source.id, kind=source.kind, title=source.title,
                uri=source.uri, tags=source.tags, year=source.year or 0,
                domain=source.domain or "", ingested_by=source.ingested_by,
            )
        return source

    async def remove(self, source_id: str) -> bool:
        self._table.delete(f"id = '{source_id}'")
        async with self.n.session() as s:
            await s.run("MATCH (n:Source {id:$id}) DETACH DELETE n", id=source_id)
        return True

    # ------------------------------------------------------------------
    async def link(self, src_id: str, dst_id: str, rel: str, props: dict | None = None):
        """
        Create a typed edge. `rel` is one of:
          LINKS_TO, DISCOVERED_FROM, MOTIVATES, CITES, DERIVED_FROM, SUGGESTED
        """
        props = props or {}
        async with self.n.session() as s:
            await s.run(
                f"MATCH (a:Source {{id:$src}}), (b:Source {{id:$dst}}) "
                f"MERGE (a)-[r:{rel}]->(b) SET r += $props",
                src=src_id, dst=dst_id, props=props,
            )

    async def unlink(self, src_id: str, dst_id: str, rel: str):
        async with self.n.session() as s:
            await s.run(
                f"MATCH (a:Source {{id:$src}})-[r:{rel}]->(b:Source {{id:$dst}}) DELETE r",
                src=src_id, dst=dst_id,
            )

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
            nodes_q = await s.run(
                "MATCH (n:Source) RETURN n.id AS id, n.title AS title, "
                "n.kind AS kind, n.tags AS tags, n.domain AS domain, "
                "n.ingested_by AS ingested_by, n.year AS year"
            )
            nodes = [dict(r) async for r in nodes_q]
            links_q = await s.run(
                "MATCH (a:Source)-[r]->(b:Source) "
                "RETURN a.id AS source, b.id AS target, type(r) AS rel, "
                "coalesce(r.confidence, 1.0) AS confidence"
            )
            links = [
                {**dict(r), "kind": _edge_kind_from_rel(r["rel"])}
                async for r in links_q
            ]
        # Mark orphans for visual differentiation
        linked_ids = {l["source"] for l in links} | {l["target"] for l in links}
        for n in nodes:
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
    }.get(rel, "wikilink")
