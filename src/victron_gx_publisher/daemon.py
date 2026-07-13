"""MQTT daemon entry point."""

from __future__ import annotations

import json
import logging
import os
import re
import ssl
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import paho.mqtt.client as mqtt

from victron_gx_publisher.aggregate import YieldAggregator
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
    raise ValueError(f"{name} must be true or false")


def _read_password() -> str | None:
    password_file = os.getenv("MQTT_PASSWORD_FILE")
    password = os.getenv("MQTT_PASSWORD")
    if password_file and password:
        raise ValueError("set only one of MQTT_PASSWORD or MQTT_PASSWORD_FILE")
    if password_file:
        return Path(password_file).read_text(encoding="utf-8").strip()
    return password


@dataclass(frozen=True)
class Settings:
    mqtt_host: str = "venus.local"
    mqtt_port: int = 8883
    mqtt_username: str | None = None
    mqtt_password: str | None = field(default=None, repr=False)
    mqtt_tls: bool = True
    mqtt_tls_insecure: bool = True
    mqtt_ca_cert: Path | None = None
    output_path: Path = Path("output/solar.json")
    vrm_portal_id: str | None = None

    @classmethod
    def from_environment(cls) -> "Settings":
        ca_cert = os.getenv("MQTT_CA_CERT")
        return cls(
            mqtt_host=os.getenv("MQTT_HOST", "venus.local"),
            mqtt_port=int(os.getenv("MQTT_PORT", "8883")),
            mqtt_username=os.getenv("MQTT_USERNAME"),
            mqtt_password=_read_password(),
            mqtt_tls=_environment_bool("MQTT_TLS", True),
            mqtt_tls_insecure=_environment_bool("MQTT_TLS_INSECURE", True),
            mqtt_ca_cert=Path(ca_cert) if ca_cert else None,
            output_path=Path(os.getenv("OUTPUT_PATH", "output/solar.json")),
            vrm_portal_id=os.getenv("VRM_PORTAL_ID"),
        )


def parse_yield_message(topic: str, payload: bytes) -> Decimal | None:
    """Return the Victron value, or None when a charger value is unavailable."""
    if not YIELD_TOPIC_PATTERN.fullmatch(topic):
        raise ValueError(f"unexpected topic: {topic}")

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

    def on_connect(
        self,
        client: mqtt.Client,
        userdata: Any,
        flags: mqtt.ConnectFlags,
        reason_code: mqtt.ReasonCode,
        properties: mqtt.Properties | None,
    ) -> None:
        if reason_code.is_failure:
            LOGGER.error("MQTT connection failed: %s", reason_code)
            return

        client.subscribe(YIELD_TOPIC_FILTER)
        LOGGER.info("subscribed to %s", YIELD_TOPIC_FILTER)
        if self.settings.vrm_portal_id:
            client.publish(f"R/{self.settings.vrm_portal_id}/keepalive")
            LOGGER.info("requested a full GX value refresh")

    def on_message(
        self, client: mqtt.Client, userdata: Any, message: mqtt.MQTTMessage
    ) -> None:
        try:
            value = parse_yield_message(message.topic, message.payload)
            changed = self.aggregator.update(message.topic, value)
        except ValueError as error:
            LOGGER.warning("ignoring %s: %s", message.topic, error)
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

    def _configure_tls(self, client: mqtt.Client) -> None:
        if not self.settings.mqtt_tls:
            return
        if self.settings.mqtt_ca_cert:
            client.tls_set(ca_certs=str(self.settings.mqtt_ca_cert))
            return
        if self.settings.mqtt_tls_insecure:
            client.tls_set(cert_reqs=ssl.CERT_NONE)
            client.tls_insecure_set(True)
            return
        client.tls_set()

    def run(self) -> None:
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        if self.settings.mqtt_username is not None:
            client.username_pw_set(
                self.settings.mqtt_username, self.settings.mqtt_password
            )
        self._configure_tls(client)
        client.on_connect = self.on_connect
        client.on_message = self.on_message
        client.reconnect_delay_set(min_delay=1, max_delay=30)

        LOGGER.info(
            "connecting to MQTT broker at %s:%d",
            self.settings.mqtt_host,
            self.settings.mqtt_port,
        )
        client.connect(self.settings.mqtt_host, self.settings.mqtt_port, keepalive=60)
        client.loop_forever(retry_first_connection=True)


def main() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    SolarYieldDaemon(Settings.from_environment()).run()


if __name__ == "__main__":
    main()
