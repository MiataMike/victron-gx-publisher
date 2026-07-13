"""Atomic JSON output rendering."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from tempfile import NamedTemporaryFile


def write_solar_json(
    path: Path,
    *,
    lifetime_yield_kwh: Decimal,
    charger_count: int,
    now: datetime | None = None,
) -> None:
    """Atomically replace the solar JSON file with the current aggregate."""
    timestamp = (now or datetime.now(UTC)).astimezone(UTC)
    document = {
        "lifetime_yield_kwh": float(lifetime_yield_kwh),
        "charger_count": charger_count,
        "updated_at": timestamp.isoformat().replace("+00:00", "Z"),
    }

    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as temporary_file:
        json.dump(document, temporary_file, indent=2)
        temporary_file.write("\n")
        temporary_path = Path(temporary_file.name)

    os.replace(temporary_path, path)
