"""Shared LanceDB-backed vector index for the lab.

Now that LanceDB ships in both install tiers (see pyproject.toml), this
module is the single place every surface should reach for when it needs
semantic recall — KB search, experiment lookup, agent memory, and so on.

Design notes
------------
* **Embedding** is a deterministic SHA1-based hash projection (128-dim,
  L2-normalized). No torch, no sentence-transformers, no model weights.
  The KB and experiment corpora are small enough that hash embeddings
  give "good enough" semantic recall without a runtime ML stack.
* **Failsoft.** If LanceDB isn't importable (defensive — it's now a
  hard dep, but stale envs happen) every call returns a sensible empty
  value. Callers should always check `available()` before relying on
  vector results, then fall back to keyword/regex paths.
* **Tables are owned per-feature.** Each consumer (PKB, experiments,
  workflows) gets its own table inside its own subdirectory, so a
  schema bump in one doesn't poison the others.
"""

from __future__ import annotations

import hashlib
import math
import re
from pathlib import Path
from typing import Any, Iterable


_TOKEN_RE = re.compile(r"[a-zA-Z0-9_\-/]{2,}")
_DEFAULT_DIM = 128


def hash_embedding(text: str, dim: int = _DEFAULT_DIM) -> list[float]:
    """Deterministic sparse embedding — same algorithm as wiki_vectors.

    Tokens are hashed into a fixed vector space with sign bits derived
    from the same SHA1 digest, then L2-normalized. Identical input
    always produces an identical vector — useful for tests and for
    rebuilding indices reproducibly.
    """
    vec = [0.0] * dim
    toks = _TOKEN_RE.findall((text or "").lower())
    if not toks:
        return vec

    for tok in toks:
        h = hashlib.sha1(tok.encode("utf-8")).digest()
        idx = int.from_bytes(h[:4], "little") % dim
        sign = 1.0 if (h[4] & 1) == 0 else -1.0
        vec[idx] += sign

    norm = math.sqrt(sum(v * v for v in vec))
    if norm <= 0:
        return vec
    return [v / norm for v in vec]


def available() -> bool:
    """Return True iff LanceDB is importable on this Python env."""
    try:
        import lancedb  # type: ignore[import-not-found]  # noqa: F401
        return True
    except Exception:
        return False


class VectorIndex:
    """Thin wrapper around a single LanceDB table.

    Use one instance per feature (PKB pages, experiments, etc). The
    table is created on first write; reads on a missing/empty table
    return [] rather than raising.
    """

    def __init__(self, *, name: str, db_path: Path, dim: int = _DEFAULT_DIM) -> None:
        self.name = name
        self.db_path = Path(db_path)
        self.dim = dim
        self._db = None  # lazy

    # -- internal --------------------------------------------------------
    def _connect(self):
        if self._db is None:
            try:
                import lancedb  # type: ignore[import-not-found]
            except Exception:
                return None
            self.db_path.mkdir(parents=True, exist_ok=True)
            try:
                self._db = lancedb.connect(str(self.db_path))
            except Exception:
                return None
        return self._db

    @staticmethod
    def _existing_tables(db) -> list[str]:
        """Return existing table names. LanceDB has shipped at least three
        return shapes for this call across versions:

          * legacy `table_names()` — plain ``list[str]``
          * mid `list_tables()`     — plain ``list[str]``
          * recent `list_tables()`  — a paginated object exposing ``.tables``

        Try each call and unwrap whichever shape we get back.
        """
        for fn in ("list_tables", "table_names"):
            getter = getattr(db, fn, None)
            if getter is None:
                continue
            try:
                result = getter()
            except Exception:
                continue
            # Paginated object (e.g. TableNamesPage with `.tables`).
            inner = getattr(result, "tables", None)
            if inner is not None:
                return list(inner)
            # Plain iterable of strings.
            try:
                names = list(result)
            except TypeError:
                continue
            if all(isinstance(n, str) for n in names):
                return names
        return []

    def _table(self):
        db = self._connect()
        if db is None:
            return None
        try:
            if self.name in self._existing_tables(db):
                return db.open_table(self.name)
        except Exception:
            return None
        return None

    # -- public ----------------------------------------------------------
    def replace(self, rows: Iterable[dict[str, Any]]) -> int:
        """Replace the table contents wholesale. Returns rows written.

        Best for small corpora that re-index cheaply (PKB pages, the
        experiment list). Each row must include a `vector` field of the
        configured dimension — callers should produce vectors via
        :func:`hash_embedding` so reads use the same projection.
        """
        db = self._connect()
        if db is None:
            return 0
        materialized = [dict(r) for r in rows]
        if not materialized:
            # Drop the table entirely so future searches return [] cleanly.
            try:
                if self.name in self._existing_tables(db):
                    db.drop_table(self.name)
            except Exception:
                pass
            return 0
        try:
            db.create_table(self.name, data=materialized, mode="overwrite")
        except TypeError:
            # Older LanceDB without mode="overwrite".
            try:
                if self.name in self._existing_tables(db):
                    db.drop_table(self.name)
            except Exception:
                pass
            try:
                db.create_table(self.name, data=materialized)
            except Exception:
                return 0
        except Exception:
            return 0
        return len(materialized)

    def search(
        self,
        query: str,
        *,
        k: int = 5,
        min_score: float = 0.0,
        where: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return up to ``k`` nearest rows for ``query``.

        Each row gets a ``score`` field in [0, 1] derived from the LanceDB
        distance (1 - distance, clamped). Rows below ``min_score`` are
        dropped. Returns [] if the table is missing or LanceDB raised.
        """
        table = self._table()
        if table is None:
            return []
        vec = hash_embedding(query, dim=self.dim)
        try:
            # L2-normalized hash vectors: squared-L2 distance lies in
            # [0, 4], with 0 meaning identical and 2 meaning orthogonal.
            # Convert to a [0, 1] similarity = 1 - dist/2 so consumers
            # have a single intuitive score regardless of metric choice.
            q = table.search(vec)
            if where:
                q = q.where(where)
            hits = q.limit(max(1, k)).to_list()
        except Exception:
            return []

        out: list[dict[str, Any]] = []
        for h in hits:
            dist = float(h.get("_distance", 2.0))
            score = max(0.0, min(1.0, 1.0 - dist / 2.0))
            if score < min_score:
                continue
            row = {k: v for k, v in h.items() if k not in ("vector", "_distance")}
            row["score"] = round(score, 4)
            out.append(row)
        return out

    def count(self) -> int:
        table = self._table()
        if table is None:
            return 0
        try:
            return int(table.count_rows())
        except Exception:
            return 0
