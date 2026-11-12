# VirtualEdge OS v0.10 — QEMU A/B rootfs evaluation

**Scope:** Host-side *QEMU-only* A/B root filesystem selection, with offline
Ed25519-verified image staging and an attempt-counted fallback. This is NOT
an OTA installer, secure boot, on-device bootloader, power-failure-qualified
system, or production rollback mechanism. The kernel is still loaded from the
existing Buildroot `images/Image` and is NOT included in the signed rootfs
bundle; updates requiring a different kernel are not supported by this demo.

The confirmed rootfs is never overwritten while staging a candidate. A
separate ext4 data volume from v0.9 is shared across slots and not included
in the signed update bundle. Keep the guest powered off while staging images.

## Prepare on WSL (QEMU off)

```sh
cd ~/dev/virtualedge-os
./scripts/test-host.sh
./scripts/build-and-test.sh --qemu
# First provision the persistent QEMU disk using the v0.9 launcher.
# If it already exists, DO NOT recreate it.
ls -lh out/persistent/virtualedge-data.ext4
# Initialize A with the currently built rootfs. Run ONCE only:
python3 tools/virtualedge_ab.py --state-dir out/ab init \
  --image out/buildroot/images/rootfs.ext4 --version 0.9.0
python3 tools/virtualedge_ab.py --state-dir out/ab status
```

Ensure the persistent data file already exists before invoking the A/B
launcher. If missing, first boot `./scripts/run-qemu-persistent.sh` and
shutdown safely to let it create the disk.

## Stage a signed candidate

Create private signing keys *outside* the project, and never commit them:

```sh
mkdir -p ~/virtualedge-private-keys
python3 tools/virtualedge_release.py keygen \
  --private-key ~/virtualedge-private-keys/dev.pem \
  --public-key ~/virtualedge-private-keys/dev.pub.pem
python3 tools/virtualedge_release.py pack \
  --image out/buildroot/images/rootfs.ext4 \
  --private-key ~/virtualedge-private-keys/dev.pem \
  --board qemu-aarch64 --version 0.10.0 \
  --output ~/virtualedge-v0.10.0-qemu.tar
python3 tools/virtualedge_ab.py --state-dir out/ab stage \
  --bundle ~/virtualedge-v0.10.0-qemu.tar \
  --public-key ~/virtualedge-private-keys/dev.pub.pem
```

Use a genuinely new rebuilt image when testing software changes. The above
commands illustrate the update format and selection logic, not a validated
functional upgrade. The `stage` tool checks signature, file digest, board
identity, and monotonic release version, and writes the inactive slot.

## Boot, validate, and confirm

```sh
./scripts/run-qemu-ab.sh
```

In the QEMU guest, log in as root, check `/proc/cmdline` for `ve.slot=B`, run
`virtualedge-selftest`, verify dashboard/configuration/data mounts and any
update-specific features, then `sync; poweroff`.

Once you have **actually seen** the test pass, confirm explicitly on WSL:

```sh
python3 tools/virtualedge_ab.py --state-dir out/ab confirm \
  --slot B --guest-selftest-passed
python3 tools/virtualedge_ab.py --state-dir out/ab status
```

No test suite automatically proves guest health or invokes `confirm`. The
confirmation flag is an operator attestation, not a cryptographic guest
measurement.

If the candidate is never confirmed, two `boot` calls select the candidate;
the third falls back to the previously confirmed slot. `abort` explicitly
abandons a pending candidate. Note: a `boot` invocation consumes an attempt
*before* QEMU runs, even if QEMU fails to start.

## Risk boundaries

- **Do not use on physical devices, production storage, or moving machinery.**
- QEMU disk images are writable; guest corruption, power loss, malicious
  root access, or incorrect host operations are not qualified or protected.
- A compromised host can replace state or the trust key. Anti-rollback is a
  software comparison, not a TPM-backed monotonic counter.
- Neither the guest bootloader nor the Linux kernel verifies the candidate.
- There is no automatic rollback based on actual guest boot health; the host
  falls back only if the candidate is not explicitly confirmed after attempts.
- Signed rootfs images do not cover the bootloader, kernel or device tree.
- We recommend immutable verified boot, protected persistent storage,
  on-device signature verification and recovery tests before any deployment.
