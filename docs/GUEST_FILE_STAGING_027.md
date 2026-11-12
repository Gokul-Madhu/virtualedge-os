# VirtualEdge OS v0.27 — Guest-side verified **file** staging

This milestone is **not an OTA installer** and does **not write block devices**.
It moves authenticated release-image *staging* into the ARM64 Linux guest, without
changing A/B slot selection, persistent metadata, bootloader state, or partitions.

## Security boundaries

`virtualedge-update-stage` requires a pre-existing absolute staging directory
owned by the executing user with mode `0700`. It rejects existing `candidate`
entries, symlinked sources, nonregular files and oversized inputs. It copies
three inputs into a private temporary directory in the staging volume, syncs
those copied files, invokes `virtualedge-update-verify` on those *same copied
bytes*, and publishes the validated candidate as one directory using Linux
`renameat2(RENAME_NOREPLACE)`. The containing directory is fsynced after
publication. Failed verification or copy leaves no published candidate.

Its external verifier path is an explicitly trusted executable, not downloaded
from the update bundle. **Do not point it at an attacker-controlled program.**
The Ed25519 trusted public key must also be provisioned independently of the
bundle. An operator with root access or control of the staging directory is
outside the threat model. This is not a sandbox and does not enforce real-time
revocation of signing keys. Secure boot, antirollback state protection, and
power-failure guarantees for physical flash are not provided.

## Host regression

```bash
python3 tests/test-guest-update-verify.py
python3 tests/test-guest-update-stage.py
```

## Build for ARM64

```bash
./scripts/enable-native-tls.sh
./scripts/build-and-test.sh --qemu
```

The OpenSSL-enabled build installs `/usr/bin/virtualedge-update-verify` and
`/usr/bin/virtualedge-update-stage` in the guest. If OpenSSL is not enabled,
neither executable is installed.

## Guest example (offline, extracted, trusted release files)

First transfer `manifest.json`, `manifest.sig`, and `image.bin` to the guest by
a channel you control. Do not use arbitrary `tar -xf` in privileged directories.
The signed `manifest.json` binds the exact bytes of `image.bin` and expected
board/version. Place the trusted Ed25519 public key **outside** the bundle at
`/etc/virtualedge/release-trust.pub.pem` after reviewing your provisioning path.

With a writable persistent `/data` volume mounted:

```sh
mkdir -m 700 /data/virtualedge-update-stage
virtualedge-update-stage \
  /data/virtualedge-update-stage \
  /tmp/update/manifest.json \
  /tmp/update/manifest.sig \
  /tmp/update/image.bin \
  /etc/virtualedge/release-trust.pub.pem \
  qemu-aarch64 0.26.0 \
  /usr/bin/virtualedge-update-verify
ls -l /data/virtualedge-update-stage/candidate
```

Do not run the command twice expecting an overwrite: `candidate` is deliberately
immutable through this workflow until an operator safely removes or archives it.
The staged candidate is a set of **regular files**, not a bootable installed
OS; do not call `reboot` expecting an A/B update. No automatic A/B transition is
performed. Never point this tool at `/dev/*` as a destination.

## Acceptance still needed

- ARM64 cross-compile and end-to-end guest invocation in user's WSL/QEMU setup.
- Filesystem crash tests on ext4 including forced VM/power interruptions.
- On-device inactive-slot layout, protected bootloader integration, immutable
  trust root and fail-safe rollback before attempting physical OTA installation.
