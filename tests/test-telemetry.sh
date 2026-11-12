#!/usr/bin/env bash
set -euo pipefail

PROJECT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"

cleanup() {
    if [ -n "${SERVER_PID:-}" ]; then
        kill "$SERVER_PID" 2>/dev/null || true
        wait "$SERVER_PID" 2>/dev/null || true
    fi
    rm -rf "$TMP"
}
trap cleanup EXIT

PORT="$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1]); s.close()')"

gcc -std=c11 -O2 -Wall -Wextra -Werror -DVE_PORT="$PORT" \
    "$PROJECT/services/telemetry/virtualedge-api.c" \
    -o "$TMP/virtualedge-api"

"$TMP/virtualedge-api" >"$TMP/server.log" 2>&1 &
SERVER_PID=$!

for attempt in 1 2 3 4 5; do
    if curl --noproxy '*' -fsS --max-time 2 \
       http://127.0.0.1:${PORT}/health \
       >"$TMP/health.json"; then
        break
    fi
    sleep 1
done

curl --noproxy '*' -fsS --max-time 3 \
    http://127.0.0.1:${PORT}/api/v1/telemetry \
    >"$TMP/telemetry.json"

python3 - "$TMP" <<'PY'
import json
import pathlib
import sys

folder = pathlib.Path(sys.argv[1])
health = json.loads((folder / "health.json").read_text())
telemetry = json.loads((folder / "telemetry.json").read_text())

assert health["status"] == "ok"
assert health["service"] == "virtualedge-api"

assert telemetry["system"] == "VirtualEdge OS"
assert telemetry["uptime_seconds"] >= 0
assert telemetry["memory_total_kb"] > 0
assert telemetry["memory_available_kb"] >= 0

sensors = telemetry["sensors"]
assert sensors["source"] == "simulation"
assert isinstance(sensors["temperature_c"], (int, float))
assert isinstance(sensors["vibration_g"], (int, float))
assert isinstance(sensors["voltage_v"], (int, float))

print("PASS: Health endpoint")
print("PASS: Telemetry JSON")
print("PASS: Real system measurements")
print("PASS: Simulated sensor fields")
PY

echo "VirtualEdge Phase 3 API regression tests passed."
