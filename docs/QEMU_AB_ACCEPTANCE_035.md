# v0.35: QEMU A/B acceptance hardening

This release adds **early kernel-panic recognition** to `scripts/test-qemu.py` and
**strict boot-sequence validation** to `scripts/accept-qemu-ota.py`. No changes to
firmware partitions, bootloader, or signing keys. The `0.33.0` test bundle made
from an unchanged root filesystem is **not** evidence of an application upgrade.

## WSL acceptance

1. Shut down all interactive QEMU guests. Do not run another QEMU while accepting.
2. Keep the existing `out/ab`, persistent ext4 volume, development trust keys and
   signed test bundle intact. Do not re-initialize a valid A/B state.
3. Run:

```bash
cd ~/dev/virtualedge-os
python3 tests/test-ota-boot-evidence.py
python3 tests/test-ota-accept-entry.py
python3 tools/virtualedge_ab.py --state-dir out/ab audit
mkdir -p ~/virtualedge-test-reports
python3 scripts/accept-qemu-ota.py \
    --state-dir out/ab \
    --data-image out/persistent/virtualedge-data.ext4 \
    --bundle out/ota-demo/virtualedge-test-0.33.0.tar \
    --public-key "$HOME/virtualedge-private-keys/dev-ed25519.pub.pem" \
    --scenario both --timeout 240 \
    --report "$HOME/virtualedge-test-reports/ota-v035.json"
```

Each scenario uses a disposable copy of A/B state and the data disk. A valid
both-scenario report must show one candidate confirmation boot, followed by an
independent fallback test with two candidate boots and a baseline boot.

If the kernel cannot mount its root filesystem or start init, the test runner
now reports that failure immediately rather than consuming its entire timeout.
Inspect the printed QEMU serial output; confirm disk order (`/dev/vda` root,
`/dev/vdb` data) before changing images.

A/B acceptance on the developer's WSL QEMU installation **has not been run in
this release-building environment**. Host regression tests alone do not
substitute for real guest boots.

## Hardware / secure boot / power-loss qualification

This release does not implement a physical A/B partition installer, hardware
root of trust, verified boot, or automated power interruption. A production
hardware implementation requires a selected board, storage medium, signed
boot chain and recovery design before any destructive test. Never use these
QEMU regular-file update tools directly against live block devices.
