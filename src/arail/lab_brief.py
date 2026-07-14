"""The lab brief — one shared context for humans and agents.

Compiles what the lab *is right now* into a small, cheap document:
the mounted World's identity, the active goal, the research program
headline, any operator redirects, a digest of the approved knowledge
(the Compiled KB the WK-10 gate scopes agents to), and the freshest
agent outputs.

Consumers:
- ``GET /api/lab/brief`` renders it on the Knowledge page's Agent Focus
  section (humans read it there);
- Buddy's system prompt (``lab_brain._state_block``) and the
  Researcher's planning prompt prepend ``brief_markdown()`` — agents
  literally read the same context the page shows.

Design rules: best-effort everywhere (a missing file yields ``None``/
empty, never an exception — curated-first, model-optional), and cheap
per request (stat-keyed cache; the one directory walk is TTL-bounded).
"""

from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

_log = logging.getLogger(__name__)

SCHEMA = "arail.lab-brief/v1"

# How long the expensive bits (agents/ walk, pending count) may be reused
# while the cheap stat-key is unchanged.
_TTL_SECONDS = 30.0

_RECENT_APPROVED = 8
_RECENT_OUTPUTS = 5
_PROGRAM_EXCERPT_CHARS = 600
_MARKDOWN_MAX_LINES = 40


def _pkb_root() -> Path:
    from arail.pkb import _pkb_root as pr
    return pr()


# ── World identity ───────────────────────────────────────────────────────

def _mounted_bundle_dir() -> Optional[Path]:
    """The mounted World's canonical bundle dir (catalog copy preferred) —
    mirrors world_routes._mounted_catalog_dir without importing the portal."""
    try:
        from arail import world_mount as wm
        record = wm.current_mount()
        if record is None:
            return None
        catalog = wm._default_worlds_dir() / record.world
        if (catalog / "manifest.json").exists():
            return catalog
        bundle = Path(record.bundle_dir)
        return bundle if (bundle / "manifest.json").exists() else None
    except Exception:  # noqa: BLE001
        return None


def world_summary() -> Optional[dict[str, Any]]:
    """Identity card for the mounted World, or None when unmounted.
    Reads only the small bundle JSON files; every field is best-effort."""
    bundle = _mounted_bundle_dir()
    if bundle is None:
        return None
    try:
        manifest = json.loads((bundle / "manifest.json").read_bytes())
    except Exception:  # noqa: BLE001
        return None
    out: dict[str, Any] = {
        "slug": manifest.get("world"),
        "display_name": manifest.get("display_name") or manifest.get("world"),
        "provenance_tier": manifest.get("provenance_tier"),
        "provenance_counts": manifest.get("provenance_counts"),
        "term_count": None,
        "category_count": None,
    }
    try:
        terms = json.loads((bundle / "terms.json").read_bytes()).get("terms", [])
        out["term_count"] = len(terms)
    except Exception:  # noqa: BLE001
        pass
    try:
        spec = json.loads((bundle / "spec.json").read_bytes())
        out["category_count"] = len(spec.get("categories", []))
    except Exception:  # noqa: BLE001
        pass
    return out


# ── Section builders (each best-effort) ──────────────────────────────────

def _goal_section() -> Optional[dict[str, Any]]:
    try:
        from arail.goals import GoalStore
        current = GoalStore().get_current()
        if not current:
            return None
        return {
            "goal_text": current.get("goal_text", ""),
            "progress": current.get("progress", 0),
            "status": current.get("status", ""),
            "created_at": current.get("created_at", ""),
        }
    except Exception:  # noqa: BLE001
        return None


def _program_section(pkb_root: Path) -> dict[str, Any]:
    path = pkb_root / "research" / "program.md"
    out: dict[str, Any] = {"exists": False, "objective": "", "excerpt": "",
                           "knob_count": 0, "path": "research/program.md"}
    if not path.exists():
        return out
    out["exists"] = True
    try:
        from arail.research.program_loader import parse_program
        recipe = parse_program(path)
        if recipe is not None:
            out["objective"] = recipe.goal or recipe.intent or ""
            out["knob_count"] = len(recipe.knobs)
    except Exception:  # noqa: BLE001
        pass
    try:
        out["excerpt"] = path.read_text(errors="replace").strip()[:_PROGRAM_EXCERPT_CHARS]
    except OSError:
        pass
    return out


def _redirects_section() -> dict[str, Any]:
    out: dict[str, Any] = {}
    try:
        from arail.agent_redirects import get_agent_redirect
        for agent_id in ("researcher", "buddy"):
            r = get_agent_redirect(agent_id)
            if r and str(r.get("instruction") or "").strip():
                out[agent_id] = {
                    "instruction": str(r.get("instruction") or "").strip(),
                    "preset": r.get("preset", ""),
                    "set_at": r.get("set_at", ""),
                }
    except Exception:  # noqa: BLE001
        pass
    return out


def _knowledge_section(pkb_root: Path) -> dict[str, Any]:
    out: dict[str, Any] = {
        "gate_enabled": True,
        "approved_total": 0,
        "approved_by_kind": {},
        "recent_approved": [],
        "pending_total": 0,
    }
    try:
        from arail import compiled_kb as ckb
        out["gate_enabled"] = ckb.gate_enabled()
        approved = ckb.list_approved(pkb_root)
        out["approved_total"] = len(approved)
        by_kind: dict[str, int] = {}
        for rec in approved:
            k = rec.get("kind", "source")
            by_kind[k] = by_kind.get(k, 0) + 1
        out["approved_by_kind"] = by_kind
        out["recent_approved"] = [
            {"title": r.get("title", r.get("path", "")),
             "kind": r.get("kind", ""),
             "approved_at": r.get("approved_at", "")}
            for r in approved[:_RECENT_APPROVED]
        ]
        out["pending_total"] = len(ckb.pending_paths(pkb_root))
    except Exception:  # noqa: BLE001
        pass
    return out


def _recent_agent_outputs(pkb_root: Path) -> list[dict[str, Any]]:
    """Newest markdown outputs under agents/ (contracts excluded), mtime
    ordered. This is the one directory walk in the brief — TTL-cached."""
    agents_dir = pkb_root / "agents"
    if not agents_dir.exists():
        return []
    rows: list[tuple[float, Path]] = []
    try:
        for p in agents_dir.rglob("*.md"):
            # Outputs only — skip agent contracts and folder docs.
            if p.name in ("AGENT.md", "README.md") or not p.is_file():
                continue
            try:
                rows.append((p.stat().st_mtime, p))
            except OSError:
                continue
    except OSError:
        return []
    rows.sort(key=lambda t: t[0], reverse=True)
    out: list[dict[str, Any]] = []
    try:
        from arail import compiled_kb as ckb
        approved = ckb.approved_paths(pkb_root)
        kind_of = ckb.kind_of
    except Exception:  # noqa: BLE001
        approved, kind_of = set(), lambda _p: ""
    for mtime, p in rows[:_RECENT_OUTPUTS]:
        rel = p.relative_to(pkb_root).as_posix()
        out.append({
            "path": rel,
            "title": p.stem.replace("_", " ").replace("-", " "),
            "kind": kind_of(rel),
            "mtime": datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat(timespec="seconds"),
            "approved": rel in approved,
        })
    return out


# ── The brief ────────────────────────────────────────────────────────────

def build_brief(pkb_root: Path | None = None) -> dict[str, Any]:
    """Assemble the full brief. Every section degrades independently."""
    root = pkb_root or _pkb_root()
    return {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "world": world_summary(),
        "goal": _goal_section(),
        "research_program": _program_section(root),
        "redirects": _redirects_section(),
        "knowledge": _knowledge_section(root),
        "recent_agent_outputs": _recent_agent_outputs(root),
    }


def brief_markdown(brief: dict[str, Any]) -> str:
    """The exact text agents receive — compact, capped, plain markdown."""
    lines: list[str] = ["# Lab brief", ""]

    w = brief.get("world")
    if w:
        bits = [f"**{w.get('display_name') or w.get('slug')}**"]
        if w.get("provenance_tier"):
            bits.append(str(w["provenance_tier"]))
        if w.get("term_count") is not None:
            bits.append(f"{w['term_count']} terms")
        if w.get("category_count") is not None:
            bits.append(f"{w['category_count']} categories")
        lines.append("- World: " + " · ".join(bits))
    else:
        lines.append("- World: none mounted")

    g = brief.get("goal")
    if g and g.get("goal_text"):
        pct = int(float(g.get("progress") or 0) * 100)
        lines.append(f"- Active goal: \"{g['goal_text'][:140]}\" ({pct}%)")
    else:
        lines.append("- Active goal: none")

    prog = brief.get("research_program") or {}
    if prog.get("exists"):
        head = (prog.get("objective") or "").strip()
        suffix = f" · {prog['knob_count']} knobs" if prog.get("knob_count") else ""
        lines.append(f"- Research program: {head[:120] or 'present'}{suffix} (research/program.md)")

    for agent_id, r in (brief.get("redirects") or {}).items():
        lines.append(f"- Operator redirect ({agent_id}): {r['instruction'][:140]}")

    k = brief.get("knowledge") or {}
    gate = "approved-only" if k.get("gate_enabled") else "raw corpus (gate off)"
    lines.append(
        f"- Compiled KB ({gate}): {k.get('approved_total', 0)} approved, "
        f"{k.get('pending_total', 0)} pending review"
    )
    if k.get("approved_by_kind"):
        kinds = ", ".join(f"{n} {kind.replace('_', ' ')}" for kind, n
                          in sorted(k["approved_by_kind"].items()))
        lines.append(f"  - approved by kind: {kinds}")
    if k.get("recent_approved"):
        lines.append("  - recently approved: "
                     + "; ".join(r["title"][:60] for r in k["recent_approved"][:4]))

    outs = brief.get("recent_agent_outputs") or []
    if outs:
        lines.append("- Recent agent outputs:")
        for o in outs:
            mark = "approved" if o.get("approved") else "pending review"
            lines.append(f"  - {o['title'][:70]} ({o.get('kind', '').replace('_', ' ')}, {mark})")

    return "\n".join(lines[:_MARKDOWN_MAX_LINES])


# ── Stat-keyed cache ─────────────────────────────────────────────────────

_cache_lock = threading.Lock()
_cache: dict[str, Any] = {"key": None, "expires": 0.0, "brief": None}


def _mtime(p: Path) -> float:
    try:
        return p.stat().st_mtime
    except OSError:
        return 0.0


def _cache_key(root: Path) -> tuple:
    from arail.config import DATA_DIR
    world = None
    try:
        from arail import world_mount as wm
        record = wm.current_mount()
        world = record.world if record else None
    except Exception:  # noqa: BLE001
        pass
    kb = root / "compiled" / "kb"
    return (
        world,
        _mtime(DATA_DIR / "goals" / "current.json"),
        _mtime(DATA_DIR / "agent_redirects.json"),
        _mtime(kb / "approved.json"),
        _mtime(kb / "rejected.json"),
        _mtime(root / "research" / "program.md"),
    )


def get_cached_brief(pkb_root: Path | None = None) -> dict[str, Any]:
    """The brief, cheap: rebuilt only when a source file's mtime moves or
    the TTL (for the agents/ walk + pending count) lapses."""
    root = pkb_root or _pkb_root()
    key = _cache_key(root)
    now = time.monotonic()
    with _cache_lock:
        if _cache["brief"] is not None and _cache["key"] == key and now < _cache["expires"]:
            return _cache["brief"]
    brief = build_brief(root)
    with _cache_lock:
        _cache.update({"key": key, "expires": now + _TTL_SECONDS, "brief": brief})
    return brief
