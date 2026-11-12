#!/usr/bin/env bash
# QEMU-only A/B boot selection; never writes physical storage.
set -euo pipefail
PROJECT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGES="$PROJECT/out/buildroot/images"
STATE="${VE_AB_STATE_DIR:-$PROJECT/out/ab}"
QEMU="$PROJECT/out/buildroot/host/bin/qemu-system-aarch64"
if [[ ! -x "$QEMU" ]]; then QEMU="$(command -v qemu-system-aarch64)"; fi
[[ -s "$IMAGES/Image" ]] || { echo 'Missing ARM64 kernel' >&2; exit 1; }
[[ -f "$PROJECT/out/persistent/virtualedge-data.ext4" ]] || {
  echo 'Missing persistent volume. First run scripts/run-qemu-persistent.sh and power off cleanly.' >&2; exit 1;
}
selected="$(python3 "$PROJECT/tools/virtualedge_ab.py" --state-dir "$STATE" boot)"
read -r SLOT VERSION ROOTFS <<<"$selected"
[[ "$SLOT" == A || "$SLOT" == B ]] || exit 1
[[ -f "$ROOTFS" && "$ROOTFS" == "$STATE/rootfs-$SLOT.ext4" ]] || exit 1
NET='user,id=eth0'
if [[ "${VE_FORWARD_DASHBOARD:-0}" == 1 ]]; then
  NET+=',hostfwd=tcp:127.0.0.1:18080-:8080'
fi
echo "Booting VirtualEdge slot $SLOT version $VERSION; run virtualedge-selftest in guest before host confirmation"
# Boot a temporary root copy: the confirmed A/B slot is hash-protected and
# must not be dirtied by ext4 journal writes during an interactive boot.
BOOT_DIR="$(mktemp -d -t virtualedge-ab-root.XXXXXXXX)"
trap 'rm -rf -- "$BOOT_DIR"' EXIT
cp -- "$ROOTFS" "$BOOT_DIR/boot-rootfs.ext4"
"$QEMU" -M virt -cpu cortex-a53 -smp 1 -m 256 -nographic \
  -kernel "$IMAGES/Image" -append "rootwait root=/dev/vda console=ttyAMA0 ve.slot=$SLOT ve.version=$VERSION" \
  -netdev "$NET" -device virtio-net-device,netdev=eth0 \
  -drive "file=$PROJECT/out/persistent/virtualedge-data.ext4,if=none,format=raw,id=data" \
  -device virtio-blk-device,drive=data \
  -drive "file=$BOOT_DIR/boot-rootfs.ext4,if=none,format=raw,id=rootfs" -device virtio-blk-device,drive=rootfs
