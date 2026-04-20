"""Pure logic for model URI resolution and loading.

Kept free of GCP SDK imports so unit tests can exercise ``resolve_model_uri``
with stub :class:`ModelUriResolver` implementations. LightGBM is imported
because the ``Booster`` type is part of the public surface that the lifespan
hands to request handlers.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import lightgbm as lgb
from common.logging import get_logger

from ..ports.model_store import ModelArtifactSource, ModelUriResolver

logger = get_logger(__name__)


@dataclass(frozen=True)
class LoadedModel:
    booster: lgb.Booster
    model_path: str  # original URI (gs:// or local)


def resolve_model_uri(*, override: str, resolver: ModelUriResolver) -> str | None:
    """Return an explicit override if supplied, otherwise ask the resolver.

    Returns ``None`` when no model is available. Callers decide whether that
    is acceptable (Phase 4: yes — /search falls back to lexical_rank).
    """
    if override:
        return override
    return resolver.latest()


def load_model(
    model_uri: str,
    local_dir: Path,
    source: ModelArtifactSource,
) -> LoadedModel:
    local_path = source.materialize(model_uri, local_dir)
    booster = lgb.Booster(model_file=str(local_path))
    logger.info("Loaded model from %s", model_uri)
    return LoadedModel(booster=booster, model_path=model_uri)
