import json
from datetime import UTC, datetime
from decimal import Decimal

from victron_gx_publisher.output import write_solar_json


def test_writes_solar_json(tmp_path) -> None:
    output_path = tmp_path / "nested" / "solar.json"

    write_solar_json(
        output_path,
        lifetime_yield_kwh=Decimal("19.75"),
        charger_count=2,
        now=datetime(2026, 7, 13, 12, 30, tzinfo=UTC),
    )

    assert json.loads(output_path.read_text()) == {
        "lifetime_yield_kwh": 19.75,
        "charger_count": 2,
        "updated_at": "2026-07-13T12:30:00Z",
    }
