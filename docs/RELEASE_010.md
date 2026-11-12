# VirtualEdge OS v0.10 — QEMU A/B boot-slot evaluation

Added `tools/virtualedge_ab.py` to stage signed releases into an inactive
QEMU rootfs slot with atomic host-side state tracking and bounded trial boots.
Added `scripts/run-qemu-ab.sh` to boot the selected slot alongside the
existing dedicated persistent-data disk. Added host tests for update staging,
signature checks, fallback, explicit confirmation, board mismatch, version
floor and abort. Preserved prior telemetry, dashboard, monitoring and
configuration services.

## Verification gates

- Python A/B state machine tests: executed in host environment.
- Existing host regression suite: execute with `./scripts/test-host.sh`.
- ARM64 Buildroot compilation: requires your WSL Buildroot toolchain.
- QEMU boot of candidate A and B: requires your WSL QEMU environment.
- Reboot persistence and recovery: manual guest verification required.
- Hardware OTA / secure boot / field rollback: **not implemented**.
