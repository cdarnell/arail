---
title: wiki module
section: docs
tags: [python, module]
aliases: [wiki, wiki.py]
source: src/oglab/wiki.py
generated: 2026-04-15T01:00:48Z
---

# wiki module

**Source:** `src/oglab/wiki.py`

OGLab Wiki — the documentation-as-code compiler.

Scans a PKM tree, parses frontmatter and wikilinks, resolves backlinks,
builds a knowledge graph, and caches the result to disk so the portal
can serve wiki pages fast.

Design:
- Pure functions, no async, no portal coupling — unit-testable.
- Extends ``oglab.pkm`` rather than replacing it; ``pkm.compile_index``
  still produces the flat index for users who don't want a wiki.
- Frontmatter is optional on user pages, required on auto-generated
  pages from :mod:`oglab.docgen`.
- Wikilinks follow Obsidian syntax: ``[[target]]``, ``[[target|alias]]``,
  ``[[target#heading]]``.

Exposes a CLI entry point: ``python -m oglab.wiki build``.

## Classes

### `WikiRef`

A parsed ``[[target]]`` reference from page body.

### `Page`

One page in the wiki, after parsing.

**Methods:**

- `to_dict(self)`

### `WikiGraph`

### `WikiBuildResult`

## Functions

### `slugify(text)`

Convert a title or path-fragment into a url-safe slug.

Lowercases, strips unicode accents, replaces non-word chars with
hyphens, collapses repeats, trims.

### `parse_frontmatter(text)`

Split a ``---YAML---\n`` block from the body.

Tolerant — any parse failure yields ``({}, text)`` and logs a warning.
Only a tiny subset of YAML is supported (top-level key: value, and
list values expressed as ``[a, b, c]``). That keeps us off a heavy
YAML dependency while covering everything our frontmatter contract
actually uses (title, section, tags, aliases, source, generated).

### `parse_wikilinks(body)`

Extract every ``[[target]]`` reference from a body.

Handles the three forms:
  - ``[[target]]``
  - ``[[target|alias]]``
  - ``[[target#heading]]`` (anchor also combines with alias)

Skips fenced and inline code blocks so code examples that
*mention* wikilinks don't get parsed as real ones.

### `build_page_index(pkm_root)`

Walk the PKM tree, parse every ``*.md`` file, return slug→Page.

Hidden files, the ``.wiki-cache`` directory, and the ``inbox/`` are
excluded.

### `resolve_links(pages)`

Resolve outgoing wikilink targets to slugs and invert into backlinks.

Mutates pages in place. Runs in O(pages * links) which is fine for
the scale we care about (~1k pages).

### `build_link_graph(pages)`

Build the knowledge graph from resolved pages.

Node shape matches ``/api/system/graph`` so the existing Canvas
renderer can draw it with no changes.

### `render_page(page, pages)`

Public wrapper — render a page's body to HTML.

### `compile_wiki(pkm_root, repo_root)`

Top-level compile: parse, resolve, graph, optionally generate from
source, and write the cache manifest.

``repo_root`` enables the docgen pass. When omitted, only user content
under ``pkm_root`` is compiled.

### `load_manifest(pkm_root)`

Load the cached manifest, rebuilding once if absent.
