"""Execution budget tracking."""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class RunBudget:
    """Track model and read budgets for one run."""

    deadline_seconds: float
    max_model_calls: int = 6
    max_additional_record_ids: int = 10
    started_at: float = field(default_factory=time.monotonic)
    model_calls: int = 0
    additional_record_ids: int = 0
    baseline_ids: set[str] = field(default_factory=set)

    def expired(self) -> bool:
        """Return whether the total deadline elapsed."""
        return (time.monotonic() - self.started_at) >= self.deadline_seconds

    def remaining_seconds(self) -> float:
        """Seconds left before deadline."""
        return max(0.0, self.deadline_seconds - (time.monotonic() - self.started_at))

    def can_model_call(self) -> bool:
        """Return whether another model call is allowed."""
        return not self.expired() and self.model_calls < self.max_model_calls

    def record_model_call(self) -> None:
        """Consume one model call."""
        self.model_calls += 1

    def can_read_additional(self, record_ids: list[str]) -> bool:
        """Check additional read budget excluding baseline IDs."""
        new_ids = [record_id for record_id in record_ids if record_id not in self.baseline_ids]
        return self.additional_record_ids + len(set(new_ids)) <= self.max_additional_record_ids

    def record_additional_reads(self, record_ids: list[str]) -> None:
        """Consume additional read budget."""
        for record_id in record_ids:
            if record_id not in self.baseline_ids:
                self.additional_record_ids += 1
