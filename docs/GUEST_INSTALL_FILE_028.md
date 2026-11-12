# VirtualEdge OS v0.28 — signed candidate → inactive regular-file image

**Development-only, deliberately NOT a block-device OTA installer.** This release
implements `virtualedge-update-install-file`: a small native C utility which
accepts a `candidate/` created by `virtualedge-update-stage`, copies its three
files to a *new private snapshot*, calls the independent trusted
`virtualedge-update-verify` executable on that snapshot, and atomically
publishes the image bytes as `inactive-slot.img` in a private destination
folder. The public key must come from a trusted source independent of the update.

It refuses an existing `inactive-slot.img`, non-private directories, symlinks
for the staged image, mismatched signatures/hashes, wrong boards, and versions
below the supplied floor. It operates on ordinary files, not physical partitions;
it **does not change boot metadata, select a rootfs, reboot, or write `/dev/*`**.
It is not power-failure qualified and does not provide a verified boot chain.

## Run selected WSL host tests

```bash
python3 tests/test-guest-update-install-file.py
python3 tests/test-guest-update-stage.py
python3 tests/test-guest-update-verify.py
```

The standard `./scripts/build-and-test.sh --qemu` cross-compiles the new program
when Buildroot OpenSSL is enabled with `./scripts/enable-native-tls.sh`.
A successful ARM64 cross-build and actual QEMU test still need to be run in WSL.

## Example inside the guest (after staging a signed bundle)

Provision a trusted Ed25519 public key and staged candidate. On a writable
persistent filesystem:

```sh
mkdir -m 700 /data/virtualedge-inactive-files
virtualedge-update-install-file \
    /data/virtualedge-update-stage \
    /data/virtualedge-inactive-files \
    /etc/virtualedge/release-trust.pub.pem \
    qemu-aarch64 \
    0.27.0 \
    /usr/bin/virtualedge-update-verify
ls -l /data/virtualedge-inactive-files/inactive-slot.img
```

The output `inactive-slot.img` is a *regular file to inspect*, not an active
boot partition. Never rename/copy it to a physical disk or alter QEMU boot
parameters without separate layout and rollback acceptance.

A failed install leaves the destination without an image except for unusual
late failures after publication (e.g. `fsync` failure); in that case inspect
and discard the destination file manually before retrying. A successful install
refuses to overwrite its output on subsequent attempts. The file is created
with mode 0600 and the parent directory must be owner-controlled mode 0700.

## Next gate

Validate the precise QEMU block topology and use a bootloader-controlled A/B
layout with read-only current root, inactive partition identification, write
barriers, retry tracking and real power interruption tests. Do not extend this
utility to raw block devices as a shortcut.
