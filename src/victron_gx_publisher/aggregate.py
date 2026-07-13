"""Solar charger lifetime-yield aggregation."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal


@dataclass
class YieldAggregator:
    """Track the latest lifetime yield reported by each charger topic."""

    _yield_by_topic: dict[str, Decimal] = field(default_factory=dict)

    def update(self, topic: str, value: Decimal | None) -> bool:
        """Update one charger and return whether the aggregate changed."""
        if value is None:
            return self._yield_by_topic.pop(topic, None) is not None

        if value < 0:
            raise ValueError("lifetime yield cannot be negative")

        if self._yield_by_topic.get(topic) == value:
            return False

        self._yield_by_topic[topic] = value
        return True

    @property
    def charger_count(self) -> int:
        return len(self._yield_by_topic)

    @property
    def total(self) -> Decimal:
        return sum(self._yield_by_topic.values(), start=Decimal(0))

    @property
    def topics(self) -> tuple[str, ...]:
        return tuple(sorted(self._yield_by_topic))
