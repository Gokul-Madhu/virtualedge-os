#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
EXE="$(mktemp -d)/virtualedge-api"
PORT="${VE_PREVIEW_PORT:-18081}"
cleanup(){ kill "${PID:-}" 2>/dev/null || true; rm -f "$EXE"; rmdir "$(dirname "$EXE")" 2>/dev/null || true; }
trap cleanup EXIT
if command -v ss >/dev/null && ss -ltn | grep -qE "[:.]${PORT}[[:space:]]"; then
  echo "Port $PORT is already in use; stop the other server first." >&2
  exit 1
fi
gcc -std=c11 -O2 -Wall -Wextra -Werror \
  "-DVE_PORT=$PORT" \
  -DVE_DASHBOARD_FILE=\""$ROOT/board/virtualedge/rootfs-overlay/usr/share/virtualedge/dashboard.html"\" \
  "$ROOT/services/telemetry/virtualedge-api.c" -o "$EXE"
"$EXE" & PID=$!
echo "VirtualEdge dashboard preview running: http://localhost:${PORT}/dashboard"
echo 'Press Ctrl+C to stop. Values are from WSL + simulated sensors, not the QEMU guest.'
wait "$PID"
