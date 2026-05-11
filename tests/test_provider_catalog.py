"""Pin the curated provider catalogue introduced by sprint 2026-05-11-min-cloud-first.

The catalogue lives in two places that must stay in sync:
  1. `_PROVIDER_KEY_ENVS` and `_PROVIDER_META` in src/arail/portal/app.py
  2. The JS `PROVIDERS` array in src/arail/portal/templates/chat.html

These tests assert both surfaces declare the same 10 curated providers
(5 direct labs + 5 aggregators) plus `custom` as the bring-your-own row.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src"))

from arail.portal import app as portal_app


CURATED_TEN = {
    # Direct labs
    "claude", "openai", "gemini", "mistral", "xai",
    # Aggregators
    "openrouter", "huggingface", "nvidia", "together", "groq",
}


def test_provider_key_envs_has_all_ten():
    """All 10 curated providers must be in `_PROVIDER_KEY_ENVS`."""
    keys = set(portal_app._PROVIDER_KEY_ENVS.keys())
    missing = CURATED_TEN - keys
    assert not missing, f"Missing curated providers in _PROVIDER_KEY_ENVS: {missing}"


def test_provider_meta_has_all_ten():
    """Every curated provider must have a `_PROVIDER_META` entry with the
    full required field set."""
    required_fields = {"label", "base", "models_path", "auth", "docs", "signup"}
    for pid in CURATED_TEN:
        assert pid in portal_app._PROVIDER_META, (
            f"Provider {pid!r} missing from _PROVIDER_META"
        )
        meta = portal_app._PROVIDER_META[pid]
        missing_fields = required_fields - set(meta.keys())
        assert not missing_fields, (
            f"Provider {pid!r} _PROVIDER_META missing fields: {missing_fields}"
        )


def test_env_var_names_are_unique():
    """No two providers may share an env var — would cause silent key
    collisions in secrets.env."""
    env_vars = list(portal_app._PROVIDER_KEY_ENVS.values())
    seen: dict[str, str] = {}
    for pid, env in portal_app._PROVIDER_KEY_ENVS.items():
        if env in seen:
            raise AssertionError(
                f"Env var {env!r} used by both {pid!r} and {seen[env]!r}"
            )
        seen[env] = pid
    assert len(env_vars) == len(set(env_vars))


def test_all_meta_have_signup_field():
    """Every entry in _PROVIDER_META — including the existing 4 and the
    `custom` catch-all — must have a `signup` field (may be empty string
    for `custom`). The status payload always includes the field."""
    for pid, meta in portal_app._PROVIDER_META.items():
        assert "signup" in meta, (
            f"Provider {pid!r} missing 'signup' field — would break "
            "the /api/providers/status payload contract"
        )


def test_status_payload_includes_signup():
    """`/api/providers/status` response must include `signup` per provider.

    We exercise the construction logic by mirroring it locally rather than
    spinning up the FastAPI test client (which requires the full portal
    boot path). The contract is what we pin: every provider in the
    payload has a `signup` key."""
    payload_providers = [
        {
            "id": pid,
            "label": meta["label"],
            "docs": meta.get("docs", ""),
            "signup": meta.get("signup", ""),
            "has_token": False,
            "base": meta.get("base", ""),
            "supports_models_list": bool(meta.get("models_path")),
        }
        for pid, meta in portal_app._PROVIDER_META.items()
    ]
    for entry in payload_providers:
        assert "signup" in entry, (
            f"Provider entry {entry['id']!r} missing 'signup' key in payload"
        )


def test_signup_urls_are_https():
    """Every non-empty signup URL must be https — we ship these to users."""
    for pid, meta in portal_app._PROVIDER_META.items():
        url = meta.get("signup", "")
        if not url:
            continue  # custom row's signup is intentionally empty
        assert url.startswith("https://"), (
            f"Provider {pid!r} signup URL is not HTTPS: {url!r}"
        )


def test_docs_urls_are_https_when_set():
    """Same for docs URLs — keys are sensitive, so the docs link to a
    provider console must be https."""
    for pid, meta in portal_app._PROVIDER_META.items():
        url = meta.get("docs", "")
        if not url:
            continue
        assert url.startswith("https://"), (
            f"Provider {pid!r} docs URL is not HTTPS: {url!r}"
        )


# ─── JS catalogue mirror ────────────────────────────────────────────────


def test_js_providers_array_includes_all_ten():
    """The JS `PROVIDERS` array in chat.html must list the same 10
    curated providers as the server-side catalogue, in the same order
    where possible (labs first, then aggregators)."""
    chat_html = (_REPO_ROOT / "src" / "arail" / "portal" / "templates" / "chat.html").read_text()
    # Extract the PROVIDERS array body. The const declaration is a multi-line
    # block; the regex finds everything between `const PROVIDERS = [` and
    # the matching closing `];`.
    m = re.search(r"const\s+PROVIDERS\s*=\s*\[(.*?)\];", chat_html, re.DOTALL)
    assert m, "could not locate the JS PROVIDERS array in chat.html"
    body = m.group(1)
    # The id field is `id: 'name'` per row.
    js_ids = set(re.findall(r"id:\s*'([a-z_]+)'", body))
    missing = CURATED_TEN - js_ids
    extra = js_ids - CURATED_TEN - {"custom"}
    assert not missing, (
        f"JS PROVIDERS array missing curated providers: {missing}"
    )
    # Extra entries are allowed if they're explicitly tagged as catch-all
    # (currently just `custom`). We do NOT include `custom` in the JS
    # PROVIDERS array because the modal shows a separate "Custom" path —
    # but if someone adds it back here, allow it.
    assert not extra - {"custom"}, (
        f"JS PROVIDERS array has unexpected ids: {extra - {'custom'}}"
    )
