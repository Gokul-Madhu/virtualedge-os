#!/usr/bin/env bash
# QEMU-only optional persistence on a separate ext4 data volume.
# Does not modify Buildroot's generated start-qemu.sh or rootfs image.
set -euo pipefail
PROJECT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGES="$PROJECT/out/buildroot/images"
DATA_DIR="$PROJECT/out/persistent"
DATA_IMAGE="${VE_DATA_IMAGE:-$DATA_DIR/virtualedge-data.ext4}"
KERNEL="$IMAGES/Image"
ROOTFS="$IMAGES/rootfs.ext4"
HOST_QEMU="$PROJECT/out/buildroot/host/bin/qemu-system-aarch64"

if [[ ! -f "$KERNEL" || ! -e "$ROOTFS" ]]; then
    echo 'ERROR: Buildroot image missing; build VirtualEdge first' >&2; exit 1
fi
if [[ -L "$DATA_IMAGE" || ( -e "$DATA_IMAGE" && ! -f "$DATA_IMAGE" ) ]]; then
    echo 'ERROR: data image must be a regular file, not a symlink or device' >&2
    exit 1
fi
if [[ ! "${VE_DATA_SIZE_MB:-64}" =~ ^[0-9]+$ ]] || (( ${VE_DATA_SIZE_MB:-64} < 8 || ${VE_DATA_SIZE_MB:-64} > 2048 )); then
    echo 'ERROR: VE_DATA_SIZE_MB must be between 8 and 2048' >&2
    exit 1
fi
if [[ ! -e "$DATA_IMAGE" ]]; then
    mkdir -p "$(dirname "$DATA_IMAGE")"
    if [[ "$DATA_IMAGE" != *.ext4 ]]; then echo 'ERROR: data image must end with .ext4' >&2; exit 1; fi
    command -v mkfs.ext4 >/dev/null || { echo 'ERROR: install e2fsprogs (mkfs.ext4)' >&2; exit 1; }
    truncate -s "${VE_DATA_SIZE_MB:-64}M" "$DATA_IMAGE"
    mkfs.ext4 -F -q -L VEDATA "$DATA_IMAGE"
    echo "Created new persistent data volume: $DATA_IMAGE"
else
    echo "Reusing existing data volume: $DATA_IMAGE"
fi
if [[ -x "$HOST_QEMU" ]]; then
    QEMU="$HOST_QEMU"
else
    QEMU="$(command -v qemu-system-aarch64 || true)"
    [[ -n "$QEMU" ]] || { echo 'ERROR: qemu-system-aarch64 unavailable' >&2; exit 1; }
fi

NET='user,id=eth0'
# Forwarding is explicitly opt-in and bound only to the host loopback interface.
if [[ "${VE_FORWARD_DASHBOARD:-0}" == 1 ]]; then
    NET+=',hostfwd=tcp:127.0.0.1:18080-:8080'
    echo 'Dashboard forwarded on http://127.0.0.1:18080/dashboard'
    echo 'The guest API must be configured to bind eth0 (VE_LISTEN_ANY=1).'
fi
# Never boot the Buildroot release/signing artifact read-write. Use a disposable
# root copy; keep only the separately attached /data volume persistent.
BOOT_DIR="$(mktemp -d -t virtualedge-persistent-root.XXXXXXXX)"
trap 'rm -rf -- "$BOOT_DIR"' EXIT
cp -- "$ROOTFS" "$BOOT_DIR/rootfs.ext4"
"$QEMU" -M virt -cpu cortex-a53 -smp 1 -m 256 -nographic \
    -kernel "$KERNEL" -append 'rootwait root=/dev/vda console=ttyAMA0' \
    -netdev "$NET" -device virtio-net-device,netdev=eth0 \
    -drive "file=$DATA_IMAGE,if=none,format=raw,id=data" \
    -device virtio-blk-device,drive=data \
    -drive "file=$BOOT_DIR/rootfs.ext4,if=none,format=raw,id=rootfs" \
    -device virtio-blk-device,drive=rootfs
