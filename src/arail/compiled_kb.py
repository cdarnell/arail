"""The Compiled Knowledge Base — the human-approved layer agents build on.

ARAIL's raw corpus (world terms, forged/grown drafts, ingested notes, and the
agents' own research/experiment outputs) is a *candidate pool*: created, but
unvetted. It must never silently become the truth agents experiment against.
This module is the gate DaC's lifecycle calls for (RAW -> COMPILED, promotion
requires provenance, a human approves): nothing crosses from raw corpus into
the Compiled KB without an explicit human approval.

Design (v1, deliberately lean and reversible):

  * The Compiled KB is a *manifest over the raw corpus*, not a second copy.
    ``lab/pkb/compiled/kb/approved.json`` records, per approved item, its
    pkb-relative path, a title, derived provenance, and the sha256 of the
    exact bytes approved (so a later raw edit is detectable as drift). The
    raw file stays put; approval is a signed pointer to a specific version.
  * ``rejected.json`` remembers dismissals so rejected candidates don't keep
    resurfacing in the review queue.
  * The retrieval gate is a query-time filter: ``pkb.search(..., approved_only
    =True)`` keeps only hits whose path is in ``approved_paths()``. Agents that
    experiment/develop (Researcher, chat RAG, goal drafter) pass approved_only;
    raw stays browsable in the DaC tab but is not what agents build on.

Never raises on read paths — a missing/corrupt manifest reads as "nothing
approved yet" (fail-closed: the gate errs toward *less* agent-visible truth,
never more).
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

SCHEMA = "arail.compiled-kb/v1"

# Where the Compiled KB manifest lives under the pkb root. Sits beside
# docgen's compiled/docs/ (auto-docs) but is a distinct, human-owned tree.
_KB_SUBDIR = ("compiled", "kb")
_APPROVED_FILE = "approved.json"
_REJECTED_FILE = "rejected.json"

# Candidate kinds surfaced in the review queue, mapped from source_kind /
# path. World per-term pages are the headline case; agent outputs are the
# "true experiment/research" the user wants to promote deliberately.
_WORLD_TERM_RE = re.compile(r"^sources/world-[^/]+/terms/[^/]+\.md$")


def _pkb_root() -> Path:
    from arail.config import PKB_ROOT
    return PKB_ROOT


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _kb_dir(pkb_root: Path) -> Path:
    return pkb_root.joinpath(*_KB_SUBDIR)


def _load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — missing/corrupt reads as empty (fail-closed)
        return default


def _save_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


# ── Manifest access ──────────────────────────────────────────────────────

def _approved_map(pkb_root: Path) -> dict[str, dict[str, Any]]:
    """path -> approved record. Tolerates legacy/list shapes."""
    raw = _load_json(_kb_dir(pkb_root) / _APPROVED_FILE, {})
    if isinstance(raw, dict):
        items = raw.get("items", raw)
    else:
        items = raw
    out: dict[str, dict[str, Any]] = {}
    if isinstance(items, dict):
        for k, v in items.items():
            if isinstance(v, dict):
                out[k] = v
    elif isinstance(items, list):
        for v in items:
            if isinstance(v, dict) and v.get("path"):
                out[v["path"]] = v
    return out


def _rejected_set(pkb_root: Path) -> set[str]:
    raw = _load_json(_kb_dir(pkb_root) / _REJECTED_FILE, [])
    if isinstance(raw, dict):
        raw = raw.get("items", [])
    return {p for p in raw if isinstance(p, str)} if isinstance(raw, list) else set()


def approved_paths(pkb_root: Path | None = None) -> set[str]:
    """The set of pkb-relative paths that are approved into the Compiled KB.

    This is the gate the retrieval layer consults. Fail-closed: any error
    yields the empty set (agents see no approved truth rather than raw)."""
    root = pkb_root or _pkb_root()
    try:
        return set(_approved_map(root).keys())
    except Exception:  # noqa: BLE001
        return set()


def is_approved(rel_path: str, pkb_root: Path | None = None) -> bool:
    return rel_path in approved_paths(pkb_root)


def rejected_paths(pkb_root: Path | None = None) -> set[str]:
    """The set of pkb-relative paths a human has dismissed from the review
    queue. Consumed by the knowledge-graph brain scope (a rejected agent
    output must not linger as a ghost candidate). Fails open to the empty
    set — worst case a dismissed item reappears as a ghost, never data loss."""
    root = pkb_root or _pkb_root()
    try:
        return _rejected_set(root)
    except Exception:  # noqa: BLE001
        return set()


def list_approved(pkb_root: Path | None = None) -> list[dict[str, Any]]:
    root = pkb_root or _pkb_root()
    return sorted(_approved_map(root).values(),
                  key=lambda r: r.get("approved_at", ""), reverse=True)


# ── Provenance / classification ──────────────────────────────────────────

def _read_text(p: Path) -> str:
    try:
        return p.read_text(errors="replace")
    except OSError:
        return ""


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()


def _title_of(rel: str, text: str) -> str:
    # frontmatter title:, then first ATX heading, then filename stem.
    m = re.search(r"^title:\s*(.+)$", text, re.MULTILINE)
    if m:
        return m.group(1).strip().strip("'\"")[:200]
    m = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    if m:
        return m.group(1).strip()[:200]
    return Path(rel).stem.replace("-", " ").replace("_", " ")[:200]


def _kind_of(rel: str) -> str:
    if _WORLD_TERM_RE.match(rel):
        return "world_term"
    if rel.startswith("sources/scout/"):
        return "scout_finding"
    if rel.startswith("agents/research/"):
        return "agent_research"
    if rel.startswith("agents/experiments/"):
        return "agent_experiment"
    if rel.startswith("agents/synthesis/"):
        return "agent_synthesis"
    if rel.startswith("agents/recommendations/"):
        return "agent_recommendation"
    if rel.startswith("agents/buddy/dreams/"):
        return "agent_dream"
    if rel.startswith("inbox/") or rel.startswith("notes/"):
        return "note"
    return "source"


# Public alias — the graph brain-scope and the lab brief classify nodes by
# the same path rules the review queue uses.
def kind_of(rel_path: str) -> str:
    return _kind_of(rel_path)


def _provenance_of(rel: str, text: str, kind: str) -> str:
    """Derived, never asserted. World terms carry a ``Source:`` line; agent
    outputs are provenance-labeled by their kind; everything else is 'user'."""
    if kind == "world_term":
        m = re.search(r"^Source:\s*(.+)$", text, re.MULTILINE)
        if m:
            return m.group(1).strip()[:200]
        return "world-term"
    if kind == "scout_finding":
        # agenda_watch findings carry the watched feed URL as a Source: line
        m = re.search(r"^Source:\s*(.+)$", text, re.MULTILINE)
        if m:
            return m.group(1).strip()[:200]
        return "scout-finding"
    if kind.startswith("agent_"):
        return kind
    if kind == "note":
        return "user-note"
    return "user"


def _world_of(rel: str) -> str | None:
    m = re.match(r"^sources/(world-[^/]+)/", rel)
    return m.group(1) if m else None


# ── The candidate feed (review queue) ────────────────────────────────────

# What may enter the queue. Bundle-machinery JSON, the auto-doc tree, the
# TOC index, the vector cache, and the Compiled-KB manifest itself never do.
_QUEUE_SUFFIXES = {".md", ".markdown", ".txt"}


def _is_candidate(rel: str) -> bool:
    if rel.startswith("compiled/"):          # auto-docs + our own manifest
        return False
    if rel.startswith(".") or "/." in rel:   # dotfiles, .cache, .wiki-cache
        return False
    if rel == "index.md":                    # the TOC compile_index writes
        return False
    if Path(rel).suffix.lower() not in _QUEUE_SUFFIXES:
        return False
    # world bundle machinery (spec/terms/roster/... json) already excluded by suffix
    return True


def list_pending(pkb_root: Path | None = None, *, limit: int = 500) -> list[dict[str, Any]]:
    """Raw candidates awaiting a human decision: everything indexable that is
    neither already approved nor previously rejected. This is the review
    queue — agents propose (by creating raw content); the human approves."""
    root = pkb_root or _pkb_root()
    if not root.exists():
        return []
    approved = approved_paths(root)
    rejected = _rejected_set(root)
    out: list[dict[str, Any]] = []
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(root).as_posix()
        if rel in approved or rel in rejected or not _is_candidate(rel):
            continue
        text = _read_text(p)
        kind = _kind_of(rel)
        out.append({
            "path": rel,
            "title": _title_of(rel, text),
            "kind": kind,
            "provenance": _provenance_of(rel, text, kind),
            "world": _world_of(rel),
            "preview": text.strip()[:280],
            "sha256": _sha256(text),
        })
        if len(out) >= limit:
            break
    # world terms first (the headline promotion case), then scout findings
    # (time-sensitive "the agents noticed something" items), agent outputs, notes
    order = {"world_term": 0, "scout_finding": 1, "agent_research": 2,
             "agent_experiment": 2, "agent_synthesis": 2,
             "agent_recommendation": 2, "note": 3}
    out.sort(key=lambda r: (order.get(r["kind"], 3), r["title"].lower()))
    return out


def pending_paths(pkb_root: Path | None = None) -> list[str]:
    """Candidate paths awaiting review — the cheap variant of list_pending
    (same walk and filters, but no file reads / titles / hashes). For
    counts and digests: the lab brief and the hero stats hit this per
    request, so it must stay glob-only."""
    root = pkb_root or _pkb_root()
    if not root.exists():
        return []
    approved = approved_paths(root)
    rejected = _rejected_set(root)
    out: list[str] = []
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(root).as_posix()
        if rel in approved or rel in rejected or not _is_candidate(rel):
            continue
        out.append(rel)
    return out


def pending_count(pkb_root: Path | None = None) -> int:
    return len(pending_paths(pkb_root))


# ── The gate: approve / reject / revoke ──────────────────────────────────

def _clean_rel(rel: str) -> str:
    # Defense-in-depth: normalize and reject traversal/absolute paths.
    rel = str(rel).replace("\\", "/").strip().lstrip("/")
    if ".." in Path(rel).parts or not rel:
        raise ValueError(f"illegal path: {rel!r}")
    return rel


def approve(paths: Iterable[str], pkb_root: Path | None = None, *,
            approver: str = "operator") -> list[dict[str, Any]]:
    """Promote raw items into the Compiled KB. Requires each path to exist and
    to be a legitimate candidate; records provenance + a content hash of the
    exact approved bytes. Idempotent per path. Returns the new/updated records.
    """
    root = pkb_root or _pkb_root()
    current = _approved_map(root)
    rejected = _rejected_set(root)
    added: list[dict[str, Any]] = []
    for raw_rel in paths:
        try:
            rel = _clean_rel(raw_rel)
        except ValueError:
            continue  # traversal/absolute paths never enter the Compiled KB
        if not _is_candidate(rel):
            continue
        full = root / rel
        if not full.is_file():
            continue
        text = _read_text(full)
        kind = _kind_of(rel)
        rec = {
            "path": rel,
            "title": _title_of(rel, text),
            "kind": kind,
            "provenance": _provenance_of(rel, text, kind),
            "world": _world_of(rel),
            "sha256": _sha256(text),
            "approved_at": _now(),
            "approved_by": approver,
            "schema": SCHEMA,
        }
        current[rel] = rec
        rejected.discard(rel)
        added.append(rec)
    _save_json(_kb_dir(root) / _APPROVED_FILE,
               {"schema": SCHEMA, "updated_at": _now(), "items": current})
    _save_json(_kb_dir(root) / _REJECTED_FILE,
               {"schema": SCHEMA, "items": sorted(rejected)})
    return added


def dangling_paths(pkb_root: Path | None = None) -> list[str]:
    """Approved paths whose raw file no longer exists on disk.

    The Compiled KB is a *manifest over the raw corpus*, not a copy — so an
    approval is only ever a pointer. When the raw file goes away the pointer
    survives, and because the retrieval gate is a query-time intersection
    (``approved_paths()`` filtered against live search hits), a dangling
    pointer can never match anything. Enough of them and the gate goes
    silently empty: agents get zero approved truth and nothing says why.

    The way this happens in practice is a World switch.
    ``world_mount._sweep_other_worlds()`` deletes every other
    ``sources/world-*/`` staged dir on mount — deliberately, because a World
    IS the lab's dataset — but it has no reason to know about the approval
    manifest, so the approvals for those terms outlive their files.

    Read-only. Never raises.
    """
    root = pkb_root or _pkb_root()
    try:
        if not root.is_dir():
            return []
        return sorted(rel for rel in _approved_map(root) if not (root / rel).is_file())
    except Exception:  # noqa: BLE001
        return []


def prune_dangling(pkb_root: Path | None = None) -> list[str]:
    """Drop approvals whose raw file is gone. Returns the paths removed.

    Reconciliation, not revocation: every path it removes already resolved
    to nothing, so the agent-visible truth is unchanged by definition — what
    changes is that the manifest stops lying about its size, and the review
    queue stops counting corpses.

    Refuses (returns ``[]``, touching nothing) when the pkb root itself is
    missing or unreadable. That case makes EVERY path look deleted, and the
    correct reading is "the lab is misconfigured", not "the operator revoked
    556 approvals" — a prune that fires there would destroy the manifest at
    exactly the moment it is least able to tell the difference.
    """
    root = pkb_root or _pkb_root()
    if not root.is_dir():
        return []
    current = _approved_map(root)
    dropped = sorted(rel for rel in current if not (root / rel).is_file())
    if not dropped:
        return []
    for rel in dropped:
        current.pop(rel, None)
    _save_json(_kb_dir(root) / _APPROVED_FILE,
               {"schema": SCHEMA, "updated_at": _now(), "items": current})
    return dropped


def reject(paths: Iterable[str], pkb_root: Path | None = None) -> int:
    """Dismiss candidates so they stop resurfacing. Reversible (a later
    approve re-admits them). Does not touch the raw file."""
    root = pkb_root or _pkb_root()
    rejected = _rejected_set(root)
    n = 0
    for raw_rel in paths:
        try:
            rel = _clean_rel(raw_rel)
        except ValueError:
            continue
        if rel not in rejected:
            rejected.add(rel)
            n += 1
    _save_json(_kb_dir(root) / _REJECTED_FILE,
               {"schema": SCHEMA, "items": sorted(rejected)})
    return n


def revoke(paths: Iterable[str], pkb_root: Path | None = None) -> int:
    """Remove items from the Compiled KB (un-approve). The raw file remains;
    agents simply stop building on it. Fully reversible."""
    root = pkb_root or _pkb_root()
    current = _approved_map(root)
    n = 0
    for raw_rel in paths:
        rel = str(raw_rel).replace("\\", "/").strip().lstrip("/")
        if rel in current:
            del current[rel]
            n += 1
    _save_json(_kb_dir(root) / _APPROVED_FILE,
               {"schema": SCHEMA, "updated_at": _now(), "items": current})
    return n


# ── The retrieval gate toggle ────────────────────────────────────────────

def gate_enabled() -> bool:
    """Whether agent retrieval is scoped to the Compiled KB. Default ON — the
    hard gate the user asked for. ``ARAIL_APPROVED_ONLY=off`` reverts to the
    legacy raw-corpus behavior (a reversible escape hatch, e.g. for a brand
    new lab with nothing approved yet)."""
    return os.getenv("ARAIL_APPROVED_ONLY", "on").strip().lower() not in (
        "off", "0", "false", "no")


# ── CLI (./arailctl pkb prune | status) ──────────────────────────────────

def _cli(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(
        prog="arailctl pkb",
        description="Inspect and reconcile the Compiled KB (the approved layer agents build on).",
    )
    sub = ap.add_subparsers(dest="op", required=True)
    p_prune = sub.add_parser(
        "prune", help="drop approvals whose raw file no longer exists")
    p_prune.add_argument("--dry-run", action="store_true",
                         help="list what would be dropped, change nothing")
    sub.add_parser("status", help="show live vs dangling approval counts")
    args = ap.parse_args(argv)

    root = _pkb_root()
    if not root.is_dir():
        print(f"pkb root not found: {root}", file=sys.stderr)
        return 3

    approved = approved_paths(root)
    dangling = dangling_paths(root)

    if args.op == "status" or getattr(args, "dry_run", False):
        print(f"approved : {len(approved)}")
        print(f"live     : {len(approved) - len(dangling)}")
        print(f"dangling : {len(dangling)}")
        for rel in dangling[:20]:
            print(f"  - {rel}")
        if len(dangling) > 20:
            print(f"  … and {len(dangling) - 20} more")
        if dangling and args.op == "status":
            print("\nfix: ./arailctl pkb prune")
        return 0

    dropped = prune_dangling(root)
    if not dropped:
        print("Nothing to prune — every approval resolves to a file on disk.")
        return 0
    print(f"Pruned {len(dropped)} approval(s) whose raw file no longer exists.")
    print(f"Compiled KB now holds {len(approved_paths(root))} approved item(s).")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_cli())
