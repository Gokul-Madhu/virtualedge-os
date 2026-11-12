# VirtualEdge OS v0.8 — Verifiable release artifacts

This revision advances reproducible and secure *packaging*, not production deployment.

## New capabilities

- Offline Ed25519-signed release manifests bound to exactly one image by SHA-256.
- Board-specific authorization and caller-provided version floor.
- Strict, bounded archive verification with no arbitrary extraction.
- Tamper, rollback, board mismatch and oversized payload tests in host CI.
- All v0.7 API, monitor, dashboard, device configuration and QEMU scripts retained.

## Verification performed during release generation

Run `./scripts/test-host.sh` and record its result. Host tests don't demonstrate
that a newly built QEMU image runs or that physical devices boot.

## Remaining blockers

- Hardware support: Raspberry Pi/industrial target kernel, bootloader, DT and sensor drivers.
- OTA: no writer, no A/B rootfs, no rollback/power-loss validation.
- Security: no TLS/authenticated remote management, device enrollment, secure boot or key rotation.
- Operations: no dedicated persistent partition or endurance/industrial qualification.

Until these pass, label VirtualEdge OS as a **prototype**.
