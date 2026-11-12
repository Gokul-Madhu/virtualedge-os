# Release status — VirtualEdge OS v0.9.0

## Verified in host environment

- Original native C monitoring/diagnostic/HTTP API regression tests.
- Dashboard endpoint, simulated faults, event ring/history and rotation.
- Linux thermal sysfs adapter using fixtures, including failure and recovery.
- Local threshold editing, strict configuration validation and SIGHUP reload.
- Daemon supervisor restart/stop behavior.
- Ed25519 signed offline release bundle generation/verification: valid bundles,
  board identity, anti-rollback floor, image size bound, image and manifest tamper.
- Script syntax checks and archive integrity.

## Verified previously by user in QEMU

- Linux ARM64 boot, DHCP and HTTP connectivity, monitoring, simulation,
  fault injection, dashboard access in Windows browser.
- This is evidence for prior image builds; **not proof that v0.8 QEMU build works**.

## Not yet verified

- Rebuilding and booting this v0.8 source image using the user's Buildroot toolchain.
- Independent hardware image deployment on Raspberry Pi or industrial boards.
- Actual I2C/SPI/RS485/CAN device drivers, physical sensor calibration.
- Device TLS authentication, secure enrollment, identity management, key rotation.
- Boot-chain security, A/B OTA installation, automatic rollback after power loss.
- Industrial endurance, watchdog/failsafe, threat-model and hardware qualification.

**Classification: engineering prototype, NOT industrial-ready.**

## v0.9 additions (host verification only)

- QEMU second-disk launcher and early data-volume mount service.
- Host test validates launcher reuses the same image and does not format it again.
- Real ext4 mounting and persistence across QEMU reboot require device-side testing.
- A/B updates, guest-side signature verification and recovery remain incomplete.

## v0.10 update-slot groundwork

Host-side QEMU A/B rootfs slot management and signed offline staging are
implemented and tested as a simulation. No on-device bootloader validation,
automatic guest-health confirmation, signed kernel update, real OTA transfer,
or hardware rollback validation is claimed. See `docs/AB_QEMU.md`.

## v0.11 guest A/B acceptance (source implementation)

- Host script to test pending slot with QEMU using disposable disk copies, with guest `/proc/cmdline` slot/version check and API self-test.
- Optional host confirmation only after successful guest test, and negative-path regression tests.
- Host tests are executable without QEMU. **Real QEMU candidate boot and promotion require execution on the user's WSL environment** and have not been verified in this build environment.
- No secure boot, on-device OTA installation, hardware qualification or power-fail-safe bootloader is provided.

## v0.13 opt-in local HTTP Basic
Host-level authenticated/unauthenticated route and credential-file checks added.
Authentication is opt-in and not encrypted; authenticated guest operations are
not covered by the legacy anonymous QEMU self-test. No production network security
or industrial deployment acceptance is claimed.
