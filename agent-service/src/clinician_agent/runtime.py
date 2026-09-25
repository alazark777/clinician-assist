"""In-process run scheduling and task tracking."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class RunScheduler:
    """Track active generation tasks."""

    max_active: int
    _tasks: dict[str, asyncio.Task[None]] = field(default_factory=dict)
    _cancel_events: dict[str, asyncio.Event] = field(default_factory=dict)

    async def active_count(self, db_count: int) -> int:
        """Return authoritative active run count."""
        return db_count

    def can_start(self, db_count: int) -> bool:
        """Return whether another run may start."""
        return db_count < self.max_active

    def register(self, run_id: str, task: asyncio.Task[None], cancel_event: asyncio.Event) -> None:
        """Track a run task."""
        self._tasks[run_id] = task
        self._cancel_events[run_id] = cancel_event

    def cleanup(self, run_id: str) -> None:
        """Remove finished task tracking."""
        self._tasks.pop(run_id, None)
        self._cancel_events.pop(run_id, None)

    def cancel(self, run_id: str) -> None:
        """Signal cancellation for a run."""
        event = self._cancel_events.get(run_id)
        if event:
            event.set()
