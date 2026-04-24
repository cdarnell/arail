"""Draft a first-pass research program from a goal.

The lab's autoresearch loop expects three files in
``lab/pkb/research/``: ``program.md`` (what to research), ``prepare.py``
(measurement contract), and ``train.py`` (apply step). The first and
last are auto-drafted by this module the moment a goal is set; the
user then edits them. ``prepare.py`` is sticky and never touched here.

Design notes
------------
* **Templated, not LLM-driven.** The parsed_goal dict already came out
  of an LLM call (see ``arail.portal.app._parse_goal``). Reusing its
  structure keeps the drafter cheap and deterministic. A second LLM
  pass for hypothesis generation is a follow-up milestone — slot it
  in by extending ``_render_hypotheses``.
* **Refuses to overwrite by default.** Once the user has edited
  ``program.md``, a re-set goal must not clobber that work. The portal
  exposes a Re-draft button that explicitly passes ``force=True``.
* **Air-gap aware.** Without ``LAB_MODE=hybrid +
  ARAIL_AUTORESEARCH_FETCH_EXTRAS=1`` the Sources section uses only
  the curated YAML + KB hits. Live fetch is opt-in.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from arail.research.train_template import TRAIN_PY_TEMPLATE


_DEFAULT_RESEARCH_DIR = Path("lab/pkb/research")
_DEFAULT_SOURCES_PATH = Path(__file__).parent / "default_sources.yaml"


@dataclass
class DraftResult:
    """What the drafter did, in machine-readable form."""

    wrote: bool
    program_path: Path
    train_path: Path
    reason: str = ""
    fetched_external: bool = False
    sources_count: int = 0
    hypothesis_count: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "wrote": self.wrote,
            "program_path": str(self.program_path),
            "train_path": str(self.train_path),
            "reason": self.reason,
            "fetched_external": self.fetched_external,
            "sources_count": self.sources_count,
            "hypothesis_count": self.hypothesis_count,
        }


def load_default_sources(path: Path | None = None) -> list[dict[str, str]]:
    """Read the curated default sources from disk. Returns []
    on parse failure so the drafter degrades gracefully."""
    target = path or _DEFAULT_SOURCES_PATH
    try:
        data = yaml.safe_load(target.read_text())
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    out: list[dict[str, str]] = []
    for entry in data:
        if isinstance(entry, dict) and entry.get("title") and entry.get("url"):
            out.append({
                "title": str(entry["title"]),
                "url": str(entry["url"]),
                "why": str(entry.get("why", "")),
            })
    return out


def draft_program(
    *,
    goal_record: dict[str, Any],
    kb_hits: list[dict[str, Any]] | None = None,
    research_dir: Path | None = None,
    force: bool = False,
    fetch_external: bool = False,
) -> DraftResult:
    """Draft program.md (and the train.py stub) for ``goal_record``.

    Parameters
    ----------
    goal_record:
        Output of ``goal_store.get_current()`` — must include
        ``goal_text`` and ``parsed`` dict.
    kb_hits:
        Output of ``arail.pkb.search(goal_text)``, or None to skip
        the KB section.
    research_dir:
        Override target dir; defaults to ``lab/pkb/research/``.
    force:
        Overwrite an existing program.md. The default ``False`` is
        the safe path so re-setting a goal doesn't blow away user
        edits — only the explicit "Re-draft" button uses ``True``.
    fetch_external:
        If True AND the lab is not airgapped, fetch a small number
        of related abstracts and append to Sources. Stub for now —
        the real Browser/Curator delegation is a follow-up.
    """
    target_dir = (research_dir or _DEFAULT_RESEARCH_DIR)
    program_path = target_dir / "program.md"
    train_path = target_dir / "train.py"

    if program_path.exists() and not force:
        # Special case: the lab's startup auto-seeder
        # (arail.agents.builtin_seed) bakes in a generic AeroLLM
        # research template before the user sets a goal. Once a real
        # goal is set, that static template is stale by definition —
        # transparently replace it. We detect it by the unique
        # ``auto_goal:`` frontmatter key the seeder writes (and which
        # this drafter never produces).
        if not _is_static_seed_template(program_path):
            return DraftResult(
                wrote=False,
                program_path=program_path,
                train_path=train_path,
                reason="program.md exists — pass force=True to overwrite",
            )

    target_dir.mkdir(parents=True, exist_ok=True)

    parsed = goal_record.get("parsed") or {}
    goal_text = goal_record.get("goal_text", "") or parsed.get("primary_objective", "")
    domain = parsed.get("domain", "general")

    # Resolve sources: curated defaults + KB hits (always), plus
    # optional live fetches (opt-in, airgap-gated).
    defaults = load_default_sources()
    kb_section = _summarize_kb_hits(kb_hits or [])
    fetched: list[dict[str, str]] = []
    fetched_flag = False
    if fetch_external and _allow_live_fetch():
        fetched = _fetch_extra_sources(goal_text)
        fetched_flag = bool(fetched)

    body = _render_program_md(
        goal_text=goal_text,
        parsed=parsed,
        kb_hits=kb_hits or [],
        default_sources=defaults,
        fetched_sources=fetched,
        fetched_flag=fetched_flag,
    )
    program_path.write_text(body)

    # Stub train.py is idempotent — only write it if missing so we
    # don't clobber user edits even on a force re-draft.
    if not train_path.exists():
        train_path.write_text(TRAIN_PY_TEMPLATE)

    return DraftResult(
        wrote=True,
        program_path=program_path,
        train_path=train_path,
        reason="drafted",
        fetched_external=fetched_flag,
        sources_count=len(defaults) + len(fetched) + len(kb_section),
        hypothesis_count=len(parsed.get("sub_objectives") or []),
    )


# -- internals ------------------------------------------------------------

def _allow_live_fetch() -> bool:
    """Live external fetch is opt-in: hybrid mode AND explicit env."""
    mode = os.getenv("LAB_MODE", os.getenv("ARAIL_MODE", "airgapped")).strip().lower()
    if mode == "airgapped":
        return False
    return os.getenv("ARAIL_AUTORESEARCH_FETCH_EXTRAS", "0") == "1"


def _is_static_seed_template(program_path: Path) -> bool:
    """True if the on-disk program.md is the lab's static auto-seed
    rather than a real draft or user-edited file.

    The seeder (``arail.agents.builtin_seed``) writes an ``auto_goal:``
    key in the YAML frontmatter; this drafter never produces that key.
    Reading just the first ~40 lines is enough — the frontmatter
    block is always at the top.
    """
    try:
        with program_path.open() as f:
            head = "".join(line for _, line in zip(range(40), f))
    except OSError:
        return False
    return "auto_goal:" in head and "auto_drafted: true" not in head


def _fetch_extra_sources(goal_text: str) -> list[dict[str, str]]:
    """Stub — when the user enables external fetch we'll route through
    the existing Curator/Browser path. Returning [] keeps the rest of
    the drafter happy until that wiring lands."""
    _ = goal_text  # silence unused
    return []


def _summarize_kb_hits(hits: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Reduce KB hits to the fields the markdown template wants.

    We drop structural noise (manifests, generated indexes, wiki
    cache) — same filter the researcher and dashboard use, kept here
    so the drafter doesn't need to import either.
    """
    out: list[dict[str, str]] = []
    for h in hits:
        path = (h.get("path") or "").lower()
        if (
            path.endswith(".json")
            or path.endswith("/index.md")
            or path == "index.md"
            or "/.wiki-cache/" in path
            or "/manifest" in path
        ):
            continue
        out.append({
            "name": str(h.get("name") or h.get("path") or "?"),
            "path": str(h.get("path") or ""),
            "score": f"{(h.get('score', 0.0) * 100):.0f}%" if h.get("score") is not None else "",
        })
        if len(out) >= 5:
            break
    return out


def _render_hypotheses(parsed: dict[str, Any]) -> list[str]:
    """Pull hypotheses out of the parsed goal's sub-objectives.

    Templated for now — the LLM call that produced ``parsed`` already
    rewrote the user's free-form goal into measurable sub-objectives,
    so we surface them as the testable hypotheses without a second
    LLM pass.
    """
    subs = parsed.get("sub_objectives") or []
    if isinstance(subs, list) and subs:
        return [str(s).strip() for s in subs if str(s).strip()]
    primary = parsed.get("primary_objective", "")
    if primary:
        return [str(primary).strip()]
    return []


def _render_program_md(
    *,
    goal_text: str,
    parsed: dict[str, Any],
    kb_hits: list[dict[str, Any]],
    default_sources: list[dict[str, str]],
    fetched_sources: list[dict[str, str]],
    fetched_flag: bool,
) -> str:
    drafted_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    domain = parsed.get("domain", "general")
    success_metrics = parsed.get("success_metrics") or {}
    hypotheses = _render_hypotheses(parsed)
    kb_section = _summarize_kb_hits(kb_hits)

    lines: list[str] = []
    # ── Frontmatter ──
    lines.append("---")
    lines.append(f"title: {_escape_yaml(goal_text or 'Research program (draft)')}")
    lines.append("section: research")
    lines.append("tags: [auto-drafted, program, research]")
    lines.append(f"goal: {_escape_yaml(goal_text)}")
    lines.append(f"intent: {_escape_yaml(domain)}")
    lines.append(f"drafted_at: {drafted_at}")
    lines.append("auto_drafted: true")
    lines.append(f"fetched_external: {'true' if fetched_flag else 'false'}")
    lines.append("---")
    lines.append("")

    # ── Header + Goal ──
    lines.append(f"# Research program — {goal_text or '(unset goal)'}")
    lines.append("")
    lines.append("> First-pass draft generated by the lab the moment you")
    lines.append("> set the goal. **You're meant to edit this file.** The")
    lines.append("> autoresearch loop reads it; what you write here is")
    lines.append("> what gets tested. See `lab/pkb/research/README.md` for")
    lines.append("> the full recipe contract.")
    lines.append("")
    lines.append("## Goal")
    lines.append("")
    primary = parsed.get("primary_objective") or goal_text
    lines.append(str(primary))
    lines.append("")

    # ── Hypotheses ──
    lines.append("## Hypotheses worth testing")
    lines.append("")
    if hypotheses:
        for i, h in enumerate(hypotheses, 1):
            lines.append(f"{i}. **{h}** — measurable in `prepare.py`'s primary metric.")
    else:
        lines.append("_No sub-objectives parsed from the goal — write your "
                     "own hypotheses here, one per testable claim._")
    lines.append("")

    # ── Success criteria ──
    lines.append("## Success criteria")
    lines.append("")
    if success_metrics and isinstance(success_metrics, dict):
        for k, v in success_metrics.items():
            lines.append(f"- **{k}** — {v}")
    else:
        lines.append("- A candidate \"ships\" when the measurement delta")
        lines.append("  reproduces across at least 3 separate runs and the")
        lines.append("  validation guardrails in `prepare.py` pass.")
    lines.append("")

    # ── Knobs (empty placeholder block) ──
    lines.append("## Knobs")
    lines.append("")
    lines.append("Optional — the autoresearch loop will read a fenced YAML")
    lines.append("block here and use it instead of its hardcoded candidates.")
    lines.append("Format: a list of `{label: ..., knobs: {...}}` entries.")
    lines.append("")
    lines.append("```yaml")
    lines.append("# Add your candidate variants here. Example:")
    lines.append("# - label: prefetch-2-layers")
    lines.append("#   knobs:")
    lines.append("#     prefetch_lookahead: 2")
    lines.append("```")
    lines.append("")

    # ── Sources ──
    lines.append("## Sources")
    lines.append("")
    if kb_section:
        lines.append("### From your knowledge base")
        lines.append("")
        for hit in kb_section:
            score = f" ({hit['score']})" if hit.get("score") else ""
            lines.append(f"- [{hit['name']}](../{hit['path']}){score}")
        lines.append("")
    if default_sources:
        lines.append("### Curated defaults — \"LLMs on disk\"")
        lines.append("")
        for src in default_sources:
            why = f" — {src['why']}" if src.get("why") else ""
            lines.append(f"- [{src['title']}]({src['url']}){why}")
        lines.append("")
    if fetched_sources:
        lines.append("### Fetched (external)")
        lines.append("")
        for src in fetched_sources:
            lines.append(f"- [{src['title']}]({src['url']})")
        lines.append("")
    if not (kb_section or default_sources or fetched_sources):
        lines.append("_No sources yet — drop files into the Knowledge tab "
                     "or edit this section directly._")
        lines.append("")

    # ── Constraints (locked guidance) ──
    lines.append("## Constraints")
    lines.append("")
    lines.append("- **Do NOT modify [prepare.py](prepare.py)** — it's the")
    lines.append("  validation contract. Changing it means the agent is")
    lines.append("  grading its own homework.")
    lines.append("- **Do NOT skip the baseline.** Every variant needs a")
    lines.append("  pre-change measurement.")
    lines.append("- **Log every experiment**, not just the winners. The")
    lines.append("  failures are often where the next hypothesis comes from.")
    lines.append("")

    # ── Footer ──
    lines.append("---")
    lines.append("")
    lines.append("Drafted automatically. Edit any section to course-correct;")
    lines.append("the autoresearch loop reads what's here, not what was")
    lines.append("originally drafted. Click **Re-draft** on the dashboard's")
    lines.append("\"Lab knows\" panel to regenerate from the current goal")
    lines.append("(this clobbers your edits).")
    lines.append("")

    return "\n".join(lines)


def _escape_yaml(value: str) -> str:
    """Quote-and-escape a value for safe single-line YAML embedding."""
    if value is None:
        return ""
    s = str(value).replace("\n", " ").strip()
    if not s:
        return ""
    # Wrap in double quotes if there are characters YAML would
    # interpret. Simpler than full PyYAML-quoting for the few fields
    # we emit.
    needs_quote = any(c in s for c in ":#[]{}|>&*!%@`'\"")
    if needs_quote or s[0] in "-?:,":
        s = '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return s
