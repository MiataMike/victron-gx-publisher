import subprocess
from decimal import Decimal

import pytest

from victron_gx_publisher.venus_dbus import (
    discover_chargers,
    parse_dbus_value,
    read_solar_yields,
)


def test_parses_venus_dbus_value() -> None:
    assert parse_dbus_value("value = 115.52999877929688\n") == Decimal(
        "115.52999877929688"
    )


@pytest.mark.parametrize(
    "output",
    ["", "error", "value = NaN", "value = -1"],
)
def test_rejects_invalid_dbus_values(output: str) -> None:
    with pytest.raises(ValueError):
        parse_dbus_value(output)


def fake_runner(command, **kwargs):
    if command == ["/usr/bin/dbus", "-y"]:
        stdout = (
            "com.victronenergy.settings\n"
            "com.victronenergy.solarcharger.ttyUSB1\n"
            "com.victronenergy.solarcharger.ttyUSB0\n"
        )
    elif any("ttyUSB0" in part for part in command):
        stdout = "value = 115.52999877929688\n"
    elif any("ttyUSB1" in part for part in command):
        stdout = "value = 42.25\n"
    else:
        raise AssertionError(command)
    return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")


def test_discovers_solar_chargers() -> None:
    assert discover_chargers(runner=fake_runner) == [
        "com.victronenergy.solarcharger.ttyUSB0",
        "com.victronenergy.solarcharger.ttyUSB1",
    ]


def test_reads_every_charger_yield() -> None:
    assert read_solar_yields(runner=fake_runner) == {
        "com.victronenergy.solarcharger.ttyUSB0": Decimal(
            "115.52999877929688"
        ),
        "com.victronenergy.solarcharger.ttyUSB1": Decimal("42.25"),
    }
