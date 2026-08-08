import pytest

from victron_gx_publisher.mqtt import (
    _encode_remaining_length,
    _encode_string,
    _packet,
    topic_matches,
)


@pytest.mark.parametrize(
    ("value", "encoded"),
    [
        (0, b"\x00"),
        (127, b"\x7f"),
        (128, b"\x80\x01"),
        (16384, b"\x80\x80\x01"),
        (268435455, b"\xff\xff\xff\x7f"),
    ],
)
def test_encodes_mqtt_remaining_length(value: int, encoded: bytes) -> None:
    assert _encode_remaining_length(value) == encoded


def test_rejects_invalid_remaining_length() -> None:
    with pytest.raises(ValueError):
        _encode_remaining_length(-1)
    with pytest.raises(ValueError):
        _encode_remaining_length(268435456)


def test_encodes_utf8_mqtt_string() -> None:
    assert _encode_string("solar") == b"\x00\x05solar"


def test_builds_mqtt_packet_header() -> None:
    assert _packet(12, 0, b"") == b"\xc0\x00"
    assert _packet(3, 0, b"x" * 128)[:3] == b"\x30\x80\x01"


@pytest.mark.parametrize(
    ("topic_filter", "topic", "matches"),
    [
        ("N/+/solarcharger/+/Yield/System", "N/id/solarcharger/288/Yield/System", True),
        ("N/+/solarcharger/+/Yield/System", "N/id/system/0/Yield/System", False),
        ("N/#", "N/id/solarcharger/288/Yield/System", True),
        ("N/+", "N/id/extra", False),
    ],
)
def test_topic_matching(topic_filter: str, topic: str, matches: bool) -> None:
    assert topic_matches(topic_filter, topic) is matches
