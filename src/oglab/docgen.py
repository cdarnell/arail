"""OGLab docgen — turn the repo's own source into wiki pages.

Walks a repo root and emits markdown pages into
``{pkm_root}/compiled/docs/`` for:

- **Python modules** (``src/oglab/**/*.py``) — parsed via ``ast`` to
  extract the module docstring, the public classes and functions, and
  each of their docstrings. No runtime import required, so optional
  deps don't block the scan.
- **Shell scripts** (``scripts/*.sh``, plus the root ``oglab``
  dispatcher) — extracts the header comment block and the ``usage()``
  body if present.
- **Compose overlays** (``compose/*.yml``) — first comment block +
  top-level service summary (image, ports, volumes).
- **Hand-written guides** (``docs/*.md``, ``README.md``,
  ``CONTRIBUTING.md``, ``SECURITY.md``, ``CODE_OF_CONDUCT.md``) — copied
  into the wiki with computed frontmatter if missing.
- **Configuration** (``.env.example``) — parses comment blocks into a
  configuration reference page.

Every generated page carries ``source:`` and ``generated:`` frontmatter
so the wiki compiler knows it's auto-generated. The compiler NEVER
writes to ``notes/``, ``sources/``, or ``agents/`` — auto-docs are
quarantined to ``compiled/docs/`` so they can never overwrite user
content.

Public entry point: :func:`generate_all`.
"""

from __future__ import annotations

import ast
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

_log = logging.getLogger(__name__)

_FRONT_LINE_RE = re.compile(r"^[#\s]*(.*)$")
_SHELL_USAGE_RE = re.compile(
    r"^(?:usage|print_usage|help|show_help)\s*\(\s*\)\s*\{",
    re.MULTILINE,
)


# ── Frontmatter builder ─────────────────────────────────────────────────

def _frontmatter(
    title: str,
    *,
    section: str,
    tags: Iterable[str],
    aliases: Iterable[str] = (),
    source: Optional[str] = None,
) -> str:
    """Render a minimal YAML frontmatter block matching wiki.parse_frontmatter."""
    lines = ["---", f"title: {title}", f"section: {section}"]
    tags_list = [t for t in tags if t]
    if tags_list:
        lines.append("tags: [" + ", ".join(tags_list) + "]")
    aliases_list = [a for a in aliases if a]
    if aliases_list:
        lines.append("aliases: [" + ", ".join(aliases_list) + "]")
    if source:
        lines.append(f"source: {source}")
    lines.append(
        "generated: " + datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    )
    lines.append("---")
    lines.append("")
    return "\n".join(lines)


# ── Idempotent writer ───────────────────────────────────────────────────

def _write_page(path: Path, body: str) -> bool:
    """Write ``body`` to ``path`` unless the existing file already matches
    byte-for-byte after stripping the ``generated:`` timestamp. Returns
    True if the file was (re)written.

    This is what makes repeated ``wiki build`` runs fast and noise-free:
    we don't thrash on files that haven't changed just because the
    timestamp moves forward a few seconds.
    """
    stripped_new = _strip_generated(body)
    if path.exists():
        try:
            existing = _strip_generated(path.read_text())
            if existing == stripped_new:
                return False
        except OSError:
            pass
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)
    return True


def _strip_generated(text: str) -> str:
    return "\n".join(
        ln for ln in text.splitlines() if not ln.startswith("generated:")
    )


# ── Python module introspection (AST, no imports) ──────────────────────

def _python_module_to_markdown(source_path: Path, rel_to_repo: str) -> str:
    """Parse a Python module and render it as markdown."""
    source = source_path.read_text()
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        return f"# {source_path.stem}\n\n*Could not parse: {e}*\n"

    module_doc = ast.get_docstring(tree) or ""
    module_name = source_path.stem
    display_title = f"{module_name} module"
    slug_tags = ["python", "module"]

    # Walk top-level classes + functions; skip private ones.
    classes: list[tuple[str, Optional[str], list[tuple[str, Optional[str], str]]]] = []
    functions: list[tuple[str, Optional[str], str]] = []

    for node in tree.body:
        if isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
            if node.name.startswith("_") and not node.name.startswith("__"):
                continue
            sig = _render_signature(node)
            functions.append((node.name, ast.get_docstring(node), sig))
        elif isinstance(node, ast.ClassDef):
            if node.name.startswith("_"):
                continue
            class_methods: list[tuple[str, Optional[str], str]] = []
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if sub.name.startswith("_") and not sub.name.startswith("__"):
                        continue
                    class_methods.append(
                        (sub.name, ast.get_docstring(sub), _render_signature(sub))
                    )
            classes.append((node.name, ast.get_docstring(node), class_methods))

    lines: list[str] = []
    lines.append(
        _frontmatter(
            display_title,
            section="docs",
            tags=slug_tags,
            aliases=[module_name, source_path.name],
            source=rel_to_repo,
        )
    )
    lines.append(f"# {display_title}")
    lines.append("")
    lines.append(f"**Source:** `{rel_to_repo}`")
    lines.append("")
    if module_doc:
        lines.append(module_doc.strip())
        lines.append("")

    if classes:
        lines.append("## Classes")
        lines.append("")
        for name, doc, methods in classes:
            lines.append(f"### `{name}`")
            lines.append("")
            if doc:
                lines.append(doc.strip())
                lines.append("")
            if methods:
                lines.append("**Methods:**")
                lines.append("")
                for mname, mdoc, msig in methods:
                    lines.append(f"- `{msig}`")
                    if mdoc:
                        first_line = mdoc.strip().split("\n")[0]
                        lines.append(f"    - {first_line}")
                lines.append("")

    if functions:
        lines.append("## Functions")
        lines.append("")
        for name, doc, sig in functions:
            lines.append(f"### `{sig}`")
            lines.append("")
            if doc:
                lines.append(doc.strip())
                lines.append("")

    if not classes and not functions and not module_doc:
        lines.append("*No public API; this module only contains private helpers "
                     "or constants.*")
        lines.append("")

    return "\n".join(lines)


def _render_signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    args: list[str] = []
    for arg in node.args.args:
        args.append(arg.arg)
    if node.args.vararg:
        args.append("*" + node.args.vararg.arg)
    if node.args.kwarg:
        args.append("**" + node.args.kwarg.arg)
    return f"{node.name}({', '.join(args)})"


# ── Shell script header extraction ─────────────────────────────────────

def _shell_script_to_markdown(source_path: Path, rel_to_repo: str) -> str:
    """Extract the header comment block + usage() body from a shell script."""
    text = source_path.read_text()
    lines = text.splitlines()

    header_lines: list[str] = []
    in_header = False
    for i, ln in enumerate(lines):
        stripped = ln.strip()
        if i == 0 and stripped.startswith("#!"):
            in_header = True
            continue
        if stripped.startswith("#"):
            in_header = True
            header_lines.append(stripped.lstrip("#").strip())
        elif in_header and not stripped:
            header_lines.append("")
        elif in_header and not stripped.startswith("#"):
            break

    header_text = "\n".join(header_lines).strip()

    # Look for a usage() function body.
    usage_match = _SHELL_USAGE_RE.search(text)
    usage_text = ""
    if usage_match:
        depth = 1
        i = usage_match.end()
        while i < len(text) and depth > 0:
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
            i += 1
        body = text[usage_match.end():i - 1]
        usage_text = body.strip()

    # Top-level function names (rough — anything matching `name()` at line start).
    func_names = sorted(set(
        re.findall(r"^([a-zA-Z_][a-zA-Z0-9_]*)\s*\(\s*\)\s*\{", text, re.MULTILINE)
    ))

    script_name = source_path.name
    title = f"{script_name} (shell)"
    md: list[str] = []
    md.append(
        _frontmatter(
            title,
            section="docs",
            tags=["shell", "script"],
            aliases=[source_path.stem, script_name],
            source=rel_to_repo,
        )
    )
    md.append(f"# {title}")
    md.append("")
    md.append(f"**Source:** `{rel_to_repo}`")
    md.append("")
    if header_text:
        md.append("## Overview")
        md.append("")
        md.append(header_text)
        md.append("")
    if usage_text:
        md.append("## Usage")
        md.append("")
        md.append("```text")
        md.append(usage_text)
        md.append("```")
        md.append("")
    if func_names:
        md.append("## Functions")
        md.append("")
        for name in func_names:
            md.append(f"- `{name}()`")
        md.append("")
    return "\n".join(md)


# ── Compose overlay summary ────────────────────────────────────────────

def _compose_file_to_markdown(source_path: Path, rel_to_repo: str) -> str:
    """Render a compose YAML as a summary page.

    No YAML parser — we scan for the leading comment block and the
    top-level ``services:`` / ``image:`` / ``ports:`` / ``volumes:`` keys.
    """
    text = source_path.read_text()
    lines = text.splitlines()

    header: list[str] = []
    for ln in lines:
        stripped = ln.strip()
        if not stripped:
            if header:
                header.append("")
            continue
        if stripped.startswith("#"):
            header.append(stripped.lstrip("#").strip())
        else:
            break
    header_text = "\n".join(header).strip()

    # Pull out first service block — image/ports/volumes.
    image = ""
    ports: list[str] = []
    volumes: list[str] = []
    in_services = False
    service_name = ""
    for ln in lines:
        s = ln.rstrip()
        if re.match(r"^services:\s*$", s):
            in_services = True
            continue
        if not in_services:
            continue
        m_svc = re.match(r"^  ([a-zA-Z0-9_-]+):\s*$", s)
        if m_svc:
            if service_name:
                break
            service_name = m_svc.group(1)
            continue
        if not service_name:
            continue
        m_img = re.match(r"^    image:\s*(.+?)\s*$", s)
        if m_img:
            image = m_img.group(1)
            continue
        m_port = re.match(r'^      - "?([^"]+)"?\s*$', s)
        if m_port and ":" in m_port.group(1):
            ports.append(m_port.group(1))
            continue

    title = f"{source_path.stem} (compose overlay)"
    md: list[str] = []
    md.append(
        _frontmatter(
            title,
            section="docs",
            tags=["compose", "docker", "add-on"],
            aliases=[source_path.stem, source_path.name],
            source=rel_to_repo,
        )
    )
    md.append(f"# {title}")
    md.append("")
    md.append(f"**Source:** `{rel_to_repo}`")
    md.append("")
    if header_text:
        md.append(header_text)
        md.append("")
    if service_name:
        md.append("## Service")
        md.append("")
        md.append(f"- **name:** `{service_name}`")
        if image:
            md.append(f"- **image:** `{image}`")
        if ports:
            md.append("- **ports:**")
            for p in ports:
                md.append(f"    - `{p}`")
        md.append("")
    md.append("## How to start")
    md.append("")
    md.append(f"```bash\ndocker compose -f {rel_to_repo} up -d\n```")
    md.append("")
    return "\n".join(md)


# ── Guide copy with frontmatter enrichment ─────────────────────────────

def _guide_to_markdown(source_path: Path, rel_to_repo: str) -> str:
    """Copy a hand-written doc, injecting frontmatter if it's missing."""
    raw = source_path.read_text()
    # If the file already has frontmatter, trust it.
    from oglab.wiki import parse_frontmatter
    meta, body = parse_frontmatter(raw)
    if meta:
        return raw  # user has curated it, don't touch
    title = source_path.stem.replace("-", " ").replace("_", " ").title()
    fm = _frontmatter(
        title,
        section="docs",
        tags=["guide"],
        aliases=[source_path.stem],
        source=rel_to_repo,
    )
    return fm + body


# ── .env.example → configuration reference ─────────────────────────────

def _env_example_to_markdown(source_path: Path, rel_to_repo: str) -> str:
    text = source_path.read_text()
    lines = text.splitlines()

    md: list[str] = []
    md.append(
        _frontmatter(
            ".env.example (configuration reference)",
            section="docs",
            tags=["configuration", "env", "reference"],
            aliases=["env-vars", "configuration"],
            source=rel_to_repo,
        )
    )
    md.append("# Configuration reference")
    md.append("")
    md.append(
        "Auto-generated from `.env.example`. Copy that file to `.env` and "
        "edit the values you need; the lab reads env vars at startup via "
        "`python-dotenv`."
    )
    md.append("")

    # Walk the file, grouping consecutive comment lines as a doc block
    # followed by the var line(s) they describe.
    buffer: list[str] = []
    for ln in lines:
        stripped = ln.strip()
        if not stripped:
            buffer = []
            continue
        if stripped.startswith("#"):
            clean = stripped.lstrip("#").strip()
            if clean.startswith("---"):
                continue  # section dividers
            buffer.append(clean)
            continue
        # Otherwise, it's a var line (KEY=value).
        m = re.match(r"^([A-Z_][A-Z0-9_]*)\s*=\s*(.*)$", stripped)
        if not m:
            continue
        key, val = m.group(1), m.group(2)
        md.append(f"### `{key}`")
        md.append("")
        if buffer:
            md.append(" ".join(buffer))
            md.append("")
        md.append(f"**Default:** `{val or '(empty)'}`")
        md.append("")
        buffer = []

    return "\n".join(md)


# ── Top-level driver ───────────────────────────────────────────────────

def generate_all(repo_root: Path, pkm_root: Path) -> dict[str, int]:
    """Generate the full ``compiled/docs/`` tree from ``repo_root``.

    Returns a dict of counts: ``{"python": N, "shell": N, "compose": N,
    "guide": N, "env": N, "written": N}``. The ``written`` count is
    lower than the sum when files were already up-to-date and skipped.
    """
    out_base = pkm_root / "compiled" / "docs"
    counts = {"python": 0, "shell": 0, "compose": 0, "guide": 0, "env": 0, "written": 0}

    # 1. Python modules under src/oglab
    py_dir = repo_root / "src" / "oglab"
    if py_dir.is_dir():
        for py in sorted(py_dir.rglob("*.py")):
            if py.name == "__init__.py" or py.name.startswith("_"):
                # Skip dunder-only init modules (they rarely carry public API).
                try:
                    if not ast.get_docstring(ast.parse(py.read_text())):
                        continue
                except (OSError, SyntaxError):
                    continue
            rel = py.relative_to(repo_root).as_posix()
            try:
                body = _python_module_to_markdown(py, rel)
            except Exception as e:  # noqa: BLE001
                _log.warning("docgen: skipping %s (%s)", rel, e)
                continue
            slug = py.relative_to(py_dir).with_suffix("").as_posix().replace("/", "-")
            out = out_base / "modules" / f"oglab-{slug}.md"
            counts["python"] += 1
            if _write_page(out, body):
                counts["written"] += 1

    # 2. Shell scripts + oglab dispatcher
    shell_targets = list(sorted((repo_root / "scripts").glob("*.sh"))) if (repo_root / "scripts").is_dir() else []
    dispatcher = repo_root / "oglab"
    if dispatcher.is_file():
        shell_targets.append(dispatcher)
    for sh in shell_targets:
        rel = sh.relative_to(repo_root).as_posix()
        try:
            body = _shell_script_to_markdown(sh, rel)
        except Exception as e:  # noqa: BLE001
            _log.warning("docgen: skipping %s (%s)", rel, e)
            continue
        out = out_base / "scripts" / f"{sh.stem or sh.name}.md"
        counts["shell"] += 1
        if _write_page(out, body):
            counts["written"] += 1

    # 3. Compose overlays
    compose_dir = repo_root / "compose"
    if compose_dir.is_dir():
        for ym in sorted(list(compose_dir.glob("*.yml")) + list(compose_dir.glob("*.yaml"))):
            rel = ym.relative_to(repo_root).as_posix()
            try:
                body = _compose_file_to_markdown(ym, rel)
            except Exception as e:  # noqa: BLE001
                _log.warning("docgen: skipping %s (%s)", rel, e)
                continue
            out = out_base / "compose" / f"{ym.stem}.md"
            counts["compose"] += 1
            if _write_page(out, body):
                counts["written"] += 1

    # 4. Hand-written guides
    guide_targets: list[Path] = []
    for name in ("README.md", "CONTRIBUTING.md", "SECURITY.md", "CODE_OF_CONDUCT.md"):
        p = repo_root / name
        if p.is_file():
            guide_targets.append(p)
    docs_dir = repo_root / "docs"
    if docs_dir.is_dir():
        guide_targets.extend(sorted(docs_dir.glob("*.md")))
    for g in guide_targets:
        rel = g.relative_to(repo_root).as_posix()
        try:
            body = _guide_to_markdown(g, rel)
        except Exception as e:  # noqa: BLE001
            _log.warning("docgen: skipping %s (%s)", rel, e)
            continue
        out = out_base / "guides" / f"{g.stem}.md"
        counts["guide"] += 1
        if _write_page(out, body):
            counts["written"] += 1

    # 5. .env.example configuration reference
    env_path = repo_root / ".env.example"
    if env_path.is_file():
        try:
            body = _env_example_to_markdown(env_path, ".env.example")
            out = out_base / "configuration" / "env-vars.md"
            counts["env"] += 1
            if _write_page(out, body):
                counts["written"] += 1
        except Exception as e:  # noqa: BLE001
            _log.warning("docgen: env-example failed (%s)", e)

    return counts
