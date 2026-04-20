"""Port for model artifact upload.

Concrete adapter: :class:`training.adapters.artifact_store.GcsArtifactUploader`.
Restored in Phase 6 (Task 1) for the ranker training pipeline.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class ArtifactUploader(Protocol):
    def upload(self, local_dir: Path, *, run_id: str, date_str: str) -> str:
        """Upload ``local_dir`` and return the resulting ``gs://.../model.txt`` URI."""
        ...
