# VirtualEdge OS 0.7.0-dev — release evidence

## Included

- ARM64-native local configuration command (`virtualedge-config`), strict finite-number/range validation, atomic config writes.
- SIGHUP-initiated live, all-or-nothing configuration reload (last-valid thresholds retained after invalid edits).
- Read-only `/api/v1/config` and `/api/v1/device` endpoints.
- Dashboard displays hostname, config revision and validation state.
- Guest self-test extended to exercise management endpoints.
- New isolated host integration test for CLI validation, reload and negative cases.

## Verified in preparation environment

`./scripts/test-host.sh` passed all included host checks, including legacy telemetry, HTTP and dashboard behavior, supervisor, sysfs sensor fixtures, event buffer, and the new config management test.

## Pending acceptance on user's WSL/QEMU

- Run `./scripts/build-and-test.sh --qemu` with Buildroot 2026.08.1 and toolchain available.
- Confirm `virtualedge-selftest` passes, then interactively validate local config change and SIGHUP reload.
- Confirm Windows dashboard shows the guest hostname and current config state through localhost forwarding.
- Reboot and validate durability of chosen config on the same disk image.

## Not implemented / not qualified

- Physical industrial SBC board port and real sensor drivers beyond the opt-in sysfs adapter.
- Network authentication, HTTPS, certificates, RBAC or remote configuration mutation.
- Signed A/B system OTA, secure boot, rollback, or safe fleet provisioning.
- Power-loss/corruption tests, multi-day load soak, vulnerability assessment and field qualification.

This remains an **engineering prototype**, not a finished or certified industrial OS.
