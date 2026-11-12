# Consolidated v0.32 validation record

## Demonstrated by the user's WSL/QEMU environment before consolidation
- ARM64 QEMU self-test and API/dashboard boot: PASS.
- Persistent ext4 data mounted; configuration retained across reboots: PASS.
- Guest native Ed25519/SHA-256 signed-image verification: PASS.
- Guest staging and inactive regular-file installation: PASS.
- Signed bundle, imported image, staged image and installed image SHA-256 identical: PASS.
- Separate QEMU OTA trial boot initially failed with `No working init found` due to disk ordering; corrected in this release but not yet re-tested on WSL.

## Tests performed on consolidated source in packaging environment
- `python3 tests/test-release-integration.py`: PASS.
- `python3 tests/test-signed-release.py`: PASS.
- `python3 tests/test-persistence.py`: PASS (mock mkfs, no real guest mount).
- `python3 tests/test-guest-update-verify.py`: 9 tests PASS.
- Python compilation and shell syntax checks: PASS.
- Combined long native staging suite timed out during execution; not a full-suite PASS.

## Pending
- Run full host suite, ARM64 cross-build, persistent launcher reboot and actual OTA A/B confirmation and rollback in WSL.
- Physical-board OTA, secure boot, industrial qualification and power interruption testing not implemented or verified.
