"""Docgen smoke tests — repo-source → wiki page generation."""

from __future__ import annotations

from pathlib import Path

import pytest

from arail import docgen, wiki


@pytest.fixture()
def fake_repo(tmp_path: Path) -> Path:
    """Build a tiny synthetic repo with one of every source family."""
    repo = tmp_path / "repo"
    (repo / "src" / "fakelab" / "sub").mkdir(parents=True)
    (repo / "scripts").mkdir()
    (repo / "compose").mkdir()
    (repo / "docs").mkdir()

    (repo / "src" / "fakelab" / "__init__.py").write_text(
        '"""Fakelab package init — used by tests."""\n'
    )
    (repo / "src" / "fakelab" / "core.py").write_text(
        '"""Core — the fake module under test."""\n'
        '\n\n'
        'PUBLIC_CONST = 42\n\n'
        'class Widget:\n'
        '    """A widget. Does widget things."""\n'
        '    def wiggle(self, amount: int) -> None:\n'
        '        """Wiggle the widget by the given amount."""\n'
        '        pass\n'
        '    def _private(self):\n'
        '        pass\n\n'
        'def public_fn(x: int) -> int:\n'
        '    """Double x."""\n'
        '    return x * 2\n\n'
        'def _helper():\n'
        '    pass\n'
    )
    (repo / "scripts" / "doit.sh").write_text(
        '#!/usr/bin/env bash\n'
        '# doit.sh — does the thing.\n'
        '#\n'
        '# Longer description here over multiple lines.\n'
        'set -euo pipefail\n'
        '\n'
        'usage() {\n'
        '    echo "Usage: doit.sh [--force]"\n'
        '    echo "  --force   bypass confirmation"\n'
        '}\n'
        '\n'
        'helper_fn() {\n'
        '    echo helper\n'
        '}\n'
        '\n'
        '"$@"\n'
    )
    (repo / "compose" / "app.yml").write_text(
        '# Fake compose overlay — runs a tiny web app.\n'
        '# Bind to 127.0.0.1 by default.\n'
        'services:\n'
        '  app:\n'
        '    image: example/app:latest\n'
        '    ports:\n'
        '      - "127.0.0.1:8000:8000"\n'
    )
    (repo / "README.md").write_text("# Fake repo\n\nHello.\n")
    (repo / "docs" / "how-to.md").write_text("# How to\n\nDo things.\n")
    (repo / ".env.example").write_text(
        "# -----\n"
        "# Toggle X — controls whether X does its thing.\n"
        "# -----\n"
        "X_ENABLED=true\n"
        "\n"
        "# Y mode — options: fast | slow\n"
        "Y_MODE=fast\n"
    )
    return repo


@pytest.fixture()
def fake_pkm(tmp_path: Path) -> Path:
    """Empty PKB scaffold for docgen to write into."""
    root = tmp_path / "pkm"
    for sub in ("compiled/docs", "inbox", "notes"):
        (root / sub).mkdir(parents=True)
    return root


def test_generate_all_counts(fake_repo: Path, fake_pkm: Path, monkeypatch):
    # Point docgen's module-under-test scanner at our fake src/fakelab;
    # the real docgen hardcodes src/arail. We patch the attribute so the
    # generic walker looks at our fake package.
    monkeypatch.setattr(docgen, "_log", docgen._log)  # no-op, keeps import
    # Monkey-patch the scan path by temporarily renaming the folder
    # structure docgen expects. Instead of that, we call the lower-level
    # helpers directly on the fixture files.
    counts = docgen.generate_all(fake_repo, fake_pkm)
    # We only hit the branches that exist in the fake repo:
    # - python (fakelab is under src/, not src/arail, so docgen skips it)
    # - shell (scripts/doit.sh)
    # - compose (compose/app.yml)
    # - guide (README.md, docs/how-to.md)
    # - env (.env.example)
    assert counts["shell"] == 1
    assert counts["compose"] == 1
    assert counts["guide"] == 2
    assert counts["env"] == 1
    assert counts["written"] >= 4


def test_python_module_to_markdown_extracts_public_api(fake_repo: Path):
    src = fake_repo / "src" / "fakelab" / "core.py"
    md = docgen._python_module_to_markdown(src, "src/fakelab/core.py")
    assert "# core module" in md
    assert "Core — the fake module under test." in md
    # Public class + method rendered
    assert "`Widget`" in md
    assert "wiggle(self, amount)" in md
    # Public function rendered
    assert "public_fn(x)" in md
    # Private helpers skipped
    assert "_private" not in md
    assert "_helper" not in md
    # Frontmatter present
    assert md.startswith("---")
    assert "source: src/fakelab/core.py" in md


def test_shell_header_extraction(fake_repo: Path):
    sh = fake_repo / "scripts" / "doit.sh"
    md = docgen._shell_script_to_markdown(sh, "scripts/doit.sh")
    assert "doit.sh — does the thing." in md
    assert "Longer description" in md
    assert "## Usage" in md
    assert "--force" in md
    assert "helper_fn()" in md
    assert md.startswith("---")


def test_compose_file_to_markdown(fake_repo: Path):
    yml = fake_repo / "compose" / "app.yml"
    md = docgen._compose_file_to_markdown(yml, "compose/app.yml")
    assert "Fake compose overlay" in md
    assert "`app`" in md
    assert "example/app:latest" in md
    assert "127.0.0.1:8000:8000" in md
    assert "docker compose -f compose/app.yml up -d" in md


def test_env_example_to_markdown(fake_repo: Path):
    env = fake_repo / ".env.example"
    md = docgen._env_example_to_markdown(env, ".env.example")
    assert "# Configuration reference" in md
    assert "`X_ENABLED`" in md
    assert "`Y_MODE`" in md
    assert "Toggle X" in md
    assert "Default:** `true`" in md


def test_guide_preserves_existing_frontmatter(fake_repo: Path):
    g = fake_repo / "docs" / "how-to.md"
    # Rewrite with frontmatter to confirm it's preserved.
    g.write_text("---\ntitle: Custom\n---\n# Body\n")
    out = docgen._guide_to_markdown(g, "docs/how-to.md")
    assert "title: Custom" in out
    assert "generated:" not in out  # unchanged


def test_guide_injects_frontmatter_when_missing(fake_repo: Path):
    g = fake_repo / "docs" / "how-to.md"  # has no frontmatter
    out = docgen._guide_to_markdown(g, "docs/how-to.md")
    assert out.startswith("---")
    assert "source: docs/how-to.md" in out


def test_idempotent_regeneration_skips_unchanged(fake_repo: Path, fake_pkm: Path):
    counts1 = docgen.generate_all(fake_repo, fake_pkm)
    counts2 = docgen.generate_all(fake_repo, fake_pkm)
    # Second run should write 0 files (all already up-to-date).
    assert counts2["written"] == 0
    # But the discovery counts match.
    for key in ("shell", "compose", "guide", "env"):
        assert counts1[key] == counts2[key]


def test_generated_pages_integrate_into_wiki_index(fake_repo: Path, fake_pkm: Path):
    # Generate docs.
    docgen.generate_all(fake_repo, fake_pkm)
    # Compile the wiki index over the PKB tree that contains them.
    pages = wiki.build_page_index(fake_pkm)
    # At least the shell + compose + guides + env pages should be present.
    slugs = list(pages.keys())
    assert any("doit" in s for s in slugs)
    assert any("app" in s for s in slugs)
    assert any("env-vars" in s for s in slugs)
