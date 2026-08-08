from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Protocol


class RunExecutorPort(Protocol):
    """Execute a run outside the API process and report durable progress."""

    def submit(self, run_id: str, payload: Mapping[str, object]) -> str:
        ...

    def cancel(self, run_id: str) -> None:
        ...

    def execute(self, run_id: str, progress: Callable[[Mapping[str, object]], None]) -> None:
        ...
