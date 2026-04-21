"""
Synthesize what a cluster of sources says. Unlike the note-only version,
this handles heterogeneous source kinds (a paper + a USDA pull + a user
note), making the synthesis prompt explicit about source type so the
LLM can cite appropriately.
"""
from app.services.graph_store import GraphStore
from app.services.llm_router import complete

SYSTEM = """You synthesize clusters of research sources in an AI lab.
Sources may be papers, API snapshots (USDA, NOAA), user notes, experiment
logs, or web pages. Be concise (under 150 words). Structure:
  - Central theme (one sentence)
  - 2-3 sub-themes with one source each as evidence
  - Any notable gap or tension

Never invent findings. If sources disagree, say so. Prefer the user's
own words when excerpting."""


async def synthesize_cluster(store: GraphStore, source_id: str, hops: int = 2) -> str:
    graph_neighbors = await store.neighborhood(source_id, depth=hops, limit=8)
    semantic_neighbors = await store.semantic_neighbors(source_id, k=6)

    seen = {source_id}
    neighbors = []
    for n in graph_neighbors + semantic_neighbors:
        if n["id"] in seen:
            continue
        seen.add(n["id"])
        neighbors.append(n)

    anchor = await store.get(source_id)
    excerpts = []
    if anchor:
        excerpts.append(f"### [anchor: {anchor['kind']}] {anchor['title']}\n{anchor.get('body_excerpt','')[:800]}")

    for n in neighbors[:10]:
        full = await store.get(n["id"])
        if not full:
            continue
        excerpts.append(f"### [{full['kind']}] {full['title']}\n{full.get('body_excerpt','')[:600]}")

    if len(excerpts) < 2:
        return "Not enough connected sources yet to synthesize a cluster."

    prompt = "Synthesize this cluster of sources:\n\n" + "\n\n---\n\n".join(excerpts)
    return await complete(prompt, system=SYSTEM, temperature=0.4)
