from decimal import Decimal

import pytest

from victron_gx_publisher.daemon import Settings, parse_yield_message


TOPIC = "N/portal-id/solarcharger/288/Yield/System"


def test_parses_victron_yield_payload() -> None:
    assert parse_yield_message(TOPIC, b'{"value": 1234.56}') == Decimal("1234.56")


def test_accepts_null_as_an_unavailable_value() -> None:
    assert parse_yield_message(TOPIC, b'{"value": null}') is None


@pytest.mark.parametrize(
    ("topic", "payload"),
    [
        ("N/portal-id/system/0/Yield/System", b'{"value": 1}'),
        (TOPIC, b"not-json"),
        (TOPIC, b'{"other": 1}'),
        (TOPIC, b'{"value": true}'),
        (TOPIC, b'{"value": "NaN"}'),
    ],
)
def test_rejects_unexpected_messages(topic: str, payload: bytes) -> None:
    with pytest.raises(ValueError):
        parse_yield_message(topic, payload)


def test_reads_password_from_secret_file(tmp_path, monkeypatch) -> None:
    secret_file = tmp_path / "mqtt_password"
    secret_file.write_text("device-secret\n")
    monkeypatch.setenv("MQTT_PASSWORD_FILE", str(secret_file))
    monkeypatch.delenv("MQTT_PASSWORD", raising=False)

    settings = Settings.from_environment()

    assert settings.mqtt_password == "device-secret"
    assert "device-secret" not in repr(settings)


def test_rejects_two_password_sources(monkeypatch, tmp_path) -> None:
    secret_file = tmp_path / "mqtt_password"
    secret_file.write_text("file-secret")
    monkeypatch.setenv("MQTT_PASSWORD_FILE", str(secret_file))
    monkeypatch.setenv("MQTT_PASSWORD", "environment-secret")

    with pytest.raises(ValueError, match="only one"):
        Settings.from_environment()
