"""W&B-backed :class:`ExperimentTracker` adapter.

Falls back to ``mode='offline'`` when no API key is supplied so that CI +
local smoke tests do not depend on network egress.
"""

from __future__ import annotations

import os
from pathlib import Path
from types import TracebackType
from typing import Any

from common.logging import get_logger

logger = get_logger(__name__)


class WandbExperimentTracker:
    """Thin wrapper around ``wandb.init`` / ``wandb.log`` / ``wandb.finish``.

    The ``wandb`` import is deferred until ``__enter__`` so the Protocol stays
    usable in environments without the wandb package (e.g. tests stubbing the
    port).
    """

    def __init__(
        self,
        *,
        project: str,
        api_key: str = "",
        run_id: str | None = None,
        workdir: Path | None = None,
    ) -> None:
        self._project = project
        self._api_key = api_key
        self._run_id = run_id
        self._workdir = workdir
        self._run: object | None = None

    def __enter__(self) -> WandbExperimentTracker:
        import wandb

        if self._api_key:
            os.environ["WANDB_API_KEY"] = self._api_key
            mode: str = "online"
        else:
            mode = "offline"
            logger.warning("W&B API key absent — falling back to offline mode")
        kwargs: dict[str, Any] = {"project": self._project, "mode": mode}
        if self._run_id:
            kwargs["name"] = self._run_id
        if self._workdir:
            self._workdir.mkdir(parents=True, exist_ok=True)
            kwargs["dir"] = str(self._workdir)
        self._run = wandb.init(**kwargs)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        import wandb

        wandb.finish(exit_code=1 if exc is not None else 0)
        self._run = None

    def log_metrics(self, metrics: dict[str, float]) -> None:
        import wandb

        wandb.log(metrics)
