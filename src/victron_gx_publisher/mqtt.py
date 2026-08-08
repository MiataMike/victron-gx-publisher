"""Small dependency-free MQTT 3.1.1 client for Venus OS."""

from __future__ import annotations

import socket
import ssl
import time
from typing import Callable, Optional


MessageCallback = Callable[[str, bytes], None]


def _encode_remaining_length(value: int) -> bytes:
    if value < 0 or value > 268435455:
        raise ValueError("invalid MQTT remaining length")
    encoded = bytearray()
    while True:
        digit = value % 128
        value //= 128
        if value:
            digit |= 0x80
        encoded.append(digit)
        if not value:
            return bytes(encoded)


def _encode_string(value: str) -> bytes:
    encoded = value.encode("utf-8")
    if len(encoded) > 65535:
        raise ValueError("MQTT string is too long")
    return len(encoded).to_bytes(2, "big") + encoded


def _packet(packet_type: int, flags: int, payload: bytes) -> bytes:
    return bytes([(packet_type << 4) | flags]) + _encode_remaining_length(len(payload)) + payload


def topic_matches(topic_filter: str, topic: str) -> bool:
    filter_parts = topic_filter.split("/")
    topic_parts = topic.split("/")
    for index, part in enumerate(filter_parts):
        if part == "#":
            return index == len(filter_parts) - 1
        if index >= len(topic_parts):
            return False
        if part != "+" and part != topic_parts[index]:
            return False
    return len(filter_parts) == len(topic_parts)


class MqttClient:
    """Enough MQTT for a resilient QoS-0 subscriber and publisher."""

    def __init__(
        self,
        host: str,
        port: int,
        *,
        client_id: str = "victron-gx-publisher",
        username: Optional[str] = None,
        password: Optional[str] = None,
        use_tls: bool = False,
        tls_insecure: bool = False,
        ca_cert: Optional[str] = None,
        keepalive: int = 60,
        on_message: Optional[MessageCallback] = None,
    ) -> None:
        self.host = host
        self.port = port
        self.client_id = client_id
        self.username = username
        self.password = password
        self.use_tls = use_tls
        self.tls_insecure = tls_insecure
        self.ca_cert = ca_cert
        self.keepalive = keepalive
        self.on_message = on_message
        self._socket: Optional[socket.socket] = None
        self._packet_id = 0

    def _next_packet_id(self) -> int:
        self._packet_id = self._packet_id % 65535 + 1
        return self._packet_id

    @staticmethod
    def _recv_exact(connection: socket.socket, length: int) -> bytes:
        chunks = bytearray()
        while len(chunks) < length:
            chunk = connection.recv(length - len(chunks))
            if not chunk:
                raise ConnectionError("MQTT broker closed the connection")
            chunks.extend(chunk)
        return bytes(chunks)

    def _recv_packet(self) -> tuple[int, int, bytes]:
        if self._socket is None:
            raise ConnectionError("MQTT client is not connected")
        first = self._recv_exact(self._socket, 1)[0]
        multiplier = 1
        remaining = 0
        for _ in range(4):
            digit = self._recv_exact(self._socket, 1)[0]
            remaining += (digit & 127) * multiplier
            if not digit & 128:
                break
            multiplier *= 128
        else:
            raise ValueError("malformed MQTT remaining length")
        return first >> 4, first & 15, self._recv_exact(self._socket, remaining)

    def connect(self) -> None:
        connection = socket.create_connection((self.host, self.port), timeout=15)
        if self.use_tls:
            context = ssl.create_default_context(cafile=self.ca_cert)
            if self.tls_insecure:
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE
            connection = context.wrap_socket(connection, server_hostname=self.host)
        connection.settimeout(1)
        self._socket = connection

        flags = 0x02
        fields = [_encode_string(self.client_id)]
        if self.username is not None:
            flags |= 0x80
            fields.append(_encode_string(self.username))
        if self.password is not None:
            if self.username is None:
                raise ValueError("MQTT_PASSWORD requires MQTT_USERNAME")
            flags |= 0x40
            fields.append(_encode_string(self.password))

        variable = _encode_string("MQTT") + bytes([4, flags]) + self.keepalive.to_bytes(2, "big")
        connection.sendall(_packet(1, 0, variable + b"".join(fields)))
        packet_type, _, payload = self._recv_packet()
        if packet_type != 2 or len(payload) != 2:
            raise ConnectionError("invalid MQTT CONNACK")
        if payload[1] != 0:
            raise ConnectionError("MQTT connection refused (code %d)" % payload[1])

    def subscribe(self, topic_filter: str) -> None:
        if self._socket is None:
            raise ConnectionError("MQTT client is not connected")
        packet_id = self._next_packet_id()
        payload = packet_id.to_bytes(2, "big") + _encode_string(topic_filter) + bytes([0])
        self._socket.sendall(_packet(8, 2, payload))

    def publish(self, topic: str, payload: bytes = b"") -> None:
        if self._socket is None:
            raise ConnectionError("MQTT client is not connected")
        self._socket.sendall(_packet(3, 0, _encode_string(topic) + payload))

    def loop_forever(self) -> None:
        if self._socket is None:
            raise ConnectionError("MQTT client is not connected")
        last_traffic = time.monotonic()
        while True:
            try:
                packet_type, flags, payload = self._recv_packet()
            except socket.timeout:
                if time.monotonic() - last_traffic >= self.keepalive / 2:
                    self._socket.sendall(_packet(12, 0, b""))
                    last_traffic = time.monotonic()
                continue

            last_traffic = time.monotonic()
            if packet_type == 3:
                if len(payload) < 2:
                    raise ValueError("malformed MQTT PUBLISH")
                topic_length = int.from_bytes(payload[:2], "big")
                offset = 2 + topic_length
                topic = payload[2:offset].decode("utf-8")
                qos = (flags >> 1) & 3
                packet_id = None
                if qos:
                    packet_id = int.from_bytes(payload[offset:offset + 2], "big")
                    offset += 2
                if self.on_message is not None:
                    self.on_message(topic, payload[offset:])
                if qos == 1 and packet_id is not None:
                    self._socket.sendall(_packet(4, 0, packet_id.to_bytes(2, "big")))

    def close(self) -> None:
        if self._socket is not None:
            try:
                self._socket.sendall(_packet(14, 0, b""))
            except OSError:
                pass
            self._socket.close()
            self._socket = None
