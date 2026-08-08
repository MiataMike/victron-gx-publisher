"""Native Venus OS D-Bus collector entry point."""

from __future__ import annotations

import logging
import os
import subprocess
import time
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Dict

from victron_gx_publisher.output import write_solar_json
from victron_gx_publisher.venus_dbus import read_solar_yields

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class Settings:
    output_path: Path = Path("/data/victron-gx-publisher/output/solar.json")
    poll_seconds: float = 30.0
    dbus_command: str = "/usr/bin/dbus"

    @classmethod
    def from_environment(cls) -> "Settings":
        settings = cls(
            output_path=Path(
                os.getenv(
                    "OUTPUT_PATH",
                    "/data/victron-gx-publisher/output/solar.json",
                )
            ),
            poll_seconds=float(os.getenv("POLL_SECONDS", "30")),
            dbus_command=os.getenv("DBUS_COMMAND", "/usr/bin/dbus"),
        )
        if settings.poll_seconds <= 0:
            raise ValueError("POLL_SECONDS must be positive")
        return settings


class SolarYieldDaemon:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._last_yields: Dict[str, Decimal] = {}

    def collect_once(self) -> bool:
        yields = read_solar_yields(self.settings.dbus_command)
        if not yields:
            LOGGER.warning("no solar chargers found on the Venus system D-Bus")
            return False
        if yields == self._last_yields:
            return False

        total = sum(yields.values(), start=Decimal(0))
        write_solar_json(
            self.settings.output_path,
            lifetime_yield_kwh=total,
            charger_count=len(yields),
        )
        self._last_yields = yields
        LOGGER.info(
            "wrote %s (%s kWh across %d chargers)",
            self.settings.output_path,
            total,
            len(yields),
        )
        return True

    def run(self) -> None:
        LOGGER.info(
            "collecting Venus D-Bus solar yields every %.1f seconds",
            self.settings.poll_seconds,
        )
        while True:
            try:
                self.collect_once()
            except (OSError, subprocess.SubprocessError, ValueError) as error:
                LOGGER.error("D-Bus collection failed: %s", error)
            time.sleep(self.settings.poll_seconds)


def main() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    SolarYieldDaemon(Settings.from_environment()).run()


if __name__ == "__main__":
    main()
