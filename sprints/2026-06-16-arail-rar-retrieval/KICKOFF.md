# Sprint Kickoff — ARAIL Real Embeddings + RAR Retrieval (Phase 3)

**Program:** The Epistemology Engine · Phase 3 — see `/Users/netsushi/ProJects/EPISTEMOLOGY_ENGINE_PLAN.md`
**Repo:** `arail` (only) · **Proposed branch:** `qukaizen/arail-rar-retrieval`
**Suggested sprint-id:** `2026-06-16-arail-rar-retrieval` · **Status:** brief / seed for `/sprint`
**⚠️ EXECUTE LAST in the spine.** Depends on Phase 1 (primitives exist) + Phase 2 (compiled ContextPacks to retrieve), **and** on ARAIL's `qukaizen/arail-world-mount` + `qukaizen/arail-stt-capabilities` landing. This touches the most coordination-sensitive files in the program.

---

## 1. Goal / win condition

ARAIL agents retrieve **real semantic matches** — reasoning primitives + cited facts — instead of the placeholder SHA1 hash projection. Win:
1. Replace the hash "embedding" with a real small embedder (**EmbeddingGemma-300M on MLX**, per Decision 3), rebuild the index.
2. Wire **RAR retrieval** so `pkb.search()` / `world_mount` return ranked **reasoning primitives** from the mounted World, not just KB text.
3. Fully **airgapped** — model loaded locally, no network.

## 2. Why now / dependencies

**Current state (grounded):**
- `src/arail/vector_index.py` — `hash_embedding(text, dim=128)` SHA1 projection (`:35`); `search()` (`:178`) embeds the query the same way (`:195`); `replace()` (`:141`).
- A **second copy**: `src/arail/wiki_vectors._hash_embedding` — both must be unified/replaced.
- `src/arail/pkb.py` — `search(query, pkb_root)` (`:590`) is the single semantic-recall entry.
- `pyproject.toml` — `lancedb>=0.13.0` is **core**; an `mlx` extra exists (`mlx`, `mlx-lm`). A comment notes hash embeddings were chosen so "no heavyweight ML deps come along" — this sprint deliberately changes that tradeoff.

**Depends on:** Phase 1A/1B (primitives) + Phase 2A (compiled ContextPacks). **And** on `qukaizen/arail-world-mount` + `qukaizen/arail-stt-capabilities` merging. **Coordinate reindex** with `qukaizen/arail-kb-incremental-persistence`.

## 3. Scope

**IN**
- **Real embedder:** add `mlx-embedding-models` + EmbeddingGemma-300M; a unified `embeddings.py`; replace **both** `vector_index.hash_embedding` and `wiki_vectors._hash_embedding`.
- **Dim migration:** 128 → 768 (Matryoshka-truncatable to 256/128 for efficiency); update the LanceDB table schema; **full reindex** of KB + experiment + wiki corpora.
- **RAR retrieval:** extend `pkb.search()` to also return reasoning primitives from the mounted World (Phase 2 ContextPacks), ranked by real similarity; surface to the researcher/buddy consumers + `world_mount` helpers.
- **Airgapped:** model from a local path; honest degradation if the model is absent.

**OUT**
- No DaC/Nucleus changes. No model training. No retrieval-UI redesign.

## 4. Where it hooks (grounded, line-anchored)

- `src/arail/vector_index.py` — `hash_embedding` (`:35`), `search` (`:178`/`:195`), `replace` (`:141`), `_DEFAULT_DIM`.
- `src/arail/wiki_vectors.py` — `_hash_embedding` (second copy to unify).
- `src/arail/pkb.py` — `search` (`:590`); the `pkb_index` build path.
- `src/arail/world_mount.py` — consumer helpers (return primitives alongside terms).
- `pyproject.toml` — add the embedding dep; revisit the "no heavyweight ML deps" comment + tier gating (this changes the minimalist tier's footprint).

## 5. File ownership (⚠️ MAXIMUM coordination — all your flagged files)

**MODIFY:** `vector_index.py`, `wiki_vectors.py`, `pkb.py`, `pkb_index.py`, `world_mount.py`, `pyproject.toml` — **every one is on your sensitive list.**
**CREATE:** `src/arail/embeddings.py` (unified embedder), tests, a reindex script.
**Execute only after `world-mount` + `stt-capabilities` merge; rebase onto latest `main`; confirm no other ARAIL session holds these files.** Coordinate the reindex with `kb-incremental-persistence`.
**DO NOT TOUCH:** DaC, Nucleus.

## 6. Definition of Done (measurable)

- Retrieval quality **beats the hash baseline** on a labeled physics recall@k set — report the numbers.
- An agent **retrieves and cites a reasoning primitive** from the mounted physics World.
- Embedder runs **airgapped** on the M5 (no network); model-absent path degrades honestly.
- Full **reindex reproducible**; table dim migrated; old hash vectors gone.
- Latency within the tick-loop budget; minimalist-tier footprint impact documented.

## 7. Hand-off / base (after world-mount + stt land)

```bash
cd /Users/netsushi/ProJects/arail
git fetch && git checkout main && git pull        # only after world-mount + stt-capabilities merge
git checkout -b qukaizen/arail-rar-retrieval
# stage this KICKOFF into arail/sprints/2026-06-16-arail-rar-retrieval/, then:
claude   # → /sprint
```

## 8. Open decisions for the personas

- **Embedder:** EmbeddingGemma-300M (Decision 3 default) vs Qwen3-Embedding-0.6B (higher quality, larger).
- **Matryoshka dim:** 256 vs 128 — efficiency vs quality.
- **Reindex:** full vs incremental (coordinate with `kb-incremental-persistence`).
- **Tier gating:** does the embedder ship in the minimalist tier, or behind an extra?
