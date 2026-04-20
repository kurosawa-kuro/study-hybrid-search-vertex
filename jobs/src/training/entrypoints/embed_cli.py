"""Cloud Run Jobs entrypoint — ``embed`` (property text → 768d vectors → BQ).

Orchestrates:

* read cleaned property text via :class:`BigQueryPropertyTextRepository`,
* load the ME5 encoder from GCS (or HuggingFace on ``--dry-run`` / local dev),
* delegate to :func:`run_embedding_batch` for the change-detection + upsert
  loop.

``--dry-run`` uses an in-process fake encoder and in-memory store so this job
can be smoke-tested without ADC or torch.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import cast

import numpy as np
from common.embeddings import E5Encoder
from common.logging import configure_logging
from common.ports.embedding_store import (
    EmbeddingRow,
    EmbeddingStore,
    PropertyText,
    PropertyTextRepository,
)

from common import get_logger

from ..adapters import create_embedding_store, create_property_text_repository
from ..config import TrainSettings
from ..services.embedding_runner import run_embedding_batch

logger = get_logger(__name__)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Property embedding batch job")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Use in-memory fakes for the BQ adapters + stub encoder.",
    )
    parser.add_argument(
        "--model-dir",
        default=None,
        help="Local directory containing the sentence-transformers checkpoint. "
        "If omitted the model is downloaded from HuggingFace (dev only).",
    )
    return parser.parse_args(argv)


@dataclass
class _FakeEncoder:
    """Deterministic stand-in for E5Encoder used by --dry-run."""

    model_name: str = "fake-e5"
    vector_dim: int = 8

    def encode_passages(self, passages: list[str]) -> np.ndarray:
        rng = np.random.default_rng(sum(len(p) for p in passages))
        return rng.normal(size=(len(passages), self.vector_dim))

    def encode_queries(self, queries: list[str]) -> np.ndarray:
        return self.encode_passages(queries)


class _InMemoryPropertyRepo:
    def __init__(self, rows: list[PropertyText]) -> None:
        self._rows = rows

    def fetch_all(self) -> list[PropertyText]:
        return list(self._rows)


class _InMemoryEmbeddingStore:
    def __init__(self) -> None:
        self._rows: dict[str, EmbeddingRow] = {}

    def existing_hashes(self) -> dict[str, str]:
        return {pid: row.text_hash for pid, row in self._rows.items()}

    def upsert(self, rows: list[EmbeddingRow]) -> int:
        for r in rows:
            self._rows[r.property_id] = r
        return len(rows)


def run(
    *,
    dry_run: bool = False,
    model_dir: str | None = None,
) -> int:
    configure_logging()
    settings = TrainSettings()
    started = datetime.now(timezone.utc)

    repo: object
    store: object
    encoder: object
    if dry_run:
        logger.warning("dry-run: using in-memory fakes + fake encoder")
        fake_rows = [
            PropertyText(property_id=f"P-{i:04d}", title=f"物件{i}", description=f"説明 {i}")
            for i in range(10)
        ]
        repo = _InMemoryPropertyRepo(fake_rows)
        store = _InMemoryEmbeddingStore()
        encoder = _FakeEncoder()
    else:
        repo = create_property_text_repository(settings)
        store = create_embedding_store(settings)
        encoder = E5Encoder.load(model_dir=Path(model_dir) if model_dir else None)

    # The Protocols guarantee .fetch_all / .existing_hashes / .upsert exist;
    # run_embedding_batch is typed to accept them directly.
    written = run_embedding_batch(
        repository=cast("PropertyTextRepository", repo),
        store=cast("EmbeddingStore", store),
        encoder=cast("E5Encoder", encoder),
        logger=logger,
        now=started,
    )
    logger.info("Embedding batch complete: %d rows upserted", written)
    return written


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        run(dry_run=args.dry_run, model_dir=args.model_dir)
    except Exception:
        logger.exception("Embedding job failed")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
