"""Embedding encoder utilities (pure — delegates the heavy model load to adapters).

:class:`E5Encoder` wraps sentence-transformers with the multilingual-e5 prompt
convention (``query:`` / ``passage:`` prefixes). Actual model loading is lazy
and isolated in :func:`E5Encoder.load` so unit tests can stub it out.
"""

from .e5_encoder import E5_MODEL_NAME, E5_VECTOR_DIM, E5Encoder, encode_passage, encode_query

__all__ = [
    "E5_MODEL_NAME",
    "E5_VECTOR_DIM",
    "E5Encoder",
    "encode_passage",
    "encode_query",
]
