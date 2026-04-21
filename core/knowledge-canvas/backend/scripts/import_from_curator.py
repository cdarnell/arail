"""
One-shot import of sources the Data Curator skill already knows about.

Walks a domain directory (e.g., domains/farming/) and turns every entry
in data-sources.json (or config.json's data_sources list) into a Source
record in the canvas. Safe to run repeatedly — ingest is idempotent.

Usage:
    python -m scripts.import_from_curator /path/to/lab/domains/farming
    python -m scripts.import_from_curator /path/to/lab/domains/farming --domain farming
"""
import argparse
import asyncio
import json
import os
from pathlib import Path

from app.models.source import IngestRequest
from app.services.adapters import adapt
from app.services.graph_store import GraphStore


def discover_source_configs(domain_dir: Path) -> tuple[list[dict], str]:
    """
    Returns (data_sources_list, domain_name).
    Supports both layouts seen in the lab:
      - domain_dir/config.json with {"data_sources": [...], "domain": "..."}
      - domain_dir/data-sources.json with just [{...}, {...}]
    """
    config_path = domain_dir / "config.json"
    if config_path.exists():
        cfg = json.loads(config_path.read_text())
        return cfg.get("data_sources", []), cfg.get("domain", domain_dir.name)

    ds_path = domain_dir / "data-sources.json"
    if ds_path.exists():
        ds = json.loads(ds_path.read_text())
        return (ds if isinstance(ds, list) else ds.get("data_sources", [])), domain_dir.name

    raise FileNotFoundError(
        f"No config.json or data-sources.json in {domain_dir}"
    )


async def main(domain_dir: Path, domain_override: str | None):
    data_sources, domain = discover_source_configs(domain_dir)
    if domain_override:
        domain = domain_override

    print(f"Importing {len(data_sources)} sources from domain '{domain}'…")

    store = GraphStore(
        lance_path=os.getenv("LANCE_PATH", "./data/lance"),
        neo4j_uri=os.getenv("NEO4J_URI", "bolt://localhost:7687"),
        neo4j_auth=(os.getenv("NEO4J_USER", "neo4j"),
                    os.getenv("NEO4J_PASSWORD", "changeme-please")),
    )
    await store.init()

    imported = 0
    for ds in data_sources:
        req = IngestRequest(
            kind="dataset" if ds.get("type") == "document_database" else "api_snapshot",
            title=ds.get("name") or ds.get("source_name", "Untitled source"),
            uri=ds.get("url") or ds.get("path") or ds["name"],
            body_excerpt=_excerpt_from_config(ds),
            tags=[domain] + ds.get("available_data", [])[:5] + _tags_from_config(ds),
            domain=domain,
            ingested_by="curator",
            meta={
                "type": ds.get("type"),
                "auth_required": ds.get("auth_required"),
                "available_data": ds.get("available_data"),
                "historical_years": ds.get("historical_years"),
                "geographic_coverage": ds.get("geographic_coverage"),
            },
        )
        source = adapt(req)
        await store.upsert(source)
        imported += 1
        if imported % 10 == 0:
            print(f"  {imported}/{len(data_sources)}")

    # Also pull example_goals as markdown-kind seed sources if present
    config_path = domain_dir / "config.json"
    if config_path.exists():
        cfg = json.loads(config_path.read_text())
        for goal in cfg.get("example_goals", []):
            req = IngestRequest(
                kind="markdown",
                title=f"Example goal: {goal[:60]}",
                uri=f"goal::{domain}::{hash(goal) & 0xffffffff:x}",
                body_excerpt=goal,
                tags=[domain, "example-goal"],
                domain=domain,
                ingested_by="curator",
            )
            await store.upsert(adapt(req))
            imported += 1

    await store.close()
    print(f"Done. Imported {imported} sources into the canvas.")


def _excerpt_from_config(ds: dict) -> str:
    parts = [ds.get("description", "")]
    if ds.get("available_data"):
        parts.append("Available data: " + ", ".join(ds["available_data"]))
    if ds.get("geographic_coverage"):
        parts.append(f"Coverage: {ds['geographic_coverage']}")
    if ds.get("historical_years"):
        parts.append(f"History: {ds['historical_years']} years")
    if ds.get("temporal_resolution"):
        parts.append(f"Resolution: {ds['temporal_resolution']}")
    return "\n".join(p for p in parts if p)[:4000]


def _tags_from_config(ds: dict) -> list[str]:
    tags = []
    if ds.get("auth_required") is False:
        tags.append("open-access")
    if ds.get("type"):
        tags.append(ds["type"].replace("_", "-"))
    return tags


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("domain_dir", type=Path,
                        help="Path to a lab domain directory, e.g., domains/farming")
    parser.add_argument("--domain", type=str, default=None,
                        help="Override domain name (defaults to dir name or config)")
    args = parser.parse_args()
    asyncio.run(main(args.domain_dir, args.domain))
