---
title: docgen module
section: docs
tags: [python, module]
aliases: [docgen, docgen.py]
source: src/oglab/docgen.py
generated: 2026-04-15T00:51:55Z
---

# docgen module

**Source:** `src/oglab/docgen.py`

OGLab docgen — turn the repo's own source into wiki pages.

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

## Functions

### `generate_all(repo_root, pkm_root)`

Generate the full ``compiled/docs/`` tree from ``repo_root``.

Returns a dict of counts: ``{"python": N, "shell": N, "compose": N,
"guide": N, "env": N, "written": N}``. The ``written`` count is
lower than the sum when files were already up-to-date and skipped.
