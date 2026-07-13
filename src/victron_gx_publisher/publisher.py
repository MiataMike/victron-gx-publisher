"""Upload generated solar JSON to Neocities without blocking MQTT collection."""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import re
import time
import uuid
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

LOGGER = logging.getLogger(__name__)
DEFAULT_API_URL = "https://neocities.org/api/upload"
REMOTE_PATH_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*[.]json$")
Transport = Callable[[Request, float], tuple[int, bytes]]


class PublishError(RuntimeError):
    """A Neocities request failed or returned an invalid response."""


@dataclass(frozen=True)
class PublisherSettings:
    output_path: Path = Path("output/solar.json")
    api_key_file: Path = Path("/run/secrets/neocities_api_key")
    remote_path: str = "solar.json"
    api_url: str = DEFAULT_API_URL
    settle_seconds: float = 10.0
    min_upload_interval: float = 300.0
    poll_seconds: float = 2.0
    request_timeout: float = 15.0

    @classmethod
    def from_environment(cls) -> "PublisherSettings":
        settings = cls(
            output_path=Path(os.getenv("OUTPUT_PATH", "output/solar.json")),
            api_key_file=Path(
                os.getenv(
                    "NEOCITIES_API_KEY_FILE",
                    "/run/secrets/neocities_api_key",
                )
            ),
            remote_path=os.getenv("NEOCITIES_REMOTE_PATH", "solar.json"),
            api_url=os.getenv("NEOCITIES_API_URL", DEFAULT_API_URL),
            settle_seconds=float(os.getenv("NEOCITIES_SETTLE_SECONDS", "10")),
            min_upload_interval=float(
                os.getenv("NEOCITIES_MIN_UPLOAD_INTERVAL", "300")
            ),
            poll_seconds=float(os.getenv("NEOCITIES_POLL_SECONDS", "2")),
            request_timeout=float(os.getenv("NEOCITIES_REQUEST_TIMEOUT", "15")),
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        if self.min_upload_interval < 60:
            raise ValueError("NEOCITIES_MIN_UPLOAD_INTERVAL must be at least 60 seconds")
        if self.settle_seconds < 0 or self.poll_seconds <= 0:
            raise ValueError("publisher timing values must be positive")
        _validate_remote_path(self.remote_path)


def _validate_remote_path(remote_path: str) -> None:
    path = PurePosixPath(remote_path)
    if (
        not remote_path
        or remote_path.startswith("/")
        or "\r" in remote_path
        or "\n" in remote_path
        or "\\" in remote_path
        or "//" in remote_path
        or any(part in {"", ".", ".."} for part in path.parts)
        or not REMOTE_PATH_PATTERN.fullmatch(remote_path)
    ):
        raise ValueError("NEOCITIES_REMOTE_PATH must be a relative .json path")


def read_api_key(path: Path) -> str:
    api_key = path.read_text(encoding="utf-8").strip()
    if not api_key:
        raise ValueError(f"Neocities API key file is empty: {path}")
    return api_key


def validate_solar_json(document: bytes) -> None:
    try:
        value = json.loads(document)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("solar output is not valid JSON") from error

    if not isinstance(value, dict):
        raise ValueError("solar output must be a JSON object")
    required = {"lifetime_yield_kwh", "charger_count", "updated_at"}
    if not required.issubset(value):
        raise ValueError("solar output is missing required fields")
    if (
        isinstance(value["lifetime_yield_kwh"], bool)
        or not isinstance(value["lifetime_yield_kwh"], (int, float))
        or not math.isfinite(value["lifetime_yield_kwh"])
        or isinstance(value["charger_count"], bool)
        or not isinstance(value["charger_count"], int)
        or value["charger_count"] < 1
        or not isinstance(value["updated_at"], str)
    ):
        raise ValueError("solar output contains invalid field values")


class NeocitiesClient:
    def __init__(
        self,
        api_key: str,
        *,
        api_url: str = DEFAULT_API_URL,
        timeout: float = 15.0,
        transport: Transport | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("Neocities API key cannot be empty")
        self._api_key = api_key
        self.api_url = api_url
        self.timeout = timeout
        self._transport = transport or self._default_transport

    @staticmethod
    def _default_transport(request: Request, timeout: float) -> tuple[int, bytes]:
        try:
            with urlopen(request, timeout=timeout) as response:
                return response.status, response.read()
        except HTTPError as error:
            return error.code, error.read()
        except URLError as error:
            raise PublishError(f"Neocities connection failed: {error.reason}") from error

    def upload(self, remote_path: str, document: bytes) -> None:
        _validate_remote_path(remote_path)
        boundary = f"----victron-gx-{uuid.uuid4().hex}"
        filename = PurePosixPath(remote_path).name
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{remote_path}"; '
            f'filename="{filename}"\r\n'
            "Content-Type: application/json\r\n\r\n"
        ).encode() + document + f"\r\n--{boundary}--\r\n".encode()
        request = Request(
            self.api_url,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "User-Agent": "victron-gx-publisher/0.1.0",
            },
        )

        status, response_body = self._transport(request, self.timeout)
        try:
            response = json.loads(response_body)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise PublishError(
                f"Neocities returned HTTP {status} with invalid JSON"
            ) from error

        if (
            status < 200
            or status >= 300
            or not isinstance(response, dict)
            or response.get("result") != "success"
        ):
            message = response.get("message", "upload failed") if isinstance(
                response, dict
            ) else "upload failed"
            raise PublishError(f"Neocities returned HTTP {status}: {message}")


class SolarFilePublisher:
    def __init__(
        self,
        settings: PublisherSettings,
        client: NeocitiesClient,
    ) -> None:
        self.settings = settings
        self.client = client
        self._observed_signature: tuple[int, int] | None = None
        self._stable_since = 0.0
        self._pending = False
        self._last_digest: str | None = None
        self._last_upload_at = float("-inf")

    def process_once(self, now: float) -> bool:
        try:
            before = self.settings.output_path.stat()
        except FileNotFoundError:
            return False

        signature = (before.st_mtime_ns, before.st_size)
        if signature != self._observed_signature:
            self._observed_signature = signature
            self._stable_since = now
            self._pending = True
            return False

        if not self._pending:
            return False
        if now - self._stable_since < self.settings.settle_seconds:
            return False
        if now - self._last_upload_at < self.settings.min_upload_interval:
            return False

        document = self.settings.output_path.read_bytes()
        after = self.settings.output_path.stat()
        after_signature = (after.st_mtime_ns, after.st_size)
        if after_signature != signature:
            self._observed_signature = after_signature
            self._stable_since = now
            return False

        validate_solar_json(document)
        digest = hashlib.sha256(document).hexdigest()
        if digest == self._last_digest:
            self._pending = False
            return False

        self.client.upload(self.settings.remote_path, document)
        self._last_digest = digest
        self._last_upload_at = now
        self._pending = False
        return True

    def run(self) -> None:
        backoff = self.settings.poll_seconds
        while True:
            try:
                uploaded = self.process_once(time.monotonic())
                if uploaded:
                    LOGGER.info(
                        "uploaded %s to Neocities as %s",
                        self.settings.output_path,
                        self.settings.remote_path,
                    )
                backoff = self.settings.poll_seconds
                time.sleep(self.settings.poll_seconds)
            except (OSError, PublishError, ValueError) as error:
                LOGGER.error("Neocities publish failed: %s", error)
                time.sleep(backoff)
                backoff = min(backoff * 2, 300.0)


def main() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    settings = PublisherSettings.from_environment()
    api_key = read_api_key(settings.api_key_file)
    client = NeocitiesClient(
        api_key,
        api_url=settings.api_url,
        timeout=settings.request_timeout,
    )
    SolarFilePublisher(settings, client).run()


if __name__ == "__main__":
    main()
