#!/usr/bin/env bash
# Starts persistent VirtualEdge QEMU and opens the Windows browser when ready.
# Development loopback HTTP only; do not expose to untrusted networks.
set -euo pipefail
PROJECT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
URL="http://127.0.0.1:18080/dashboard"
HEALTH="http://127.0.0.1:18080/health"
command -v curl >/dev/null || { echo "ERROR: curl is required" >&2; exit 1; }
if curl --noproxy '*' --silent --max-time 1 "$HEALTH" >/dev/null 2>&1; then
  echo 'ERROR: localhost:18080 already has a responding service.' >&2; exit 1
fi
watch_and_open() {
  for ((i=0; i<180; i++)); do
    if curl --noproxy '*' --fail --silent --max-time 1 "$HEALTH" 2>/dev/null | grep -q '"service":"virtualedge-api"'; then
      echo "VirtualEdge dashboard ready: $URL"
      if command -v powershell.exe >/dev/null 2>&1; then
        powershell.exe -NoProfile -NonInteractive -Command 'Start-Process "http://127.0.0.1:18080/dashboard"' >/dev/null 2>&1 || true
      elif command -v explorer.exe >/dev/null 2>&1; then
        explorer.exe "$URL" >/dev/null 2>&1 || true
      else
        echo "Open manually: $URL"
      fi
      return 0
    fi
    sleep 1
  done
  echo "Dashboard not ready on $HEALTH; guest console is still available" >&2
}
watch_and_open &
watcher=$!
cleanup() { kill "$watcher" 2>/dev/null || true; wait "$watcher" 2>/dev/null || true; }
trap cleanup EXIT INT TERM
VE_FORWARD_DASHBOARD=1 "$PROJECT/scripts/run-qemu-persistent.sh" "$@"
