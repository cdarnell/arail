"""World Forge — dream a subject into a mountable World, then curate it.

Python port of qukaizen-dac's forge pipeline, making world generation an
ARAIL capability (per DaC VISION.md: "World generation is an ARAIL
capability"; the repo boundary is the portable compiled artifact — no
cross-repo runtime imports). Ports, faithfully:

  - the 7-stage draft pipeline  (scripts/forge-world.mts: SPEC → SEED →
    DISCOVER BFS → LINK → DEFINE → CLOSE → GATE)
  - the gate                    (src/gate.ts — three laws: sourced, declared
    category, closed related-graph)
  - the provenance recognizer   (src/provenance.ts — ``model:`` regex; tier
    is DERIVED from the corpus, never asserted)
  - the sealer                  (scripts/export-bundle.mts — 6 sealed
    siblings + manifest sha256s + seal-exempt SKILL.md / capabilities /
    arail-plugin)
  - the SKILL.md renderer       (src/arail-export/skill.ts — F1 frontmatter
    and F2 body injection containment)
  - the reconcile judge         (scripts/reconcile-world.mts — the Curator's
    per-term verdict)

Byte-parity with DaC's sealer is a NON-goal: both emit valid
``dac.world-bundle/v1``; the invariant that matters (and is tested) is that
``write_bundle`` output round-trips ARAIL's own ``world_mount.load_bundle``
+ ``verify_seal`` + ``check_compat`` + ``check_categories``.

Framework-free by design (mirrors dictionary.py): sync functions, injectable
router, tolerant never-raise model-output parsing. The portal layer owns
async wrapping (``inference_slot`` + ``asyncio.to_thread``), locking, and
endpoints.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

_log = logging.getLogger(__name__)

# ── Caps (DaC forge-world.mts DEFINE stage) ─────────────────────────────
MAX_SHORT = 200
MAX_DEFINITION = 600
MAX_EXAMPLE = 300
MAX_RELATED_PER_TERM = 5

# skills_loader body cap is 56K chars; warn with margin (≈300 chars/term).
SKILL_CHAR_BUDGET = 48_000
SKILL_CHARS_PER_TERM = 300
MAX_TERMS_SOFT = 150

BUNDLE_SCHEMA = "dac.world-bundle/v1"
SEALED_FILES = ("terms.json", "spec.json", "roster.json", "face.json",
                "agenda.json", "drift-report.json")


def slugify(s: str) -> str:
    """Port of the forge's slugify: lowercase, non-alnum runs → '-', ≤48."""
    out = re.sub(r"[^a-z0-9]+", "-", str(s).lower().strip())
    return out.strip("-")[:48]


# ═══════════════════════ tolerant model-output parsing ═══════════════════

def loose_json(raw: str) -> Any:
    """Best-effort JSON from small-model output. Never raises; None on defeat.

    The repair ladder mirrors dictionary.parse_entries steps 1–4 (fence strip
    → span slice → direct load → trailing-comma repair) WITHOUT its glossary
    coercion — forge stage outputs have varied shapes.
    """
    if not raw or not isinstance(raw, str):
        return None
    text = raw.strip()
    # Strip a markdown code fence if present.
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```\s*$", text, re.S)
    if fence:
        text = fence.group(1).strip()
    # Slice to the outermost JSON value span.
    starts = [i for i in (text.find("{"), text.find("[")) if i != -1]
    if starts:
        start = min(starts)
        closer = "}" if text[start] == "{" else "]"
        end = text.rfind(closer)
        if end > start:
            text = text[start:end + 1]
    for candidate in (text, re.sub(r",\s*([}\]])", r"\1", text)):
        try:
            return json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            continue
    return None


def first_array(obj: Any) -> list:
    """Port of firstArray(): small models wrap arrays under arbitrary keys."""
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        for v in obj.values():
            if isinstance(v, list):
                return v
    return []


# ═══════════════════════ gate (port of src/gate.ts) ══════════════════════

@dataclass
class GateResult:
    ok: bool = True
    dangling_edges: list[tuple[str, str]] = field(default_factory=list)
    unsourced: list[str] = field(default_factory=list)
    undeclared_category: list[tuple[str, str]] = field(default_factory=list)


def _edge_target(edge: Any) -> str:
    if isinstance(edge, str):
        return edge.strip()
    if isinstance(edge, dict) and isinstance(edge.get("slug"), str):
        return edge["slug"].strip()
    return ""


def assert_closed_sourced_graph(terms: list[dict], declared: set[str]) -> GateResult:
    """The three laws: sourced, declared category, closed related-graph.

    Pure, total, deterministic — never raises. Empty corpus → vacuously ok.
    Self-edges resolve like any other edge. Missing slug → reported violation.
    """
    result = GateResult()
    slug_set = {t["slug"].strip() for t in terms
                if isinstance(t.get("slug"), str) and t["slug"].strip()}

    for t in terms:
        slug = t.get("slug", "")
        slug = slug.strip() if isinstance(slug, str) else ""
        if not slug:
            result.undeclared_category.append(("<missing-slug>", str(t.get("category", "<missing>"))))
            result.ok = False
            continue
        src = t.get("source", "")
        if not (isinstance(src, str) and src.strip()):
            result.unsourced.append(slug)
            result.ok = False
        cat = t.get("category", "")
        cat = cat.strip() if isinstance(cat, str) else ""
        if not cat or cat not in declared:
            result.undeclared_category.append((slug, cat))
            result.ok = False
        for edge in t.get("related") or []:
            target = _edge_target(edge)
            if target and target not in slug_set:
                result.dangling_edges.append((slug, target))
                result.ok = False
    return result


# ═══════════════ provenance (port of src/provenance.ts) ═══════════════════

# The `:` in the body class is load-bearing: without it an Ollama name:version
# tag (model:qwen2.5:7b) would launder a dreamed World to "sourced".
_MODEL_SOURCE_RE = re.compile(r"^model:[a-z0-9][a-z0-9._:/-]*$", re.I)


def tier_of_source(source: Optional[str]) -> str:
    return "model-asserted" if _MODEL_SOURCE_RE.match(str(source or "").strip()) else "sourced"


def compute_provenance_tier(sources: list[Optional[str]]) -> tuple[str, dict]:
    """Roll a corpus up to a World tier. "mixed" is computed, never authored."""
    model = sum(1 for s in sources if tier_of_source(s) == "model-asserted")
    total = len(sources)
    sourced = total - model
    tier = ("sourced" if total == 0 or model == 0
            else "model-asserted" if sourced == 0
            else "mixed")
    return tier, {"model": model, "sourced": sourced, "total": total}


# ═══════════════════════════ the draft pipeline ═══════════════════════════

class ForgeCancelled(Exception):
    """The cancel event was set; nothing was written to disk."""


class GateRefused(Exception):
    """The drafted corpus failed the gate (or produced nothing usable)."""

    def __init__(self, gate: GateResult, message: str = "gate refused the corpus"):
        super().__init__(message)
        self.gate = gate


@dataclass
class ForgeParams:
    subject: str
    slug: str
    max_terms: int = 25
    n_categories: Optional[int] = None
    n_seeds: Optional[int] = None

    def normalized(self) -> "ForgeParams":
        subject = str(self.subject).strip()[:120]
        slug = slugify(self.slug or subject)
        max_terms = max(8, min(150, int(self.max_terms)))
        # Knob mapping: 25 → 4 cats / 3 seeds · 50 → 5/4 · 100 → 6/5.
        n_cats = self.n_categories or (4 if max_terms <= 30 else 5 if max_terms <= 65 else 6)
        n_seeds = self.n_seeds or (3 if max_terms <= 30 else 4 if max_terms <= 65 else 5)
        return ForgeParams(subject, slug, max_terms, n_cats, n_seeds)


@dataclass
class ForgeResult:
    spec: dict
    terms: list[dict]
    gate: GateResult
    tier: str
    counts: dict
    source_tag: str
    stats: dict


# Stage names in pipeline order — the UI's progress rows key off these.
FORGE_STAGES = ("spec", "seed", "discover", "link", "define", "gate")

ProgressCb = Callable[[str, int, int, str], None]


def _source_tag_from_model(model_name: str) -> str:
    """model:<name> — lowercase, strip :latest, ':'→'/' (provenance-safe)."""
    name = str(model_name or "").strip().lower()
    name = re.sub(r":latest$", "", name).replace(":", "/")
    tag = f"model:{name}" if name else "model:local"
    return tag if _MODEL_SOURCE_RE.match(tag) else "model:local"


def estimate_skill_chars(n_terms: int) -> int:
    return n_terms * SKILL_CHARS_PER_TERM + 1200


def forge_world(
    params: ForgeParams,
    *,
    router: Any = None,
    progress_cb: Optional[ProgressCb] = None,
    cancel: Optional[threading.Event] = None,
) -> ForgeResult:
    """Draft a World from a subject. Pure in-memory — no disk until sealing.

    Prompts/temperatures are ported verbatim from forge-world.mts. Every model
    response goes through loose_json (tolerant; None → skip, like the spike).
    ``cancel`` is checked before every model call.
    """
    p = params.normalized()
    if not p.subject:
        raise ValueError("subject required")
    if router is None:
        from arail.router import ModelRouter
        router = ModelRouter(billing_source="agent")

    calls = 0
    repair_events = 0
    t0 = time.monotonic()
    source_tag: Optional[str] = None

    def progress(stage: str, done: int, total: int, note: str = "") -> None:
        if progress_cb:
            try:
                progress_cb(stage, done, total, note)
            except Exception:  # noqa: BLE001 — progress must never kill a forge
                pass

    def call_model(prompt: str, temperature: float = 0.3) -> Any:
        nonlocal calls, repair_events, source_tag
        if cancel is not None and cancel.is_set():
            raise ForgeCancelled()
        calls += 1
        try:
            resp = router.complete(prompt, max_tokens=700, temperature=temperature, top_p=0.9)
        except Exception as e:  # noqa: BLE001 — one bad call must not kill the run
            _log.warning("world_forge: model call failed (skipping): %s", e)
            return None
        if source_tag is None and getattr(resp, "model", None):
            source_tag = _source_tag_from_model(resp.model)
        parsed = loose_json(getattr(resp, "text", "") or "")
        if parsed is None:
            repair_events += 1
        return parsed

    # 1. SPEC — categories for the subject.
    progress("spec", 0, 1, "mapping the subject into categories")
    spec_res = call_model(
        f'You are mapping the subject "{p.subject}" into a knowledge World. '
        f'Return JSON: an array "categories" of {p.n_categories} broad sub-areas, '
        f'each {{"id":"kebab-slug","label":"Title Case"}}.'
    )
    raw_cats = first_array((spec_res or {}).get("categories", spec_res) if isinstance(spec_res, dict) else spec_res)
    cats: list[dict] = []
    for c in raw_cats:
        if isinstance(c, dict):
            cid = slugify(str(c.get("id") or c.get("label") or ""))
            label = str(c.get("label") or c.get("id") or "")
        else:
            cid, label = slugify(str(c)), str(c)
        if cid and cid not in {x["id"] for x in cats}:
            cats.append({"id": cid, "label": label})
    cats = cats[: p.n_categories]
    if not cats:
        cats = [{"id": slugify(p.subject), "label": p.subject}]
    declared = {c["id"] for c in cats}
    progress("spec", 1, 1, ", ".join(sorted(declared)))

    # 2. SEED — terms per category.
    terms: dict[str, dict] = {}
    for i, c in enumerate(cats):
        r = call_model(
            f'Subject: "{p.subject}". For the sub-area "{c["label"]}", return JSON array '
            f'"terms" of {p.n_seeds} key concepts, each {{"term":"short name"}}. '
            f"Only fundamental, well-known concepts."
        )
        items = first_array((r or {}).get("terms", r) if isinstance(r, dict) else r)
        for t in items[: p.n_seeds]:
            name = str(t.get("term") or t.get("name") or t).strip() if isinstance(t, dict) else str(t).strip()
            s = slugify(name)
            if s and s not in terms:
                terms[s] = {"slug": s, "term": name, "category": c["id"],
                            "related": [], "source": None}
        progress("seed", i + 1, len(cats), f"{len(terms)} terms seeded")

    # 3. DISCOVER — multi-pass BFS: a real queue so late finds also expand.
    queue = list(terms.keys())
    while queue and len(terms) < p.max_terms:
        ft = terms[queue.pop(0)]
        r = call_model(
            f'Subject: "{p.subject}". For the concept "{ft["term"]}", return JSON array '
            f'"related" of up to 4 directly-associated concepts in this subject, '
            f'each {{"term":"short name"}}.'
        )
        items = first_array((r or {}).get("related", r) if isinstance(r, dict) else r)
        for x in items[:4]:
            name = str(x.get("term") or x.get("name") or x).strip() if isinstance(x, dict) else str(x).strip()
            s = slugify(name)
            if not s or s in terms or len(terms) >= p.max_terms:
                continue
            terms[s] = {"slug": s, "term": name, "category": ft["category"],
                        "related": [], "source": None}
            queue.append(s)  # newly-discovered terms get expanded too
        progress("discover", len(terms), p.max_terms, f"exploring from {ft['term']}")

    # 3b. LINK — connect every term to the EXISTING set: dense AND closed by
    # construction (edges only ever point at known slugs).
    roster = ", ".join(f"{t['slug']} ({t['term']})" for t in terms.values())
    for i, t in enumerate(terms.values()):
        r = call_model(
            f'Subject: "{p.subject}". From THIS list of known concepts:\n{roster}\n'
            f'Return JSON array "related" of the slugs most directly associated with '
            f'"{t["term"]}" (up to {MAX_RELATED_PER_TERM}, choose ONLY slugs from the list, '
            f'exclude "{t["slug"]}").',
            temperature=0.1,
        )
        items = first_array((r or {}).get("related", r) if isinstance(r, dict) else r)
        for x in items[:MAX_RELATED_PER_TERM]:
            s = slugify(str(x.get("slug") or x.get("term") or x)) if isinstance(x, dict) else slugify(str(x))
            if s in terms and s != t["slug"] and s not in t["related"]:
                t["related"].append(s)
        progress("link", i + 1, len(terms), "")

    # 4. DEFINE — prose per term.
    defined = 0
    for i, t in enumerate(terms.values()):
        r = call_model(
            f'Subject: "{p.subject}". Define the concept "{t["term"]}" as JSON: '
            f'{{"short":"one line","definition":"2-3 sentences","example":"one concrete example"}}.',
            temperature=0.2,
        )
        if isinstance(r, dict):
            t["short"] = str(r.get("short") or "")[:MAX_SHORT]
            t["definition"] = str(r.get("definition") or r.get("short") or t["term"])[:MAX_DEFINITION]
            t["example"] = str(r.get("example") or "")[:MAX_EXAMPLE]
            if t["definition"]:
                defined += 1
        else:
            t["short"] = t["term"]
            t["definition"] = t["term"]
            t["example"] = ""
        # A garbage one-token short from a small model reads terribly in the
        # glossary — fall back to the definition's first line.
        if len(t["short"].strip()) < 3:
            t["short"] = t["definition"][:MAX_SHORT]
        progress("define", i + 1, len(terms), f"{defined} defined")

    # Stamp provenance now that the source tag is known.
    tag = source_tag or "model:local"
    for t in terms.values():
        t["source"] = tag

    # 5. CLOSE — drop dangling/self edges (belt and suspenders for the gate).
    present = set(terms.keys())
    for t in terms.values():
        t["related"] = [s for s in t["related"] if s in present and s != t["slug"]]

    term_list = list(terms.values())
    gate = assert_closed_sourced_graph(term_list, declared)
    if not term_list:
        raise GateRefused(gate, "nothing usable produced — try a richer model or a clearer subject")
    tier, counts = compute_provenance_tier([t["source"] for t in term_list])
    progress("gate", 1, 1, f"{'pass' if gate.ok else 'FAIL'} · tier {tier}")

    display = re.sub(r"\b\w", lambda m: m.group(0).upper(), p.subject)
    spec = {
        "_forged_notice": f'DREAMED by {tag} from "{p.subject}" in the ARAIL World Forge. '
                          f"Model-asserted, UNVERIFIED.",
        "slug": p.slug,
        "display_name": display,
        "categories": cats,
        "knowledge_sources": [{"kind": "model", "ref": tag, "trust": "model-asserted",
                               "holder": tag.removeprefix("model:")}],
    }
    n_edges = sum(len(t["related"]) for t in term_list)
    return ForgeResult(
        spec=spec, terms=term_list, gate=gate, tier=tier, counts=counts, source_tag=tag,
        stats={
            "calls": calls,
            "elapsed_s": round(time.monotonic() - t0, 1),
            "avg_edges": round(n_edges / len(term_list), 2),
            "defined": defined,
            "total": len(term_list),
            "repair_events": repair_events,
            "skill_chars": estimate_skill_chars(len(term_list)),
        },
    )


# ═══════════ SKILL.md renderer (port of src/arail-export/skill.ts) ═════════

_BODY_CONTROL_RE = re.compile(r"^([#\->`])")


def sanitize_frontmatter_scalar(s: str) -> str:
    """F1: collapse CR/LF, trim, double-quote with internal escapes."""
    flat = re.sub(r"[\r\n]+", " ", str(s)).strip()
    return '"' + flat.replace("\\", "\\\\").replace('"', '\\"') + '"'


def sanitize_body_field(s: str) -> str:
    """F2: collapse CR/LF to a space; ZWNJ-neutralize a leading control token."""
    flat = re.sub(r"[\r\n]+", " ", str(s)).strip()
    return _BODY_CONTROL_RE.sub("‌\\1", flat)


def _cmp_key(s: str) -> str:
    return s.casefold()


def render_world_skill(spec: dict, face: dict, terms: list[dict], world_sha: str) -> str:
    """SKILL.md in the exact shape skills_loader parses. Pure projection of
    gated fields (slug/term/short/source) — the honesty rail."""
    slug = str(spec.get("slug", ""))
    display_raw = str(spec.get("display_name", slug))
    display_fm = sanitize_frontmatter_scalar(display_raw)
    display_body = sanitize_body_field(display_raw)
    prov_tier = str(face.get("provenance_tier", ""))

    cat_label = {str(c.get("id", "")): str(c.get("label") or c.get("id", ""))
                 for c in spec.get("categories", []) if isinstance(c, dict)}

    by_cat: dict[str, list[dict]] = {}
    for t in terms:
        by_cat.setdefault(str(t.get("category", "")), []).append(t)
    sorted_cats = sorted(by_cat, key=_cmp_key)
    for cat in sorted_cats:
        by_cat[cat].sort(key=lambda t: _cmp_key(str(t.get("slug", ""))))

    frontmatter = "\n".join([
        "---",
        f"title: {display_fm}",
        f"id: world-{slug}",
        f"name: {display_fm}",
        f"domain: {slug}",
        'version: "1.0.0"',
        f"tags: [world, knowledge, {slug}]",
        "when_to_use:",
        f"  - When the user asks about {display_body} or its declared categories",
        "  - When grounding a claim that falls inside this World's domain",
        "when_not_to_use:",
        "  - When the question is outside this World's declared categories",
        "  - When a claim cannot be tied to one of this World's sourced terms (say so; don't invent)",
        "---",
    ])

    prov_line = (
        "Every term in this World is grounded in a cited source."
        if prov_tier == "sourced"
        else "Some terms are model-asserted (unverified); cite a source when promoting them."
        if prov_tier == "mixed"
        else "This World was DREAMED by a model — terms are model-asserted and UNVERIFIED."
    )
    rail_line = ("Answer only from the terms below. Every term lists its source. "
                 "If a question cannot be answered from these terms, say the World "
                 "does not cover it — do not invent.")

    sections: list[str] = []
    for cat in sorted_cats:
        lines: list[str] = []
        for t in by_cat[cat]:
            term_safe = sanitize_body_field(str(t.get("term", "")))
            slug_safe = sanitize_body_field(str(t.get("slug", "")))
            short_safe = sanitize_body_field(str(t.get("short", "")))
            source_safe = sanitize_body_field(str(t.get("source", "")))
            lines.append(f"- **{term_safe}** (`{slug_safe}`) — {short_safe}")
            lines.append(f"  - Source: {source_safe}")
        label = sanitize_body_field(cat_label.get(cat, cat))
        sections.append(f"### {label}\n\n" + "\n".join(lines))

    body = "\n".join([
        sanitize_body_field(str(face.get("domain_framing", ""))),
        "",
        prov_line,
        "",
        f"_{rail_line}_",
        "",
        "\n\n".join(sections),
        "",
        f"<!-- dac:world_sha256 {world_sha} -->",
    ])
    return frontmatter + "\n" + body + "\n"


# ═══════════════ the sealer (port of scripts/export-bundle.mts) ════════════

def _pretty(obj: Any) -> bytes:
    return (json.dumps(obj, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


_FRAMING_BY_TIER = {
    "sourced": "Every factual claim is grounded in the World's cited sources.",
    "mixed": "Some terms are model-asserted (unverified); cite a source when promoting them.",
    "model-asserted": "This World was DREAMED by a model — terms are model-asserted and UNVERIFIED.",
}

# Authored/display fields a caller may override (mirrors DaC's allow-list).
_FACE_DISPLAY_KEYS = ("name", "tagline", "domain_framing", "vocabulary_register",
                      "palette_hint", "theme")


def _build_face(spec: dict, tier: str, counts: dict, overrides: Optional[dict]) -> dict:
    slug = str(spec.get("slug", ""))
    display = str(spec.get("display_name", slug))
    dreamed = " (dreamed)" if tier == "model-asserted" else ""
    declared = ", ".join(str(c.get("id", "")) for c in spec.get("categories", []))
    face: dict = {
        "schema": "dac.world-face/v1",
        "world": slug,
        "name": display,
        "tagline": f"A {display} World{dreamed}.",
        "palette_hint": "slate-violet",
        "domain_framing": (f"This lab studies {display}. {_FRAMING_BY_TIER.get(tier, _FRAMING_BY_TIER['model-asserted'])} "
                           f"Hypotheses and answers stay within the declared categories ({declared})."),
        "vocabulary_register": "Use the World's own terms; cite a source for every factual claim.",
        "provenance_tier": tier,
        "provenance_counts": counts,
    }
    for key in _FACE_DISPLAY_KEYS:
        if overrides and overrides.get(key) is not None:
            if key == "theme":
                # A theme block is validated HARD before sealing (same stance
                # as DaC's exporter): a sealed bundle must never carry a theme
                # ARAIL's own mount-time validator would reject.
                from arail.world_theme import parse_world_theme
                theme_spec, reason = parse_world_theme(overrides[key])
                if theme_spec is None:
                    raise ValueError(f"face theme invalid: {reason}")
                face["theme"] = overrides[key]
            else:
                face[key] = str(overrides[key])
    # Integrity fields force-derived LAST — authored copy can never assert provenance.
    face["schema"] = "dac.world-face/v1"
    face["world"] = slug
    face["provenance_tier"] = tier
    face["provenance_counts"] = counts
    return face


def _build_capabilities(spec: dict, tier: str, terms: list[dict], world_sha: str) -> dict:
    slug = str(spec.get("slug", ""))
    display = str(spec.get("display_name", slug))
    count_by_cat: dict[str, int] = {}
    for t in terms:
        cat = str(t.get("category", ""))
        if cat:
            count_by_cat[cat] = count_by_cat.get(cat, 0) + 1
    cats = sorted(
        (c for c in spec.get("categories", [])
         if isinstance(c, dict) and count_by_cat.get(str(c.get("id", "")), 0) > 0),
        key=lambda c: _cmp_key(str(c.get("id", ""))),
    )
    cat_ids = [str(c["id"]) for c in cats]
    caps = [{
        "id": f"knowledge.ground.{slug}",
        "purpose": f"Ground claims about {display} in the World's gated glossary.",
        "desired": True,
        "interface": {"kind": "knowledge-grounding", "world": slug, "world_sha256": world_sha,
                      "categories": cat_ids, "term_count": len(terms), "provenance_tier": tier},
    }]
    for c in cats:
        cid = str(c["id"])
        caps.append({
            "id": f"knowledge.ground.{slug}.{cid}",
            "purpose": f"Ground claims about {c.get('label', cid)} in {display}.",
            "desired": True,
            "interface": {"kind": "knowledge-grounding", "world": slug, "category": cid,
                          "term_count": count_by_cat[cid]},
        })
    return {"schema": "dac.world-capabilities/v1", "world": slug, "capabilities": caps}


def _build_plugin_manifest(slug: str, display: str, term_count: int, world_sha: str) -> dict:
    return {
        "name": f"qukaizen/dac-world-{slug}",
        "type": "world",
        "description": f"DaC WorldBundle for {display} — {term_count} terms, mountable in ARAIL.",
        "version": "1.0.0",
        "dac": {
            "schema": "dac.arail-plugin/v1",
            "world": slug,
            "world_sha256": world_sha,
            "bundle": ".",
            "provides": {"capabilities": "capabilities.json", "skill": "SKILL.md",
                         "bundle_manifest": "manifest.json"},
        },
    }


def write_bundle(
    out_dir: Path,
    spec: dict,
    terms: list[dict],
    *,
    face_overrides: Optional[dict] = None,
    roster: Optional[dict] = None,
    created_at: Optional[str] = None,
) -> Path:
    """Write a sealed ``dac.world-bundle/v1`` that round-trips ARAIL's own
    load_bundle + verify_seal + check_compat + check_categories.

    Gate-refuses an invalid corpus (a sealer that sealed unsourced/dangling
    terms would defeat the whole point).
    """
    out_dir = Path(out_dir)
    slug = str(spec.get("slug", ""))
    display = str(spec.get("display_name", slug))
    declared = {str(c.get("id", "")) for c in spec.get("categories", []) if isinstance(c, dict)}

    gate = assert_closed_sourced_graph(terms, declared)
    if not gate.ok:
        raise GateRefused(gate)
    tier, counts = compute_provenance_tier([t.get("source") for t in terms])

    face = _build_face(spec, tier, counts, face_overrides)
    agenda = {
        "schema": "dac.world-agenda/v1",
        "world": slug,
        "watches": [
            {"node": slug, "feeds": [str(s.get("ref") or s.get("holder") or "source")],
             "cadence": "occasional"}
            for s in (spec.get("knowledge_sources") or [])[:3] if isinstance(s, dict)
        ],
    }
    drift = {
        "schema": "dac.world-drift/v1",
        "world": slug,
        "declared": sorted(str(t.get("slug", "")) for t in terms if t.get("slug")),
        "missing": [],
        "extra": [],
        "ok": True,
    }
    roster_doc = roster or {"schema": "dac.world-roster/v1", "world": slug,
                            "desired": [str(t.get("slug", "")) for t in terms]}

    out_dir.mkdir(parents=True, exist_ok=True)
    sealed_bytes: dict[str, bytes] = {
        "terms.json": _pretty({"version": 1, "terms": terms}),
        "spec.json": _pretty(spec),
        "roster.json": _pretty(roster_doc),
        "face.json": _pretty(face),
        "agenda.json": _pretty(agenda),
        "drift-report.json": _pretty(drift),
    }
    files: dict[str, str] = {}
    for name, raw in sealed_bytes.items():
        (out_dir / name).write_bytes(raw)
        files[name] = hashlib.sha256(raw).hexdigest()
    world_sha = files["terms.json"]

    (out_dir / "SKILL.md").write_text(render_world_skill(spec, face, terms, world_sha),
                                      encoding="utf-8")
    (out_dir / "capabilities.json").write_bytes(
        _pretty(_build_capabilities(spec, tier, terms, world_sha)))
    (out_dir / "arail-plugin.json").write_bytes(
        _pretty(_build_plugin_manifest(slug, display, len(terms), world_sha)))

    manifest = {
        "schema": BUNDLE_SCHEMA,
        "bundle_version": 1,
        "world": slug,
        "display_name": display,
        "created_at": created_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "world_sha256": world_sha,
        "files": files,
        "provenance_tier": tier,
        "provenance_counts": counts,
        "refresh_cadence": "see agenda.json",
        "compat": {"bundle_schema": 1, "terms_schema": 1},
    }
    (out_dir / "manifest.json").write_bytes(_pretty(manifest))
    return out_dir


def reseal_bundle(bundle_dir: Path, terms: Optional[list[dict]] = None) -> Path:
    """Re-seal a bundle after a terms edit: re-derive everything downstream of
    terms.json (tier/counts, drift, SKILL.md, capabilities, plugin manifest,
    manifest hashes) while preserving authored display fields (name, tagline,
    domain_framing, vocabulary_register, palette_hint, theme) and the roster
    wish-list verbatim. Atomic: builds a sibling temp dir, then swaps.
    """
    bundle_dir = Path(bundle_dir)
    spec = json.loads((bundle_dir / "spec.json").read_bytes())
    old_manifest = json.loads((bundle_dir / "manifest.json").read_bytes())
    if terms is None:
        terms = json.loads((bundle_dir / "terms.json").read_bytes()).get("terms", [])
    roster = None
    if (bundle_dir / "roster.json").exists():
        try:
            roster = json.loads((bundle_dir / "roster.json").read_bytes())
        except Exception:  # noqa: BLE001
            roster = None
    overrides: dict = {}
    if (bundle_dir / "face.json").exists():
        try:
            old_face = json.loads((bundle_dir / "face.json").read_bytes())
            overrides = {k: old_face.get(k) for k in _FACE_DISPLAY_KEYS if old_face.get(k) is not None}
        except Exception:  # noqa: BLE001
            overrides = {}

    tmp = bundle_dir.parent / f".{bundle_dir.name}.reseal-tmp"
    old = bundle_dir.parent / f".{bundle_dir.name}.reseal-old"
    for leftover in (tmp, old):
        if leftover.exists():
            shutil.rmtree(leftover)
    write_bundle(tmp, spec, terms, face_overrides=overrides, roster=roster,
                 created_at=str(old_manifest.get("created_at") or "") or None)
    # Carry over seal-exempt sidecars the sealer does not regenerate.
    for extra in ("model.json", "review.json"):
        if (bundle_dir / extra).exists():
            shutil.copy2(bundle_dir / extra, tmp / extra)
    os.rename(bundle_dir, old)
    try:
        os.rename(tmp, bundle_dir)
    except Exception:
        os.rename(old, bundle_dir)  # roll back — never leave the slug missing
        raise
    shutil.rmtree(old)
    return bundle_dir


# ═══════════ the Curator judge (port of reconcile-world.mts) ══════════════

@dataclass
class ReviewFlag:
    slug: str
    verdict: str                 # "accept" | "correct" | "reject"
    better_category: str = ""
    bad_edges: list[str] = field(default_factory=list)
    note: str = ""

    def to_dict(self) -> dict:
        return {"slug": self.slug, "verdict": self.verdict,
                "better_category": self.better_category,
                "bad_edges": list(self.bad_edges), "note": self.note}


def reconcile_terms(
    spec: dict,
    terms: list[dict],
    *,
    router: Any,
    limit: int = 16,
    cancel: Optional[threading.Event] = None,
) -> list[ReviewFlag]:
    """The Curator's review: a (deeper, when available) model judges terms.

    Returns flags ONLY for terms that need attention (correct/reject) —
    accepted terms produce no flag. Advisory sidecar data; never sealed.
    """
    subject = str(spec.get("display_name") or spec.get("slug") or "")
    cats = ", ".join(str(c.get("id", "")) for c in spec.get("categories", []))
    declared = {str(c.get("id", "")) for c in spec.get("categories", [])}
    flags: list[ReviewFlag] = []

    for t in terms[: max(1, limit)]:
        if cancel is not None and cancel.is_set():
            break
        prompt = (
            f'Subject: "{subject}". Declared categories: {cats}.\n'
            f"A smaller model drafted this term. Judge it. Return JSON:\n"
            f'{{"correct": true|false, "category_ok": true|false, '
            f'"better_category": "id-or-empty", '
            f'"bad_edges": ["slugs in related[] that are NOT really associated"], '
            f'"note": "<=12 words"}}\n\n'
            f'term: "{t.get("term", "")}"  category: "{t.get("category", "")}"  '
            f'definition: "{str(t.get("definition", ""))[:400]}"  '
            f"related: {json.dumps(t.get('related') or [])}"
        )
        try:
            resp = router.complete(prompt, max_tokens=300, temperature=0.1)
        except Exception as e:  # noqa: BLE001
            _log.warning("world_forge.reconcile: judge call failed for %s: %s", t.get("slug"), e)
            continue
        verdict = loose_json(getattr(resp, "text", "") or "")
        if not isinstance(verdict, dict):
            continue
        correct = bool(verdict.get("correct", True))
        cat_ok = bool(verdict.get("category_ok", True))
        better = slugify(str(verdict.get("better_category") or ""))
        if better not in declared:
            better = ""
        related = set(t.get("related") or [])
        bad_edges = [s for s in (slugify(str(x)) for x in (verdict.get("bad_edges") or [])
                                 if isinstance(x, str)) if s in related]
        if correct and cat_ok and not bad_edges:
            continue  # accepted — no flag
        flags.append(ReviewFlag(
            slug=str(t.get("slug", "")),
            verdict="reject" if not correct else "correct",
            better_category=better if not cat_ok else "",
            bad_edges=bad_edges,
            note=str(verdict.get("note") or "")[:120],
        ))
    return flags


# ═══════════════ world-first helpers (Phase 4 seam) ═══════════════════════

def goal_suggestions(spec: dict, tier: str) -> list[str]:
    """World-derived study goals — pure function over the mounted spec."""
    display = str(spec.get("display_name") or spec.get("slug") or "this World")
    out = [f"Study {display}: verify and deepen the glossary — find sources for "
           f"{'dreamed' if tier != 'sourced' else 'under-cited'} terms."]
    for c in spec.get("categories", [])[:4]:
        label = str(c.get("label") or c.get("id", "")) if isinstance(c, dict) else str(c)
        if label:
            out.append(f"Deepen {label}: add sourced examples and new terms in {display}.")
    return out
