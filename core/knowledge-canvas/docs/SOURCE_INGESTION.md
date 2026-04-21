# Adding a new Source kind

Adding a new source type to the canvas is three changes:

1. Add the kind to the `SourceKind` Literal in `backend/app/models/source.py`
2. Write an adapter function in `backend/app/services/adapters.py`
3. (Optional) Add a color for it in `frontend/src/components/SourceCanvas.tsx`

That's it. The store, routers, query, and frontend don't need changes —
they treat sources generically.

## Example: add a `podcast` kind

**Step 1 — models/source.py**
```python
SourceKind = Literal[
    "markdown", "api_snapshot", "paper", "web_page",
    "dataset", "experiment_log", "image",
    "podcast",      # <-- add this
]
```

**Step 2 — services/adapters.py**
```python
def podcast_adapter(episode: dict) -> Source:
    """
    Expects: {
      "feed_url": "https://...",
      "episode_id": "...",
      "title": "...",
      "transcript": "...",
      "published": "2024-11-15",
    }
    """
    uri = f"{episode['feed_url']}#{episode['episode_id']}"
    return Source(
        id=source_id(uri),
        kind="podcast",
        title=episode["title"],
        uri=uri,
        body_excerpt=(episode.get("transcript") or "")[:4000],
        tags=episode.get("tags", []) + ["podcast"],
        year=_year_from(episode.get("published")),
        meta={"feed_url": episode["feed_url"],
              "duration_s": episode.get("duration_s")},
        ingested_by="agent",
    )
```

**Step 3 — frontend/src/components/SourceCanvas.tsx**
```tsx
export const KIND_COLOR: Record<string, string> = {
  markdown:       "#e8b84c",
  paper:          "#b07be8",
  web_page:       "#6fb8ff",
  api_snapshot:   "#4fd9b8",
  dataset:        "#58d060",
  experiment_log: "#ff8a5c",
  image:          "#f06ec3",
  podcast:        "#ffb347",   // <-- new
};
```

Add a label in `frontend/src/components/LegendPanel.tsx`:
```tsx
const KIND_LABELS: Record<string, string> = {
  // ...
  podcast: "Podcasts",
};
```

Ingest via the generic endpoint:

```bash
curl -X POST http://localhost:8000/api/sources/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "kind": "podcast",
    "title": "Episode 42: Soil Microbiome",
    "uri": "https://feed.example.com/ep42",
    "body_excerpt": "Transcript excerpt...",
    "tags": ["soil", "microbiome"],
    "ingested_by": "agent"
  }'
```

## Why adapters are pure functions

Adapters have no side effects — they take input, return a `Source`.
This matters because:

1. **Testable in isolation.** No database, no network. Unit tests are
   one-liners.
2. **Composable.** The `adapt()` dispatcher in `adapters.py` and the
   `import_from_curator.py` script both call the same adapters with
   different inputs.
3. **Replaceable.** A fork can override any adapter without touching
   storage logic.

## When a new kind *does* need more work

If your new kind needs behavior the canvas doesn't currently have:

- **Custom rendering** (e.g., inline audio player for podcasts): add a
  component in `frontend/src/components/` and switch on `node.kind` in
  `SourceSidebar.tsx`.
- **Custom queries** (e.g., "podcasts longer than 30 min"): use the
  `meta` field at ingest time and filter post-hoc in a new router endpoint.
- **Custom edges** (e.g., `TRANSCRIBED_FROM`): add to the `valid_rels`
  set in `routers/sources.py` and to `_edge_kind_from_rel()` in
  `graph_store.py`.

Ninety percent of new source types need only the three steps above.
