"""
Autonomous link discovery. Scans orphan sources, asks the LLM if any of
their nearest semantic neighbors are genuinely related. Writes SUGGESTED
edges (distinct from user-created LINKS_TO edges).
"""
import json
import re

from app.services.graph_store import GraphStore
from app.services.llm_router import complete

SYSTEM = """You judge whether two sources in a research lab are
meaningfully related. Return STRICT JSON:
  {"confidence": 0.0-1.0, "relation": "<one of: supports, contradicts, extends, cites, related>", "reason": "<max 10 words>"}

Confidence means: should these be linked in a knowledge graph?
Be skeptical. Shared vocabulary is not a real link. Prefer precision."""


async def discover_links(store: GraphStore, threshold: float = 0.65, max_orphans: int = 20):
    orphans = await store.orphans(limit=max_orphans)
    suggestions = []

    for orphan in orphans:
        full = await store.get(orphan["id"])
        if not full:
            continue
        a_text = f"[{full['kind']}] {full['title']}\n{full.get('body_excerpt', '')[:1200]}"

        neighbors = await store.semantic_neighbors(orphan["id"], k=5)
        for cand in neighbors:
            b_full = await store.get(cand["id"])
            if not b_full:
                continue
            b_text = f"[{b_full['kind']}] {b_full['title']}\n{b_full.get('body_excerpt', '')[:1200]}"

            prompt = f"Source A:\n{a_text}\n\nSource B:\n{b_text}\n\nReturn JSON only."
            raw = await complete(prompt, system=SYSTEM, temperature=0.1)
            parsed = _extract_json(raw)
            if not parsed:
                continue
            conf = float(parsed.get("confidence", 0))
            if conf < threshold:
                continue

            # Write the SUGGESTED edge into Neo4j with the reason + confidence
            await store.link(
                orphan["id"], cand["id"], rel="SUGGESTED",
                props={"confidence": conf,
                       "relation": parsed.get("relation", "related"),
                       "reason": parsed.get("reason", "")},
            )
            suggestions.append({
                "source": orphan["id"], "target": cand["id"],
                "kind": "suggested", "confidence": conf,
                "relation": parsed.get("relation", ""),
                "reason": parsed.get("reason", ""),
            })
    return suggestions


def _extract_json(text: str) -> dict | None:
    m = re.search(r"\{[^{}]*\}", text, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
