#!/usr/bin/env bash
# v0.18: intentionally refuse legacy private-key staging into firmware rootfs.
set -euo pipefail
echo 'SECURITY ERROR: Embedding a TLS private key in the firmware rootfs is disabled in v0.18.' >&2
echo 'Use python3 tools/virtualedge_tls_image.py --credentials DIR --output out/persistent/virtualedge-tls-dev.ext4 instead.' >&2
exit 1
