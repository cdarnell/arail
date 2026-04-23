"""Curator agent — finds and caches high-quality resources for a goal.

This agent:
1. Takes a parsed goal
2. Generates search queries using the local LLM
3. Requests network consent for each URL via the ConsentStore
4. Fetches approved URLs and caches content locally
5. Summarises findings using the local LLM
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from arail.agents.consent import ConsentStore
from arail.config import DATA_DIR


CACHE_DIR = DATA_DIR / "cache"

# Curated source registry — domains known to have high-quality,
# freely-available data.  Agents will prefer these.
TRUSTED_SOURCES: Dict[str, Dict[str, str]] = {
    "quickstats.nass.usda.gov": {
        "name": "USDA NASS",
        "category": "agriculture",
    },
    "www.ncei.noaa.gov": {
        "name": "NOAA Climate",
        "category": "weather",
    },
    "sdmdataaccess.sc.egov.usda.gov": {
        "name": "NRCS Soil Survey",
        "category": "soil",
    },
    "api.weather.gov": {
        "name": "NWS Forecasts",
        "category": "weather",
    },
    "arxiv.org": {
        "name": "arXiv",
        "category": "research",
    },
    "huggingface.co": {
        "name": "Hugging Face",
        "category": "ml",
    },
    "paperswithcode.com": {
        "name": "Papers With Code",
        "category": "ml",
    },
}


class CuratorAgent:
    """Finds and caches resources relevant to a user's goal."""

    def __init__(self, consent: ConsentStore | None = None) -> None:
        self.consent = consent or ConsentStore()
        CACHE_DIR.mkdir(parents=True, exist_ok=True)

    def propose_sources(self, parsed_goal: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Given a parsed goal, return a list of proposed source fetches.

        Each entry is a consent request the portal will show to the user.
        Blocked entirely in airgapped mode.
        """
        import os
        if os.getenv("ARAIL_MODE", "airgapped").lower() == "airgapped":
            return []
        domain = parsed_goal.get("domain", "general")
        proposals: List[Dict[str, Any]] = []

        for host, meta in TRUSTED_SOURCES.items():
            # Simple relevance matching — a real implementation would
            # use the LLM to rank sources against the goal.
            if meta["category"] in ("research",):
                proposals.append(self._make_proposal(host, meta, parsed_goal))
            if domain == "farming" and meta["category"] in (
                "agriculture", "weather", "soil"
            ):
                proposals.append(self._make_proposal(host, meta, parsed_goal))
            if domain == "ml-research" and meta["category"] in ("ml",):
                proposals.append(self._make_proposal(host, meta, parsed_goal))

        return proposals

    def submit_proposals(self, proposals: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Submit each proposal to the consent store.  Returns the
        consent request records (pending / auto_approved)."""
        results = []
        for p in proposals:
            req = self.consent.request_access(
                url=p["url"],
                reason=p["reason"],
                agent="curator",
            )
            results.append(req)
        return results

    def fetch_approved(self, request_id: str, url: str) -> Optional[str]:
        """Fetch a URL that has been approved.  Caches the result.
        Hard-blocked in airgapped mode regardless of approval."""
        import os
        if os.getenv("ARAIL_MODE", "airgapped").lower() == "airgapped":
            return None
        # Check cache first
        cached = self._cache_path(url)
        if cached.exists():
            return cached.read_text()

        import requests  # only imported when actually fetching
        try:
            resp = requests.get(url, timeout=30,
                                headers={"User-Agent": "Arail/0.1"})
            resp.raise_for_status()
            content = resp.text
            cached.write_text(content)
            return content
        except Exception as e:
            return None

    # ── Internal ─────────────────────────────────────────────────────

    def _make_proposal(self, host: str, meta: Dict[str, str],
                        goal: Dict[str, Any]) -> Dict[str, Any]:
        goal_text = goal.get("goal", goal.get("primary_objective", ""))
        return {
            "url": f"https://{host}/",
            "source_name": meta["name"],
            "category": meta["category"],
            "reason": f"Curate {meta['category']} data for goal: {goal_text}",
        }

    @staticmethod
    def _cache_path(url: str) -> Path:
        h = hashlib.sha256(url.encode()).hexdigest()[:16]
        domain = urlparse(url).netloc.replace(".", "_")
        return CACHE_DIR / f"{domain}_{h}.txt"
