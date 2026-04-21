# Graph RAG patterns in the canvas

Three hybrid query patterns that neither LanceDB nor Neo4j can do
alone. All operate on the `Source` graph.

## 1. Traversal-filtered semantic search

> "Papers (not API pulls) linked 1-3 hops from the 'Cover crop'
> experiment, excluding #hardware, ranked by similarity to
> 'nitrogen fixation microbiome'."

```cypher
MATCH (anchor:Source {title: 'Cover crop experiment'})-[*1..3]-(n:Source)
WHERE n.kind = 'paper'
  AND NONE(t IN n.tags WHERE t = 'hardware')
RETURN n.id AS id
```

Take those IDs, pass them to LanceDB as a filter, vector search against
the query text embedding:

```python
candidate_ids = [r["id"] for r in neo4j_result]
hits = store.table.search(query_vec) \
    .where(f"id IN {tuple(candidate_ids)}") \
    .limit(25).to_list()
```

You get the intersection of structural relevance (near an anchor) and
semantic relevance (close to a query vector).

## 2. Evolution tracing

> "Show how understanding of soil health evolved across experiments
> over the last 2 years."

```cypher
MATCH (s:Source {kind: 'experiment_log'})
WHERE s.year >= 2024
RETURN s.id, s.title, s.year
ORDER BY s.year ASC, s.title ASC
```

Then for each experiment, pull its vector from LanceDB and compute
cosine distance to the previous step:

```python
prev_vec = None
for exp in ordered_experiments:
    vec = store.table.search().where(f"id = '{exp['id']}'").limit(1).to_list()[0]["vector"]
    if prev_vec is not None:
        drift = 1 - cosine(prev_vec, vec)
        # large drift = conceptual shift worth narrating
    prev_vec = vec
```

Large drift between adjacent timestamps = conceptual shifts the lab
should surface to the user. The Insight Generator uses this pattern.

## 3. Bridge detection

> "Which of my sources connect otherwise-unrelated clusters?"

```cypher
MATCH (n:Source)-[]-(m:Source)
WITH n, collect(DISTINCT m) AS neighbors
WHERE size(neighbors) >= 3
RETURN n.id, [x IN neighbors | x.id] AS neighbor_ids
```

For each candidate, pull neighbor vectors from LanceDB and compute
average pairwise distance:

```python
for candidate in candidates:
    neighbor_vecs = [get_vector(nid) for nid in candidate["neighbor_ids"]]
    pairwise = [cosine_dist(a, b) for a in neighbor_vecs for b in neighbor_vecs if id(a) < id(b)]
    bridge_score = mean(pairwise)  # high = neighbors are semantically far apart
```

High bridge score = this source is a **bridge note**, connecting
otherwise-separate parts of the knowledge graph. These are the highest-
leverage sources to cultivate — prompt the user to expand them.

## Why this beats vector-only RAG

Standard RAG (flat vector DB) can only answer: "what's semantically near
this query?" That's fine for question answering, bad for lab curation
because it loses all provenance and relationship structure.

With the Graph RAG setup, the Insight Generator can answer things like:

- "This claim is supported by 3 papers and 2 experiments, but
  contradicted by one USDA pull." (Needs: kinds + relation types)
- "You haven't looked at anything new on this topic in 4 months."
  (Needs: temporal order over nodes tagged X)
- "Your 'Cover crop' and 'Pest management' clusters have no edges
  between them — want me to suggest some?" (Needs: graph structure)

These are the queries that turn a knowledge store into a **lab
collaborator** rather than a search box.
