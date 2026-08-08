from decimal import Decimal
from pathlib import Path

import pytest

from victron_gx_publisher.daemon import Settings, SolarYieldDaemon


def test_settings_use_native_venus_defaults(monkeypatch) -> None:
    monkeypatch.delenv("OUTPUT_PATH", raising=False)
    monkeypatch.delenv("POLL_SECONDS", raising=False)
    settings = Settings.from_environment()
    assert settings.dbus_command == "/usr/bin/dbus"
    assert settings.poll_seconds == 30
    assert settings.output_path == Path(
        "/data/victron-gx-publisher/output/solar.json"
    )


def test_rejects_invalid_poll_interval(monkeypatch) -> None:
    monkeypatch.setenv("POLL_SECONDS", "0")
    with pytest.raises(ValueError, match="positive"):
        Settings.from_environment()


def test_collects_and_sums_all_chargers(tmp_path, monkeypatch) -> None:
    output = tmp_path / "solar.json"
    yields = {
        "com.victronenergy.solarcharger.ttyUSB0": Decimal("115.53"),
        "com.victronenergy.solarcharger.ttyUSB1": Decimal("42.25"),
    }
    monkeypatch.setattr(
        "victron_gx_publisher.daemon.read_solar_yields",
        lambda command: yields,
    )
    daemon = SolarYieldDaemon(Settings(output_path=output))

    assert daemon.collect_once()
    document = output.read_text()
    assert '"lifetime_yield_kwh": 157.78' in document
    assert '"charger_count": 2' in document
    assert not daemon.collect_once()


def test_does_not_replace_output_when_no_chargers_exist(tmp_path, monkeypatch) -> None:
    output = tmp_path / "solar.json"
    monkeypatch.setattr(
        "victron_gx_publisher.daemon.read_solar_yields",
        lambda command: {},
    )
    daemon = SolarYieldDaemon(Settings(output_path=output))

    assert not daemon.collect_once()
    assert not output.exists()
