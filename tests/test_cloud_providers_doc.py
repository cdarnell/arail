"""Pin the structure of docs/CLOUD_PROVIDERS.md.

This page is the user-facing onboarding ramp for the 10 cloud providers
wired into the min tier. The tests below catch documentation drift:
  - Every curated provider has a section
  - Every section has the required headers (Sign up / Get your key / Env var / Paste it)
  - Every external URL is https
"""
from __future__ import annotations

import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DOC = _REPO_ROOT / "docs" / "CLOUD_PROVIDERS.md"


CURATED_TEN_LABELS = {
    "claude":      "Anthropic Claude",
    "openai":      "OpenAI",
    "gemini":      "Google Gemini",
    "mistral":     "Mistral",
    "xai":         "xAI Grok",
    "openrouter":  "OpenRouter",
    "huggingface": "HuggingFace Inference",
    "nvidia":      "NVIDIA NIM",
    "together":    "Together AI",
    "groq":        "Groq",
}


def test_doc_exists():
    assert _DOC.exists(), f"docs/CLOUD_PROVIDERS.md is missing at {_DOC}"


def test_every_provider_has_a_section():
    """Every curated provider must have an H2 section with its label."""
    text = _DOC.read_text()
    h2s = set(re.findall(r"^## (.+?)$", text, re.MULTILINE))
    for pid, label in CURATED_TEN_LABELS.items():
        assert label in h2s, (
            f"Provider {pid!r} (label {label!r}) missing H2 section in "
            f"docs/CLOUD_PROVIDERS.md. Existing sections: {sorted(h2s)}"
        )


def test_every_section_has_required_bullets():
    """Each provider's section must mention sign-up, the env var, and
    where to find the key. The exact phrasing can drift; we check for the
    canonical bullet labels."""
    text = _DOC.read_text()
    # Split into sections by H2.
    sections = re.split(r"^## ", text, flags=re.MULTILINE)
    section_by_title = {}
    for sec in sections:
        first_nl = sec.find("\n")
        if first_nl == -1:
            continue
        title = sec[:first_nl].strip()
        body = sec[first_nl + 1:]
        section_by_title[title] = body

    for pid, label in CURATED_TEN_LABELS.items():
        body = section_by_title.get(label, "")
        assert body, f"No body found for {label!r}"
        # The canonical bullets — exact strings the section template uses.
        for needle in ("**Sign up:**", "**Get your key:**", "**Env var:**"):
            assert needle in body, (
                f"Provider section {label!r} missing {needle!r}. "
                "Sections must use the canonical bullet labels."
            )


def test_all_external_links_are_https():
    """Provider URLs must be https — keys are sensitive."""
    text = _DOC.read_text()
    # Find all link targets. Both <url> and [text](url) forms.
    bracketed = re.findall(r"<(https?://[^>]+)>", text)
    parened = re.findall(r"\]\((https?://[^)]+)\)", text)
    for url in bracketed + parened:
        # Skip /docs/* relative paths (already filtered by regex pattern).
        if url.startswith("https://"):
            continue
        if url.startswith("http://"):
            raise AssertionError(
                f"docs/CLOUD_PROVIDERS.md contains non-https URL: {url!r}"
            )


def test_each_provider_section_mentions_its_env_var():
    """Each section must mention the env var name (cross-check with
    _PROVIDER_KEY_ENVS so docs and code stay in sync)."""
    import sys
    if str(_REPO_ROOT / "src") not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT / "src"))
    from arail.portal import app as portal_app

    text = _DOC.read_text()
    sections = re.split(r"^## ", text, flags=re.MULTILINE)
    section_by_title = {}
    for sec in sections:
        first_nl = sec.find("\n")
        if first_nl == -1:
            continue
        title = sec[:first_nl].strip()
        body = sec[first_nl + 1:]
        section_by_title[title] = body

    for pid, label in CURATED_TEN_LABELS.items():
        env_var = portal_app._PROVIDER_KEY_ENVS.get(pid)
        assert env_var, f"{pid!r} not in _PROVIDER_KEY_ENVS"
        body = section_by_title.get(label, "")
        assert env_var in body, (
            f"docs/CLOUD_PROVIDERS.md section {label!r} doesn't mention "
            f"its env var {env_var!r}. Docs and code are out of sync."
        )
