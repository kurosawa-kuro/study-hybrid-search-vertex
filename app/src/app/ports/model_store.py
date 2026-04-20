"""Ports for model URI resolution + artifact materialization.

Concrete adapters: :mod:`app.adapters.model_store`. Defined as Protocols so
the lifespan wiring + unit tests can swap in stub resolvers / sources that
never touch BigQuery or GCS.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class ModelUriResolver(Protocol):
    def latest(self) -> str | None: ...


class ModelArtifactSource(Protocol):
    def materialize(self, model_uri: str, local_dir: Path) -> Path: ...
