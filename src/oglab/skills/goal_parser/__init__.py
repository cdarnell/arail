"""Goal Parser — converts natural language goals into structured objectives."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from oglab.router import ModelRouter


DOMAIN_KEYWORDS: Dict[str, list[str]] = {
    "farming": ["crop", "farm", "yield", "soil", "harvest", "peanut",
                 "corn", "wheat", "garden", "irrigation"],
    "ml-research": ["model", "training", "accuracy", "dataset", "neural",
                     "llm", "fine-tune", "gpu", "benchmark"],
    "culinary": ["cook", "recipe", "cuisine", "pastry", "dish",
                  "ingredient", "technique", "ferment"],
    "business": ["revenue", "growth", "customer", "market", "sales",
                  "profit", "scale", "startup"],
    "health": ["fitness", "health", "diet", "exercise", "wellness",
                "strength", "nutrition"],
    "education": ["learn", "skill", "knowledge", "course", "master",
                   "understand", "study"],
}


def infer_domain(text: str) -> str:
    lower = text.lower()
    scores = {
        domain: sum(1 for kw in kws if kw in lower)
        for domain, kws in DOMAIN_KEYWORDS.items()
    }
    best = max(scores, key=scores.get, default="general")  # type: ignore[arg-type]
    return best if scores.get(best, 0) > 0 else "general"


def extract_entities(text: str) -> Dict[str, list[str]]:
    entities: Dict[str, list[str]] = {
        "locations": [], "subjects": [], "metrics": [], "timeframes": [],
    }
    locs = re.findall(r"in\s+([A-Za-z\s]+?)(?:[.,;]|$)", text)
    if locs:
        entities["locations"] = [l.strip() for l in locs]
    subjs = re.findall(
        r"(?:grow|build|learn|create|master)\s+(?:the\s+)?([A-Za-z\s]+?)(?:\s+in\s+|$)",
        text, re.IGNORECASE,
    )
    if subjs:
        entities["subjects"] = [s.strip() for s in subjs]
    return entities


class GoalParser:
    """Parse a natural-language goal into a structured dict."""

    def __init__(self, router: ModelRouter | None = None) -> None:
        self.router = router  # lazy — only created if actually used

    def _get_router(self) -> ModelRouter:
        if self.router is None:
            self.router = ModelRouter()
        return self.router

    def parse(self, goal_text: str,
              context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        prompt = (
            "Parse this goal into a structured JSON object:\n\n"
            f"Goal: {goal_text}\n\n"
            "Return ONLY valid JSON with keys: goal, domain, "
            "primary_objective, sub_objectives (list), success_metrics (dict), "
            "timeline, constraints (list), resources_needed (list)."
        )
        try:
            resp = self._get_router().complete(prompt, max_tokens=800,
                                               temperature=0.5)
            text = resp.text
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                text = text.split("```")[1].split("```")[0]
            parsed = json.loads(text.strip())
        except Exception:
            parsed = self._heuristic(goal_text)

        parsed.setdefault("domain", infer_domain(goal_text))
        parsed["extracted_entities"] = extract_entities(goal_text)
        if context:
            parsed["context"] = context
        parsed["parsed_at"] = datetime.now(timezone.utc).isoformat()
        parsed["confidence"] = self._confidence(parsed)
        return parsed

    def parse_offline(self, goal_text: str) -> Dict[str, Any]:
        """Heuristic-only parsing — no LLM needed (works airgapped with no
        model loaded)."""
        parsed = self._heuristic(goal_text)
        parsed["extracted_entities"] = extract_entities(goal_text)
        parsed["parsed_at"] = datetime.now(timezone.utc).isoformat()
        parsed["confidence"] = self._confidence(parsed)
        return parsed

    # ------------------------------------------------------------------
    def _heuristic(self, goal_text: str) -> Dict[str, Any]:
        domain = infer_domain(goal_text)

        # Split on common conjunctions / punctuation to extract sub-goals
        parts = re.split(r"[;,]\s*|\band\b|\bor\b|\bthen\b", goal_text, flags=re.IGNORECASE)
        parts = [p.strip() for p in parts if len(p.strip()) > 8]
        if len(parts) > 1:
            primary = parts[0]
            sub_objectives = parts[1:]
        else:
            primary = goal_text
            sub_objectives = []

        # Infer resources from domain
        resource_hints: Dict[str, list[str]] = {
            "ml-research": ["local LLM", "GPU or AirLLM", "research papers"],
            "farming": ["weather data", "soil data", "crop databases"],
            "culinary": ["recipe databases", "ingredient sources"],
            "business": ["market data", "analytics tools"],
            "health": ["health metrics", "fitness tracking"],
            "education": ["learning materials", "practice exercises"],
        }
        resources = resource_hints.get(domain, ["local knowledge base"])

        return {
            "goal": goal_text,
            "domain": domain,
            "primary_objective": primary,
            "sub_objectives": sub_objectives,
            "success_metrics": {"research_cycles": "≥ 1 complete", "findings": "actionable"},
            "timeline": "ongoing",
            "constraints": ["local-first", "airgapped by default"],
            "resources_needed": resources,
            "parsing_method": "heuristic",
        }

    @staticmethod
    def _confidence(parsed: Dict[str, Any]) -> float:
        c = 0.7
        if not parsed.get("success_metrics"):
            c -= 0.2
        if not parsed.get("timeline") or parsed["timeline"] == "unspecified":
            c -= 0.1
        if parsed.get("domain", "general") == "general":
            c -= 0.1
        return round(min(1.0, max(0.0, c)), 2)
