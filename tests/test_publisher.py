import json
import os
from pathlib import Path
from urllib.request import Request

import pytest

from victron_gx_publisher.publisher import (
    NeocitiesClient,
    PublishError,
    PublisherSettings,
    SolarFilePublisher,
    read_api_key,
    validate_solar_json,
)


def solar_document(yield_kwh: float = 85.31) -> bytes:
    return json.dumps(
        {
            "lifetime_yield_kwh": yield_kwh,
            "charger_count": 2,
            "updated_at": "2026-07-13T18:23:44Z",
        }
    ).encode()


def test_reads_api_key_from_secret_file_without_storing_it_in_settings(
    tmp_path: Path,
) -> None:
    key_file = tmp_path / "api_key"
    key_file.write_text("secret-api-key\n")

    settings = PublisherSettings(api_key_file=key_file)

    assert read_api_key(settings.api_key_file) == "secret-api-key"
    assert "secret-api-key" not in repr(settings)


def test_rejects_empty_api_key_file(tmp_path: Path) -> None:
    key_file = tmp_path / "api_key"
    key_file.write_text("")

    with pytest.raises(ValueError, match="empty"):
        read_api_key(key_file)


def test_upload_uses_bearer_auth_and_multipart_remote_name() -> None:
    captured: list[tuple[Request, float]] = []

    def transport(request: Request, timeout: float) -> tuple[int, bytes]:
        captured.append((request, timeout))
        return 200, b'{"result":"success"}'

    client = NeocitiesClient(
        "secret-api-key",
        timeout=12,
        transport=transport,
    )
    document = solar_document()

    client.upload("data/solar.json", document)

    request, timeout = captured[0]
    assert request.full_url == "https://neocities.org/api/upload"
    assert request.get_header("Authorization") == "Bearer secret-api-key"
    assert request.get_method() == "POST"
    assert timeout == 12
    assert b'name="data/solar.json"' in request.data
    assert document in request.data


@pytest.mark.parametrize(
    ("status", "response"),
    [
        (401, b'{"result":"error","message":"unauthorized"}'),
        (429, b'{"result":"error","message":"slow down"}'),
        (500, b"not-json"),
    ],
)
def test_upload_rejects_api_errors(status: int, response: bytes) -> None:
    client = NeocitiesClient(
        "secret-api-key",
        transport=lambda request, timeout: (status, response),
    )

    with pytest.raises(PublishError):
        client.upload("solar.json", solar_document())


@pytest.mark.parametrize(
    "remote_path",
    [
        "",
        "/solar.json",
        "../solar.json",
        "solar.txt",
        "bad\nname.json",
        'bad"name.json',
        "data//solar.json",
    ],
)
def test_rejects_unsafe_remote_paths(remote_path: str) -> None:
    with pytest.raises(ValueError):
        PublisherSettings(remote_path=remote_path).validate()


def test_enforces_neocities_minimum_recurring_interval(monkeypatch) -> None:
    monkeypatch.setenv("NEOCITIES_MIN_UPLOAD_INTERVAL", "59")

    with pytest.raises(ValueError, match="at least 60"):
        PublisherSettings.from_environment()


def test_validates_solar_document() -> None:
    validate_solar_json(solar_document())

    with pytest.raises(ValueError, match="required"):
        validate_solar_json(b'{"charger_count": 2}')

    with pytest.raises(ValueError, match="invalid"):
        validate_solar_json(b'{"lifetime_yield_kwh": NaN, "charger_count": 2, "updated_at": "now"}')


class RecordingClient:
    def __init__(self) -> None:
        self.uploads: list[tuple[str, bytes]] = []

    def upload(self, remote_path: str, document: bytes) -> None:
        self.uploads.append((remote_path, document))


def test_publisher_settles_uploads_and_skips_unchanged_content(
    tmp_path: Path,
) -> None:
    output = tmp_path / "solar.json"
    output.write_bytes(solar_document())
    settings = PublisherSettings(
        output_path=output,
        settle_seconds=10,
        min_upload_interval=60,
    )
    client = RecordingClient()
    publisher = SolarFilePublisher(settings, client)  # type: ignore[arg-type]

    assert not publisher.process_once(0)
    assert not publisher.process_once(9)
    assert publisher.process_once(10)
    assert len(client.uploads) == 1
    assert not publisher.process_once(100)

    output.write_bytes(solar_document())
    os.utime(output, ns=(output.stat().st_atime_ns, output.stat().st_mtime_ns + 1))
    assert not publisher.process_once(101)
    assert not publisher.process_once(111)
    assert len(client.uploads) == 1


def test_publisher_coalesces_changes_and_throttles_uploads(tmp_path: Path) -> None:
    output = tmp_path / "solar.json"
    output.write_bytes(solar_document())
    settings = PublisherSettings(
        output_path=output,
        settle_seconds=5,
        min_upload_interval=60,
    )
    client = RecordingClient()
    publisher = SolarFilePublisher(settings, client)  # type: ignore[arg-type]

    publisher.process_once(0)
    assert publisher.process_once(5)

    output.write_bytes(solar_document(86.0))
    assert not publisher.process_once(10)
    output.write_bytes(solar_document(87.0))
    assert not publisher.process_once(12)
    assert not publisher.process_once(17)
    assert not publisher.process_once(64)
    assert publisher.process_once(65)

    assert len(client.uploads) == 2
    assert b"87.0" in client.uploads[-1][1]
