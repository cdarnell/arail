---
title: wiki_routes module
section: docs
tags: [python, module]
aliases: [wiki_routes, wiki_routes.py]
source: src/oglab/portal/wiki_routes.py
generated: 2026-04-22T01:03:30Z
---

# wiki_routes module

**Source:** `src/oglab/portal/wiki_routes.py`

OGLab Wiki — FastAPI router.

Registered in ``portal/app.py`` as ``app.include_router(wiki_router)``.
Kept in its own module so the wiki feature can be stripped by a fork
that wants to ship without it — just delete this file and remove the
one include line.

## Functions

### `wiki_root_redirect()`

The unified /knowledge page absorbed the wiki landing. Keep the
old URL alive with a 302 redirect so bookmarks don't break. The
per-page reader (/wiki/<slug>) and the graph (/wiki/graph) still
live below for deep-link access.

### `wiki_landing(request)`

### `wiki_graph_page(request, embed)`

### `wiki_tag_page(request, tag)`

### `wiki_search_page(request, q)`

### `wiki_page(request, slug)`

### `api_pages()`

### `api_page(slug)`

### `api_graph()`

### `api_status()`

Compact summary for the dashboard Curate card.

### `api_search(q)`

### `api_rebuild()`
