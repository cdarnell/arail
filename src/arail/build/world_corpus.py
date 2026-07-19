"""DaC World → Nucleus training corpus.

Pulls ARAIL-approved terms from a mounted-then-remounted DaC World and turns
them into a trained model — bypassing Nucleus's orchestrator/KICE entirely,
because World content has already been through DaC's compile-time gate
(sourced, closed, categorized) and ARAIL's Compiled-KB human-approval gate;
re-running KICE's heuristic keyword tagging over it would only downgrade it.

Two approval layers matter here (see docs/persistence.md-adjacent design
notes in the World-corpus plan): DaC's gate proves *form*; ARAIL's
Compiled-KB gate (``arail.compiled_kb``) proves *retrieval eligibility*.
This module only trusts the second — a term must be in
``compiled_kb.approved_paths()`` to be pulled, regardless of how confidently
DaC sourced it.

Content survives remounting a different World: ``world_mount.mount()``
sweeps the *staged* KB markdown for every non-current World, but the bundle
is also copied byte-for-byte into ``WORLDS_DIR/<slug>/`` (the switcher
catalog) — this module reads terms from THAT copy, not from staged
markdown, so a World does not need to stay mounted once its terms are
approved.
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

log = logging.getLogger(__name__)

# The craft/technique categories a "domain expert" bake should train on —
# excludes business/business-entity/web-platform/session-workflow, which are
# operator- or client-specific rather than general domain expertise.
CRAFT_CATEGORIES = ("genres", "gear", "exposure", "light", "composition",
                    "post-production")

# Reused verbatim from qukaizen-nucleus's docs/EXTRACTION_LAYERS_GUIDE.md —
# layer only affects RAFT distractor/oracle proximity (a quality heuristic),
# never gating, so an approximate re-derivation against already-curated text
# is legitimate reuse, not a KICE reimplementation.
_L6_AMBIGUITY_CUES = ("it depends", "varies by", "context dependent",
                      "implementation defined", "undefined behavior",
                      "unspecified", "ambiguous", "not clearly documented",
                      "no universal", "no single")
_L5_REASONING_CUES = ("because", "therefore", "however", "on the other hand",
                      "trade-off", "tradeoff", "the reason is", "this implies",
                      "as a result", "which means")


def _safe_term_slug(raw: Any) -> str:
    """Mirror arail.compiled_kb._safe_term_slug exactly — the staged term
    page filenames (and therefore approved_paths entries) were written with
    this sanitizer; reconstructing the path any other way risks silently
    missing approved terms with unusual slug characters."""
    return re.sub(r"[^a-z0-9-]+", "-", str(raw).lower()).strip("-")[:80]


# ── bundle resolution ──────────────────────────────────────────────

def resolve_world_bundle(world_slug: str,
                         worlds_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Read terms.json + spec.json from the switcher catalog copy —
    WORLDS_DIR/<slug>/ — which persists independent of which World is
    currently mounted (see module docstring)."""
    if worlds_dir is None:
        from arail.config import WORLDS_DIR
        worlds_dir = Path(WORLDS_DIR)
    bundle_dir = worlds_dir / world_slug
    terms_path = bundle_dir / "terms.json"
    spec_path = bundle_dir / "spec.json"
    if not terms_path.exists():
        raise FileNotFoundError(
            f"no World bundle at {bundle_dir} — mount it at least once "
            f"(./arailctl world mount <bundle-dir>) so it's adopted into "
            f"the catalog")
    terms_data = json.loads(terms_path.read_text())
    spec_data = json.loads(spec_path.read_text()) if spec_path.exists() else {}
    terms = terms_data.get("terms", terms_data if isinstance(terms_data, list) else [])
    return {"terms": terms, "spec": spec_data, "bundle_dir": bundle_dir}


def all_categories(world_slug: str,
                   worlds_dir: Optional[Path] = None) -> List[str]:
    """Every category id declared in this World's own spec.json, in spec
    order — the generalized "nothing specified" default. Replaces a fixed
    tuple like CRAFT_CATEGORIES (which encodes a photography-specific
    judgment call and is wrong for every other World) with whatever THIS
    World actually declares."""
    bundle = resolve_world_bundle(world_slug, worlds_dir=worlds_dir)
    return [c.get("id") for c in bundle["spec"].get("categories", [])
            if isinstance(c, dict) and c.get("id")]


def category_breakdown(
    world_slug: str, *,
    worlds_dir: Optional[Path] = None,
    pkb_root: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """Per-category term counts for a build-scope picker: spec order, each
    entry {id, label, term_count, approved_count}. Pure aggregation over
    terms.json + compiled_kb.approved_paths() — no new approval semantics,
    just counting what pull_approved_terms would otherwise return as full
    term objects. approved_count fails closed to 0 (via approved_paths'
    own fail-closed behavior) rather than raising, so a KB read error never
    crashes the picker — it just shows nothing as approved yet."""
    from arail import compiled_kb

    bundle = resolve_world_bundle(world_slug, worlds_dir=worlds_dir)
    approved = compiled_kb.approved_paths(pkb_root=pkb_root)

    total_by_cat: Dict[str, int] = {}
    approved_by_cat: Dict[str, int] = {}
    for term in bundle["terms"]:
        if not isinstance(term, dict):
            continue
        cat = term.get("category", "")
        total_by_cat[cat] = total_by_cat.get(cat, 0) + 1
        slug = _safe_term_slug(term.get("slug", ""))
        if not slug:
            continue
        rel_path = f"sources/world-{world_slug}/terms/{slug}.md"
        if rel_path in approved:
            approved_by_cat[cat] = approved_by_cat.get(cat, 0) + 1

    out: List[Dict[str, Any]] = []
    for cat in bundle["spec"].get("categories", []):
        if not isinstance(cat, dict) or not cat.get("id"):
            continue
        cid = cat["id"]
        out.append({
            "id": cid,
            "label": cat.get("label") or cid,
            "term_count": total_by_cat.get(cid, 0),
            "approved_count": approved_by_cat.get(cid, 0),
        })
    return out


# ── approved + filtered pull ────────────────────────────────────────

def pull_approved_terms(
    world_slug: str, *,
    categories: Iterable[str] = CRAFT_CATEGORIES,
    worlds_dir: Optional[Path] = None,
    pkb_root: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """Deterministic pull: every term in WORLDS_DIR/<slug>/terms.json whose
    category is in *categories* AND whose staged-page path is in
    compiled_kb.approved_paths() — never a fuzzy/semantic search, since a
    training corpus needs complete, reproducible coverage, not top-K.

    Sorted by the World's own spec.json category order, then by slug within
    a category, mirroring the order world_mount stages term pages in.
    """
    from arail import compiled_kb

    bundle = resolve_world_bundle(world_slug, worlds_dir=worlds_dir)
    approved = compiled_kb.approved_paths(pkb_root=pkb_root)
    cat_set = set(categories)
    spec_categories = [c.get("id") for c in bundle["spec"].get("categories", [])
                       if isinstance(c, dict) and c.get("id")]
    cat_order = {c: i for i, c in enumerate(spec_categories)}

    out: List[Dict[str, Any]] = []
    for term in bundle["terms"]:
        if not isinstance(term, dict):
            continue
        category = term.get("category", "")
        if category not in cat_set:
            continue
        slug = _safe_term_slug(term.get("slug", ""))
        if not slug:
            continue
        rel_path = f"sources/world-{world_slug}/terms/{slug}.md"
        if rel_path not in approved:
            continue
        out.append(term)

    out.sort(key=lambda t: (cat_order.get(t.get("category", ""), 999),
                            _safe_term_slug(t.get("slug", ""))))
    return out


# ── term → KICEExample mapping ──────────────────────────────────────

def _infer_layer(term: Dict[str, Any]) -> int:
    """1 (default) unless the term's own text carries L5/L6 cues."""
    text = f"{term.get('definition','')} {term.get('example','')}".lower()
    if any(cue in text for cue in _L6_AMBIGUITY_CUES):
        return 6
    hits = sum(1 for cue in _L5_REASONING_CUES if cue in text)
    if hits >= 2:
        return 5
    related = term.get("related")
    if isinstance(related, list) and len(related) >= 4:
        return 4
    return 1


def term_to_kice_example(term: Dict[str, Any], *,
                         id_prefix: str = "world") -> Dict[str, Any]:
    """Field mapping against nucleus's KICEExample (synthesizer/service.py):
    id, subdomain (=category — the axis RAFT's distractor selection groups
    on), layer, source_type, title, content, reasoning_prompt, quality_score.
    """
    slug = _safe_term_slug(term.get("slug", ""))
    name = term.get("term") or slug
    parts = [f"{name} — {term.get('short','')}".strip(" —"),
             term.get("definition", "")]
    if term.get("example"):
        parts.append(f"Example: {term['example']}")
    source = term.get("source", "")
    if source:
        parts.append(f"Source: {source}")
    content = "\n\n".join(p for p in parts if p)

    return {
        "id": f"{id_prefix}-{slug}",
        "subdomain": term.get("category", "general"),
        "layer": _infer_layer(term),
        "source_type": "world_term",
        "title": name,
        "content": content,
        "reasoning_prompt": (
            f"Explain {name} in photography: what it is, why it matters, "
            f"and how it's used."),
        "quality_score": 0.7 if source else 0.5,
    }


def chunk(items: List[Any], size: int = 15) -> List[List[Any]]:
    return [items[i:i + size] for i in range(0, len(items), size)]


def tag_source(records: List[Dict[str, Any]], tag: str) -> List[Dict[str, Any]]:
    """Tag each trainer record with a top-level 'source' field — Trainer's
    curriculum_weights (default {"tier2": 2.5}) auto-oversamples whichever
    tag matches, with zero Trainer-side changes."""
    for r in records:
        r["source"] = tag
    return records


# ── orchestration ───────────────────────────────────────────────────

def build_world_corpus(
    world_slug: str,
    run_id: str,
    *,
    categories: Iterable[str] = CRAFT_CATEGORIES,
    tier2_categories: Iterable[str] = (),
    student_model: str = "mlx-community/Qwen2.5-3B-Instruct-4bit",
    client: Optional[Any] = None,
    job_store: Optional[Any] = None,
    batch_size: int = 15,
    synthesize_timeout: float = 600.0,
    worlds_dir: Optional[Path] = None,
    pkb_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """pull -> map -> synthesize (tier1, then tier2 if requested) -> tag ->
    merge -> train. Checkpoints job_store at each phase. Blocking — run this
    on a background thread from the portal layer, never on the event loop
    (a full pass over ~150 terms can run 10-60+ minutes).

    tier2_categories selects the "hotspot" subset re-synthesized through a
    second /synthesize pass. The caller is responsible for having restarted
    the nucleus-teacher process with TEACHER_BACKEND=anthropic between the
    tier1 and tier2 calls (see docs/persistence.md's World-corpus runbook —
    Synthesizer has no per-request tier field, so this is process-level,
    not something this function can automate).
    """
    from arail.build.jobs import BuildJobStore
    from arail.build.nucleus_client import NucleusClient

    client = client or NucleusClient()
    job_store = job_store or BuildJobStore()

    def _update(**fields: Any) -> None:
        try:
            job_store.update(run_id, **fields)
        except Exception:  # noqa: BLE001 — progress tracking must never abort a build
            log.warning("world_corpus: job_store.update failed for %s", run_id)

    _update(phase="pull")
    tier2_set = set(tier2_categories)
    all_categories = list(dict.fromkeys(list(categories) + list(tier2_set)))
    terms = pull_approved_terms(world_slug, categories=all_categories,
                                worlds_dir=worlds_dir, pkb_root=pkb_root)
    if not terms:
        raise ValueError(
            f"no approved terms found for World '{world_slug}' in "
            f"categories {list(all_categories)} — mount + approve first")

    tier1_terms = [t for t in terms if t.get("category") not in tier2_set]
    tier2_terms = [t for t in terms if t.get("category") in tier2_set]

    _update(phase="synthesize_tier1",
           synth_progress={"tier": 1, "batch": 0, "of": len(chunk(tier1_terms, batch_size))})
    tier1_records = _synthesize_all(client, tier1_terms, id_prefix="world",
                                    batch_size=batch_size,
                                    timeout=synthesize_timeout,
                                    on_progress=lambda b, n: _update(
                                        phase="synthesize_tier1",
                                        synth_progress={"tier": 1, "batch": b, "of": n}))
    tag_source(tier1_records, "tier1")

    tier2_records: List[Dict[str, Any]] = []
    if tier2_terms:
        _update(phase="synthesize_tier2",
               synth_progress={"tier": 2, "batch": 0, "of": len(chunk(tier2_terms, batch_size))})
        tier2_records = _synthesize_all(client, tier2_terms, id_prefix="world-tier2",
                                        batch_size=batch_size,
                                        timeout=synthesize_timeout,
                                        on_progress=lambda b, n: _update(
                                            phase="synthesize_tier2",
                                            synth_progress={"tier": 2, "batch": b, "of": n}))
        tag_source(tier2_records, "tier2")

    dataset = tier1_records + tier2_records
    _update(phase="train", record_count=len(dataset))
    train_result = client.train_direct(dataset, run_id=run_id)
    _update(phase="training", train_started=train_result)

    return {
        "world_slug": world_slug,
        "categories": list(all_categories),
        "tier2_categories": list(tier2_set),
        "term_count": len(terms),
        "record_count": len(dataset),
        "train_result": train_result,
    }


def _synthesize_all(client: Any, terms: List[Dict[str, Any]], *,
                    id_prefix: str, batch_size: int, timeout: float,
                    on_progress: Any = None) -> List[Dict[str, Any]]:
    examples_by_chunk = chunk(
        [term_to_kice_example(t, id_prefix=id_prefix) for t in terms],
        batch_size)
    records: List[Dict[str, Any]] = []
    for i, batch in enumerate(examples_by_chunk, start=1):
        if on_progress:
            on_progress(i, len(examples_by_chunk))
        result = client.synthesize(batch, timeout=timeout)
        records.extend(result.get("training_records", []))
    return records
