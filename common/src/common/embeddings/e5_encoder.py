"""multilingual-e5-base encoder with ``query:`` / ``passage:`` prompt discipline.

ME5 models require the prompt prefix on every input:

* queries  → ``"query: ..."``
* passages → ``"passage: ..."``

Mixing them silently drops retrieval quality by several NDCG points. Keep the
helpers :func:`encode_query` / :func:`encode_passage` as the only entry points.

Heavy dependencies (``sentence_transformers``) are imported lazily inside
:meth:`E5Encoder.load`, so:

* unit tests can construct :class:`E5Encoder` with a stubbed ``model`` attribute
  without pulling torch into the test environment;
* composition roots (API lifespan / embedding-job entrypoint) that rely on GCS
  hydration trigger the torch import only when really loading the model.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

E5_MODEL_NAME: str = "intfloat/multilingual-e5-base"
E5_VECTOR_DIM: int = 768

QUERY_PREFIX: str = "query: "
PASSAGE_PREFIX: str = "passage: "


@dataclass
class E5Encoder:
    """Thin wrapper around a sentence-transformers model with ME5 prefixes.

    The ``model`` attribute is typed as ``Any`` because sentence-transformers
    is not a direct dependency of ``common``; tests can substitute an object
    that exposes ``.encode(texts, normalize_embeddings=True) -> np.ndarray``.
    """

    model: Any
    model_name: str = E5_MODEL_NAME
    vector_dim: int = E5_VECTOR_DIM

    @classmethod
    def load(cls, *, model_dir: Path | None = None) -> E5Encoder:
        """Instantiate a real sentence-transformers encoder from ``model_dir``.

        If ``model_dir`` is None, sentence-transformers downloads the model
        from HuggingFace on first use. In production the API / embedding-job
        lifespan hydrates the model from GCS into a temp dir first and passes
        that path, so there is no outbound network call from Cloud Run.
        """
        from sentence_transformers import SentenceTransformer

        path = str(model_dir) if model_dir is not None else E5_MODEL_NAME
        model = SentenceTransformer(path)
        return cls(model=model)

    def _encode(self, texts: list[str]) -> np.ndarray:
        vectors = self.model.encode(texts, normalize_embeddings=True)
        return np.asarray(vectors, dtype=float)

    def encode_queries(self, queries: list[str]) -> np.ndarray:
        return self._encode([QUERY_PREFIX + q for q in queries])

    def encode_passages(self, passages: list[str]) -> np.ndarray:
        return self._encode([PASSAGE_PREFIX + p for p in passages])


def encode_query(encoder: E5Encoder, query: str) -> np.ndarray:
    """Convenience: encode a single query, returns a 1D ndarray of length vector_dim."""
    return np.asarray(encoder.encode_queries([query])[0])


def encode_passage(encoder: E5Encoder, passage: str) -> np.ndarray:
    """Convenience: encode a single passage, returns a 1D ndarray."""
    return np.asarray(encoder.encode_passages([passage])[0])
