#!/usr/bin/env bash
# v0.18: Native guest TLS with dedicated, unencrypted development-credentials disk.
set -euo pipefail
PROJECT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGES="$PROJECT/out/buildroot/images"
PERSIST="$PROJECT/out/persistent"
TLS_IMAGE="${VE_TLS_IMAGE:-$PERSIST/virtualedge-tls-dev.ext4}"
DATA_IMAGE="${VE_DATA_IMAGE:-$PERSIST/virtualedge-data.ext4}"
for path in "$IMAGES/Image" "$TLS_IMAGE" "$DATA_IMAGE"; do
    [[ -f "$path" && ! -L "$path" ]] || { echo "Missing/unsafe disk or kernel: $path" >&2; exit 1; }
done
[[ -f "$IMAGES/rootfs.ext4" ]] || { echo 'Missing Buildroot rootfs.ext4' >&2; exit 1; }
QEMU="$PROJECT/out/buildroot/host/bin/qemu-system-aarch64"
[[ -x "$QEMU" ]] || QEMU="$(command -v qemu-system-aarch64 || true)"
[[ -n "$QEMU" ]] || { echo 'QEMU missing' >&2; exit 1; }
echo 'mTLS: HTTPS localhost:18444 -> guest:8443; credential disk is unencrypted DEV ONLY'
BOOT_DIR="$(mktemp -d -t virtualedge-tls-root.XXXXXXXX)"
trap 'rm -rf -- "$BOOT_DIR"' EXIT
cp -- "$IMAGES/rootfs.ext4" "$BOOT_DIR/rootfs.ext4"
"$QEMU" -M virt -cpu cortex-a53 -smp 1 -m 256 -nographic \
    -kernel "$IMAGES/Image" -append 'rootwait root=/dev/vda console=ttyAMA0 ve_tls_dev=1' \
    -netdev 'user,id=eth0,hostfwd=tcp:127.0.0.1:18444-:8443' \
    -device virtio-net-device,netdev=eth0 \
    -drive "file=$TLS_IMAGE,if=none,format=raw,readonly=on,id=tls" -device virtio-blk-device,drive=tls \
    -drive "file=$DATA_IMAGE,if=none,format=raw,id=data" -device virtio-blk-device,drive=data \
    -drive "file=$BOOT_DIR/rootfs.ext4,if=none,format=raw,id=rootfs" -device virtio-blk-device,drive=rootfs
