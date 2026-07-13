from decimal import Decimal

import pytest

from victron_gx_publisher.aggregate import YieldAggregator


def test_sums_latest_yield_across_dynamically_seen_chargers() -> None:
    aggregate = YieldAggregator()

    assert aggregate.update("charger/one", Decimal("12.5"))
    assert aggregate.update("charger/two", Decimal("7.25"))

    assert aggregate.total == Decimal("19.75")
    assert aggregate.charger_count == 2


def test_replaces_a_chargers_previous_value_without_double_counting() -> None:
    aggregate = YieldAggregator()
    aggregate.update("charger/one", Decimal("12.5"))

    assert aggregate.update("charger/one", Decimal("13.0"))
    assert aggregate.total == Decimal("13.0")
    assert not aggregate.update("charger/one", Decimal("13.0"))


def test_none_removes_an_unavailable_charger() -> None:
    aggregate = YieldAggregator()
    aggregate.update("charger/one", Decimal("12.5"))

    assert aggregate.update("charger/one", None)
    assert aggregate.total == Decimal(0)
    assert aggregate.charger_count == 0


def test_rejects_negative_lifetime_yield() -> None:
    with pytest.raises(ValueError, match="cannot be negative"):
        YieldAggregator().update("charger/one", Decimal("-1"))
