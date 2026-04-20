"""Port for kicking the training Cloud Run Job from the API side.

Concrete adapter: :class:`app.adapters.training_job.CloudRunJobRunner`.
"""

from __future__ import annotations

from typing import Protocol


class TrainingJobRunner(Protocol):
    def start(self) -> str: ...
