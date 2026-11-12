# VirtualEdge OS v0.24 — Snapshot-verified A/B staging

## Security issue addressed

Prior to v0.24, `virtualedge_ab.py stage` verified a signed release bundle from its source pathname and then opened the same pathname again for installation. A concurrent file replacement between verification and installation could cause unverified bytes to be consumed. The installed image was compared to the *second* manifest (not the verified one), so an attacker able to replace the bundle could bypass the signature check during that race.

v0.24 first copies the release archive to a private, mode-0600, size-bounded snapshot within `--state-dir`, then runs the existing Ed25519/SHA-256 verifier against **that snapshot** and stages the image from **that same snapshot**. The original pathname is not reopened after verification. The snapshot and inactive-slot staging file are removed on errors. Existing image hash, board and anti-rollback checks remain in force.

## Failure semantics

- Invalid signatures, changed source bundles, unsupported targets, symlinks and oversized bundles are rejected.
- Staging writes to a temporary inactive-slot image and atomically renames it. The **confirmed slot** is never overwritten by staging.
- The A/B metadata JSON update is atomic and fsyncs its containing directory.
- If execution stops **after** the inactive image swap but **before** metadata changes, the confirmed slot remains bootable. The operator may rerun `stage` after inspecting state; the inactive image may be an orphan and will be overwritten on a successful retry.
- This is a QEMU-host development mechanism: it does **not** provide physically power-fail-safe OTA writes, hardware-rooted trust, or firmware secure boot.

## Update instructions

Stop QEMU before modifying a slot image. Back up your existing state and rootfs images before upgrading. Existing v0.23 format-2 A/B metadata is unchanged; no migration is necessary.

```bash
cd ~/dev/virtualedge-os
python3 tests/test-ab-snapshot.py
python3 tests/test-ab-integrity.py
python3 tests/test-ab-slots.py
python3 tools/virtualedge_ab.py --state-dir out/ab audit
```

For real staging, use a verified release publisher public key and correct board:

```bash
python3 tools/virtualedge_ab.py --state-dir out/ab stage \
    --bundle "$HOME/virtualedge-v0.24.0-qemu-release.tar" \
    --public-key "$HOME/virtualedge-private-keys/dev-ed25519.pub.pem"
python3 tools/virtualedge_ab.py --state-dir out/ab status
```

The bundle path shown is illustrative; first create a properly signed image following `docs/SIGNED_RELEASES.md`. Do not stage an unverified external bundle on an actual device.

## Acceptance evidence

- `tests/test-ab-snapshot.py` deliberately replaces the original bundle **after** signed verification and asserts that only the originally snapshotted image is installed.
- Tests ensure invalid bundles and symlinked sources are rejected, and a metadata write failure does not overwrite the confirmed slot.
- Existing slot, integrity, guest-acceptance logic and signed-release host suites are compatibility checks.
- Actual Buildroot cross-compilation, real QEMU boot, power-loss recovery and physical-board OTA are **not** validated by these host tests.
