"""
Pluggable embedder. EMBEDDING_BACKEND env var selects:
  local  - sentence-transformers MiniLM, padded to 1536
  openai - text-embedding-3-small
"""
import os
from typing import Awaitable, Callable


def get_embedder() -> Callable[[str], Awaitable[list[float]]]:
    backend = os.getenv("EMBEDDING_BACKEND", "local").lower()
    if backend == "openai":
        return _openai_embedder()
    return _local_embedder()


def _openai_embedder():
    from openai import AsyncOpenAI
    client = AsyncOpenAI()

    async def embed(text: str) -> list[float]:
        r = await client.embeddings.create(
            model="text-embedding-3-small", input=text[:8000],
        )
        return r.data[0].embedding
    return embed


def _local_embedder():
    import asyncio
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer("all-MiniLM-L6-v2")

    async def embed(text: str) -> list[float]:
        loop = asyncio.get_event_loop()
        vec = await loop.run_in_executor(
            None,
            lambda: model.encode(text[:4000], normalize_embeddings=True).tolist(),
        )
        if len(vec) < 1536:
            vec = vec + [0.0] * (1536 - len(vec))
        return vec
    return embed
