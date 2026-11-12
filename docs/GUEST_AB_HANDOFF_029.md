# VirtualEdge OS v0.29 — Guest verified-file → host QEMU A/B handoff

**Development tool, not production OTA.** This joins two previously separate
prototypes: the v0.27 guest-side `candidate/` with its signed manifest,
signature and image; the v0.28 guest-side `inactive-slot.img`; and the v0.10+
WSL-hosted QEMU A/B manager.

It requires an **offline export** of all four files from the guest to the WSL
host. Shut QEMU down before exporting from its persistent ext4 disk. Exporting
is deliberately not automated because this project has not established a
safe, writable, shared guest-host filesystem or a validated disk extraction
workflow. Do not use the same image simultaneously in guest and host.

Expected host-side inputs:

```
/path/to/export/candidate/manifest.json
/path/to/export/candidate/manifest.sig
/path/to/export/candidate/image.bin
/path/to/export/inactive-slot.img
```

The `inactive-slot.img` must be byte-identical to `candidate/image.bin`.
The importer snapshots all input files into a private directory, rejects
symlinks and oversized inputs, compares SHA-256 and sizes, creates a temporary
signed release bundle using the *exported image*, and passes that private
bundle to the existing `virtualedge_ab.py stage` command. That manager verifies
Ed25519 using the separately trusted public key, enforces `qemu-aarch64`,
checks version and image digest, snapshots again, and atomically updates the
inactive image and host-side A/B state. The previous confirmed slot remains
unchanged.

## Test in Ubuntu WSL

```bash
cd ~/dev/virtualedge-os
python3 tests/test-ab-guest-handoff.py
```

## Import an exported guest candidate

Stop all QEMU instances using the persistent data disk or A/B images first.
Initialize the existing A/B manager if not already initialized (see
`docs/AB_QEMU.md`). Use a public key you provisioned and trust separately.

```bash
python3 tools/virtualedge_ab_import.py \
    --state-dir out/ab \
    --candidate-dir /path/to/export/candidate \
    --inactive-image /path/to/export/inactive-slot.img \
    --public-key "$HOME/virtualedge-private-keys/dev-ed25519.pub.pem"
python3 tools/virtualedge_ab.py --state-dir out/ab audit
python3 tools/virtualedge_ab.py --state-dir out/ab status
```

Never use the public key that comes bundled with an untrusted update.
To trial-boot the pending candidate, use `./scripts/run-qemu-ab.sh` or the
existing guest acceptance harness, after ensuring your QEMU persistent-data
image is available. Confirm *only* after a successful guest self-test and
readiness verification. If the candidate fails to confirm, the manager falls
back according to its existing boot-attempt counter.

## Important limits

- No raw block-device writes, changes to bootloaders, automatic firmware
  downloads, trusted boot, or physical-device A/B handling are added.
- Exported files and the host-managed QEMU state must not be concurrently
  modified by external processes. Trusted code and keys on the host remain
  outside an adversarial host threat model.
- The test uses small synthetic image files; it does not boot a new guest.
- Real ext4 image export, ARM64 cross-build, guest boot, guest-side install
  and power-loss durability still require separate validation.
