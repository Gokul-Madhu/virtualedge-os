"""Expose VirtualEdge temperature and vibration to EmbeddedX over USB adb reverse."""
import binascii
import json
import math
import socketserver
import struct
from urllib.request import urlopen

HEADER = struct.Struct("<2sBBHH")
CRC = struct.Struct("<H")
TELEMETRY = "http://127.0.0.1:18080/api/v1/telemetry"


def reply(command):
    if command not in (b"PING", b"INFO", b"READ"):
        return 2, b"ERROR:UNSUPPORTED_COMMAND"
    try:
        with urlopen(TELEMETRY, timeout=3) as response:
            sensors = json.loads(response.read(8192))["sensors"]
        if command == b"PING":
            return 2, b"PONG"
        if command == b"INFO":
            source = sensors.get("source", "unknown")
            return 2, f"VirtualEdge OS QEMU; sensor source={source}".encode()
        temperature = float(sensors["temperature_c"])
        vibration = float(sensors["vibration_g"])
        if not (math.isfinite(temperature) and -100 <= temperature <= 300
                and math.isfinite(vibration) and 0 <= vibration <= 1000):
            raise ValueError("sensor out of range")
        return 3, f"TEMP={temperature:.2f};VIB={vibration:.4f}".encode()
    except (OSError, ValueError, KeyError, TypeError):
        return 2, b"ERROR:VIRTUALEDGE_UNAVAILABLE"


class Handler(socketserver.StreamRequestHandler):
    timeout = None

    def handle(self):
        try:
            while True:
                header = self.rfile.read(HEADER.size)
                if len(header) != HEADER.size:
                    return
                magic, version, kind, sequence, size = HEADER.unpack(header)
                if (magic, version, kind) != (b"EX", 1, 1) or size > 4096:
                    return
                body = self.rfile.read(size + CRC.size)
                if len(body) != size + CRC.size:
                    return
                if CRC.unpack(body[size:])[0] != binascii.crc_hqx(header + body[:size], 0xffff):
                    return
                kind, payload = reply(body[:size])
                packet = HEADER.pack(b"EX", 1, kind, sequence, len(payload)) + payload
                self.wfile.write(packet + CRC.pack(binascii.crc_hqx(packet, 0xffff)))
        except OSError:
            return


if __name__ == "__main__":
    with socketserver.ThreadingTCPServer(("127.0.0.1", 8765), Handler) as server:
        print("EmbeddedX bridge listening on 127.0.0.1:8765", flush=True)
        server.serve_forever()
