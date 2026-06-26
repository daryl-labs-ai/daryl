"""Local semantic index (P8) — embeddings + cosine search, dependency-light.

Decision (ADR §11): **local-first**, the heavy ML dependency is isolated. The
core (``SemanticIndex``) is pure Python — no numpy, no torch — and cosine search
runs over normalized vectors. The only model-backed piece, ``LocalEmbedder``,
**lazily** imports ``sentence-transformers`` (optional extra ``[semantic]``) so
importing this module never requires the ML stack. Tests inject a fake embedder.

The index persists to JSON (embeddings are expensive to recompute, unlike the P5
adjacency), so P9 can load without re-embedding.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from ..exceptions import PRLError


class SemanticError(PRLError):
    """Raised on a missing embedder, a dimension mismatch, or a missing backend."""


@runtime_checkable
class Embedder(Protocol):
    """Maps texts to fixed-dimension vectors."""

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class LocalEmbedder:
    """``sentence-transformers`` embedder (optional extra ``[semantic]``).

    The import is deferred to construction so this module imports cleanly without
    the ML stack installed. Raises :class:`SemanticError` with an actionable
    message if the extra is missing.
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:  # pragma: no cover (env-dependent)
            raise SemanticError(
                "LocalEmbedder needs the 'semantic' extra: pip install daryl-dsm[semantic]"
            ) from exc
        self._model = SentenceTransformer(model_name)

    def embed(self, texts: list[str]) -> list[list[float]]:  # pragma: no cover (needs model)
        vectors = self._model.encode(list(texts))
        return [[float(x) for x in v] for v in vectors]


def _normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vec))
    if norm == 0.0:
        return [0.0 for _ in vec]
    return [x / norm for x in vec]


def _dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


class SemanticIndex:
    """In-memory vector index with pure-Python cosine search + JSON persistence.

    Vectors are stored normalized, so cosine similarity is a dot product. An
    ``Embedder`` is required to ``build``/``add``/``search`` (to embed inputs);
    a loaded index can answer ``search`` only if given an embedder for the query.
    """

    def __init__(self, embedder: Embedder | None = None):
        self._embedder = embedder
        self._ids: list[str] = []
        self._vecs: list[list[float]] = []
        self._dim: int | None = None

    def __len__(self) -> int:
        return len(self._ids)

    def _require_embedder(self) -> Embedder:
        if self._embedder is None:
            raise SemanticError("an Embedder is required for this operation")
        return self._embedder

    def _set_dim(self, dim: int) -> None:
        if self._dim is None:
            self._dim = dim
        elif dim != self._dim:
            raise SemanticError(f"vector dim mismatch: {dim} != {self._dim}")

    def add(self, node_id: str, text: str) -> None:
        vec = _normalize([float(x) for x in self._require_embedder().embed([text])[0]])
        self._set_dim(len(vec))
        self._ids.append(node_id)
        self._vecs.append(vec)

    def build(self, items: list[tuple[str, str]]) -> None:
        """Embed and index ``(node_id, text)`` pairs in one batch."""
        if not items:
            return
        raw = self._require_embedder().embed([text for _, text in items])
        for (node_id, _), vec in zip(items, raw):
            nv = _normalize([float(x) for x in vec])
            self._set_dim(len(nv))
            self._ids.append(node_id)
            self._vecs.append(nv)

    def search(self, query: str, k: int = 10) -> list[tuple[str, float]]:
        """Return up to *k* ``(node_id, score)`` pairs, highest cosine first."""
        if not self._vecs:
            return []
        q = _normalize([float(x) for x in self._require_embedder().embed([query])[0]])
        scored = [(nid, _dot(q, v)) for nid, v in zip(self._ids, self._vecs)]
        scored.sort(key=lambda t: t[1], reverse=True)
        return scored[:k]

    # -- persistence (JSON) --------------------------------------------------

    def save(self, path: Any) -> None:
        Path(path).write_text(
            json.dumps({"dim": self._dim, "ids": self._ids, "vectors": self._vecs}),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: Any, embedder: Embedder | None = None) -> "SemanticIndex":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        idx = cls(embedder=embedder)
        idx._dim = data.get("dim")
        idx._ids = list(data.get("ids", []))
        idx._vecs = [[float(x) for x in v] for v in data.get("vectors", [])]
        return idx
