"""Read solar-charger lifetime yield directly from the Venus OS system D-Bus."""

from __future__ import annotations

import subprocess
from decimal import Decimal, InvalidOperation
from typing import Callable, Dict, List

SERVICE_PREFIX = "com.victronenergy.solarcharger."
Runner = Callable[..., subprocess.CompletedProcess]


def parse_dbus_value(output: str) -> Decimal:
    """Parse the output of: dbus -y <service> /Yield/System GetValue."""
    prefix = "value ="
    line = output.strip()
    if not line.startswith(prefix):
        raise ValueError("unexpected D-Bus response: %s" % line)
    raw_value = line[len(prefix):].strip()
    try:
        value = Decimal(raw_value)
    except InvalidOperation as error:
        raise ValueError("D-Bus yield is not numeric: %s" % raw_value) from error
    if not value.is_finite() or value < 0:
        raise ValueError("D-Bus yield must be finite and non-negative")
    return value


def _run(command: List[str], runner: Runner) -> str:
    result = runner(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        check=True,
    )
    return result.stdout


def discover_chargers(
    dbus_command: str = "/usr/bin/dbus",
    *,
    runner: Runner = subprocess.run,
) -> List[str]:
    output = _run([dbus_command, "-y"], runner)
    return sorted(
        line.strip()
        for line in output.splitlines()
        if line.strip().startswith(SERVICE_PREFIX)
    )


def read_solar_yields(
    dbus_command: str = "/usr/bin/dbus",
    *,
    runner: Runner = subprocess.run,
) -> Dict[str, Decimal]:
    yields: Dict[str, Decimal] = {}
    for service in discover_chargers(dbus_command, runner=runner):
        output = _run(
            [dbus_command, "-y", service, "/Yield/System", "GetValue"],
            runner,
        )
        yields[service] = parse_dbus_value(output)
    return yields
