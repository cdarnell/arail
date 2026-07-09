"""Programmatic WorldBundle fixture builder.

Builds a minimal, seal-valid ``dac.world-bundle/v1`` directory at test time,
computing every ``manifest.files{}`` sha256 from the actual bytes — no
hand-maintained hashes. Use ``face_overrides`` to inject arbitrary (including
hostile) face.json content such as ``theme`` blocks; the bundle stays
seal-VALID because the manifest is written after the overrides are applied.
That is exactly the threat model for world-theme validation: a hostile author
can seal whatever they like.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Optional

SEALED_FILES = (
    "terms.json", "spec.json", "roster.json",
    "face.json", "agenda.json", "drift-report.json",
)


def make_bundle(
    parent: Path,
    slug: str = "testworld",
    display_name: str = "Test World",
    face_overrides: Optional[Dict[str, Any]] = None,
    *,
    drop_face_keys: tuple = (),
    terms_list: Optional[list] = None,
    categories: Optional[list] = None,
) -> Path:
    """Create ``parent/<slug>/`` as a sealed bundle and return its path.

    ``terms_list`` / ``categories`` override the single default term for
    tests that need a multi-term graph (each term: slug/term/category/short/
    definition/example/related/source); every term's category must appear in
    ``categories`` or the built bundle won't pass check_categories.
    """
    bundle = parent / slug
    bundle.mkdir(parents=True, exist_ok=True)

    term_items = terms_list if terms_list is not None else [
        {
            "slug": "alpha-term",
            "term": "Alpha Term",
            "category": "basics",
            "short": "A minimal fixture term.",
            "definition": "A term that exists so the gate has something to pass.",
            "example": "Alpha Term appears in tests.",
            "related": [],
            "source": "https://example.test/spec",
        }
    ]
    cats = categories if categories is not None else [{"id": "basics", "label": "Basics"}]
    slugs = [t["slug"] for t in term_items]
    terms = {"version": 1, "terms": term_items}
    spec = {
        "slug": slug,
        "display_name": display_name,
        "categories": cats,
        "knowledge_sources": [
            {"kind": "url", "ref": "https://example.test/spec", "trust": "primary"}
        ],
    }
    roster = {"world": slug, "declared": slugs, "gaps": []}
    agenda = {"schema": "dac.world-agenda/v1", "world": slug, "watches": []}
    drift = {
        "schema": "dac.world-drift/v1",
        "world": slug,
        "declared": slugs,
        "compiled": slugs,
        "missing": [],
        "undeclared": [],
    }
    face: Dict[str, Any] = {
        "schema": "dac.world-face/v1",
        "world": slug,
        "name": display_name,
        "tagline": f"A {display_name} World.",
        "palette_hint": "slate-violet",
        "domain_framing": f"This lab studies {display_name}.",
        "vocabulary_register": "Use the World's own terms.",
        "provenance_tier": "sourced",
        "provenance_counts": {"model": 0, "sourced": 1, "total": 1},
    }
    if face_overrides:
        face.update(face_overrides)
    for key in drop_face_keys:
        face.pop(key, None)

    contents = {
        "terms.json": terms,
        "spec.json": spec,
        "roster.json": roster,
        "face.json": face,
        "agenda.json": agenda,
        "drift-report.json": drift,
    }
    hashes: Dict[str, str] = {}
    for fname, payload in contents.items():
        raw = json.dumps(payload, indent=2).encode("utf-8")
        (bundle / fname).write_bytes(raw)
        hashes[fname] = hashlib.sha256(raw).hexdigest()

    manifest = {
        "schema": "dac.world-bundle/v1",
        "bundle_version": 1,
        "world": slug,
        "display_name": display_name,
        "created_at": "1970-01-01T00:00:00.000Z",
        "world_sha256": hashes["terms.json"],
        "files": hashes,
        "provenance_tier": "sourced",
        "provenance_counts": {"model": 0, "sourced": 1, "total": 1},
        "refresh_cadence": "see agenda.json",
        "compat": {"bundle_schema": 1, "terms_schema": 1},
    }
    (bundle / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return bundle


# A valid dark scheme with comfortable contrast, reusable across tests.
VALID_DARK = {
    "bg": "#1a0f16", "surface": "#241521", "surface2": "#2e1b2a",
    "border": "#3d2438", "text": "#eedbe8", "muted": "#b394ad",
    "accent": "#ff6fae", "accent2": "#8fd3ff", "positive": "#7ee2a8",
    "warn": "#ffc46b", "danger": "#ff5c7a", "info": "#8fd3ff",
}


def valid_theme(personality: str = "playful") -> Dict[str, Any]:
    return {
        "schema": "dac.world-theme/v1",
        "personality": personality,
        "dark": dict(VALID_DARK),
        "light": None,
    }
