"""
Natural-language query planner. Turns "take me to USDA peanut data from
2022-2024" into a hybrid query over the source store.
"""
import json
import re

from app.services.graph_store import GraphStore
from app.services.llm_router import complete

PLANNER_SYSTEM = """You translate natural-language questions about a lab's
knowledge canvas into a structured query plan. Sources in the canvas have
a `kind` which is one of: markdown, api_snapshot, paper, web_page,
dataset, experiment_log, image.

Return STRICT JSON with these keys (omit any you don't need):
  semantic_query: string — text to embed
  must_tags: [string]
  must_not_tags: [string]
  kinds: [string] — filter by source kind
  domain: string — e.g., "farming", "ml-research"
  year_from: int
  year_to: int

No extra keys. No code fences. No prose."""


async def plan_and_fly(store: GraphStore, utterance: str, k: int = 25):
    raw = await complete(f"Utterance: {utterance}", system=PLANNER_SYSTEM, temperature=0.1)
    plan = _extract_json(raw) or {"semantic_query": utterance}

    results = await store.query(
        semantic=plan.get("semantic_query") or utterance,
        must_tags=plan.get("must_tags", []),
        must_not_tags=plan.get("must_not_tags", []),
        kinds=plan.get("kinds", []),
        domain=plan.get("domain"),
        year_from=plan.get("year_from"),
        year_to=plan.get("year_to"),
        k=k,
    )

    return {
        "plan": plan,
        "node_ids": [r["id"] for r in results],
        "results": results,
    }


def _extract_json(text: str) -> dict | None:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
