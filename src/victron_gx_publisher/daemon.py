"""MQTT collector entry point, designed to run natively on Venus OS."""

from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Optional

from victron_gx_publisher.aggregate import YieldAggregator
from victron_gx_publisher.mqtt import MqttClient
from victron_gx_publisher.output import write_solar_json

LOGGER = logging.getLogger(__name__)
YIELD_TOPIC_FILTER = "N/+/solarcharger/+/Yield/System"
YIELD_TOPIC_PATTERN = re.compile(r"^N/[^/]+/solarcharger/[^/]+/Yield/System$")


def _environment_bool(name: str, default: bool) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    if raw_value.lower() in {"1", "true", "yes", "on"}:
        return True
    if raw_value.lower() in {"0", "false", "no", "off"}:
        return False
    raise ValueError("%s must be true or false" % name)


def _read_password() -> Optional[str]:
    password_file = os.getenv("MQTT_PASSWORD_FILE")
    password = os.getenv("MQTT_PASSWORD")
    if password_file and password:
        raise ValueError("set only one of MQTT_PASSWORD or MQTT_PASSWORD_FILE")
    if password_file:
        return Path(password_file).read_text(encoding="utf-8").strip()
    return password


@dataclass(frozen=True)
class Settings:
    mqtt_host: str = "127.0.0.1"
    mqtt_port: int = 1883
    mqtt_username: Optional[str] = None
    mqtt_password: Optional[str] = field(default=None, repr=False)
    mqtt_tls: bool = False
    mqtt_tls_insecure: bool = False
    mqtt_ca_cert: Optional[Path] = None
    output_path: Path = Path("/data/victron-gx-publisher/output/solar.json")
    vrm_portal_id: Optional[str] = None
    reconnect_seconds: float = 5.0

    @classmethod
    def from_environment(cls) -> "Settings":
        ca_cert = os.getenv("MQTT_CA_CERT")
        settings = cls(
            mqtt_host=os.getenv("MQTT_HOST", "127.0.0.1"),
            mqtt_port=int(os.getenv("MQTT_PORT", "1883")),
            mqtt_username=os.getenv("MQTT_USERNAME"),
            mqtt_password=_read_password(),
            mqtt_tls=_environment_bool("MQTT_TLS", False),
            mqtt_tls_insecure=_environment_bool("MQTT_TLS_INSECURE", False),
            mqtt_ca_cert=Path(ca_cert) if ca_cert else None,
            output_path=Path(
                os.getenv(
                    "OUTPUT_PATH",
                    "/data/victron-gx-publisher/output/solar.json",
                )
            ),
            vrm_portal_id=os.getenv("VRM_PORTAL_ID"),
            reconnect_seconds=float(os.getenv("MQTT_RECONNECT_SECONDS", "5")),
        )
        if not 1 <= settings.mqtt_port <= 65535:
            raise ValueError("MQTT_PORT must be between 1 and 65535")
        if settings.reconnect_seconds <= 0:
            raise ValueError("MQTT_RECONNECT_SECONDS must be positive")
        return settings


def parse_yield_message(topic: str, payload: bytes) -> Optional[Decimal]:
    """Return the Victron value, or None when a charger value is unavailable."""
    if not YIELD_TOPIC_PATTERN.fullmatch(topic):
        raise ValueError("unexpected topic: %s" % topic)

    try:
        message = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("payload is not valid JSON") from error

    if not isinstance(message, dict) or "value" not in message:
        raise ValueError("payload must be an object containing 'value'")

    value: Any = message["value"]
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("yield value must be numeric")

    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise ValueError("yield value must be numeric") from error

    if not parsed.is_finite():
        raise ValueError("yield value must be finite")
    return parsed


class SolarYieldDaemon:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.aggregator = YieldAggregator()

    def on_message(self, topic: str, payload: bytes) -> None:
        try:
            value = parse_yield_message(topic, payload)
            changed = self.aggregator.update(topic, value)
        except ValueError as error:
            LOGGER.warning("ignoring %s: %s", topic, error)
            return

        if not changed:
            return

        write_solar_json(
            self.settings.output_path,
            lifetime_yield_kwh=self.aggregator.total,
            charger_count=self.aggregator.charger_count,
        )
        LOGGER.info(
            "wrote %s (%s kWh across %d chargers)",
            self.settings.output_path,
            self.aggregator.total,
            self.aggregator.charger_count,
        )

    def _new_client(self) -> MqttClient:
        return MqttClient(
            self.settings.mqtt_host,
            self.settings.mqtt_port,
            username=self.settings.mqtt_username,
            password=self.settings.mqtt_password,
            use_tls=self.settings.mqtt_tls,
            tls_insecure=self.settings.mqtt_tls_insecure,
            ca_cert=str(self.settings.mqtt_ca_cert)
            if self.settings.mqtt_ca_cert
            else None,
            on_message=self.on_message,
        )

    def run(self) -> None:
        while True:
            client = self._new_client()
            try:
                LOGGER.info(
                    "connecting to MQTT broker at %s:%d",
                    self.settings.mqtt_host,
                    self.settings.mqtt_port,
                )
                client.connect()
                client.subscribe(YIELD_TOPIC_FILTER)
                LOGGER.info("subscribed to %s", YIELD_TOPIC_FILTER)
                if self.settings.vrm_portal_id:
                    client.publish("R/%s/keepalive" % self.settings.vrm_portal_id)
                    LOGGER.info("requested a full GX value refresh")
                client.loop_forever()
            except (ConnectionError, OSError, ValueError) as error:
                LOGGER.error(
                    "MQTT connection lost: %s; retrying in %.1f seconds",
                    error,
                    self.settings.reconnect_seconds,
                )
                time.sleep(self.settings.reconnect_seconds)
            finally:
                client.close()


def main() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    SolarYieldDaemon(Settings.from_environment()).run()


if __name__ == "__main__":
    main()
