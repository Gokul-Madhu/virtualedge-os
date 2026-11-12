# VirtualEdge v0.30 — Disposable QEMU A/B OTA acceptance

This **host-only** automation joins existing signed bundle staging, A/B trial boot
selection, the real ARM64 QEMU `virtualedge-selftest`, explicit promotion and
unconfirmed fallback. It **does not** run the guest-side native updater, download
packages, write partitions, verify a bootloader, or simulate an actual power cut.

## Prerequisites

- Ubuntu WSL2 with existing Buildroot ARM64 `out/buildroot/images/Image` and
  `out/buildroot/host/bin/qemu-system-aarch64` (or system QEMU).
- A previously initialized QEMU A/B state directory `out/ab`, **format 2**, with
  a confirmed filesystem image, **no pending update**, and passing `audit`.
- A persistent data image `out/persistent/virtualedge-data.ext4`.
- An independently trusted release public key and a correctly signed update
  bundle built for `qemu-aarch64`, with a release version strictly higher than
  the confirmed slot. The image must boot with your existing QEMU kernel.
- Ensure no other QEMU process is writing to the state or data disk.

## Prepare and verify

```bash
cd ~/dev/virtualedge-os
./scripts/build-and-test.sh --qemu
python3 tests/test-qemu-ota.py
python3 tools/virtualedge_ab.py --state-dir out/ab audit
python3 tools/virtualedge_ab.py --state-dir out/ab status
```

If needed, initialize a fresh A/B state **only after checking** your source image:

```bash
python3 tools/virtualedge_ab.py --state-dir out/ab init \
  --image out/buildroot/images/rootfs.ext4 --version 0.29.0
```

Do not run `init` over existing state, and ensure `--version` accurately reflects
that image. To prepare an illustrative signed update using an independently stored
*development* key (change version to the actual newly built image release):

```bash
python3 tools/virtualedge_release.py pack \
  --image /path/to/NEW-bootable-rootfs.ext4 \
  --private-key "$HOME/virtualedge-private-keys/dev-ed25519.pem" \
  --board qemu-aarch64 --version 0.30.0 \
  --output "$HOME/virtualedge-qemu-update-0.30.0.tar"
```

**Do not sign an old baseline image merely to satisfy the higher version check.**
The signed image must actually contain the desired update and boot correctly.

## Automated full acceptance

```bash
python3 scripts/test-qemu-ota.py \
  --state-dir out/ab \
  --data-image out/persistent/virtualedge-data.ext4 \
  --bundle "$HOME/virtualedge-qemu-update-0.30.0.tar" \
  --public-key "$HOME/virtualedge-private-keys/dev-ed25519.pub.pem" \
  --timeout 180 --scenario both
```

`--scenario confirm` boots the pending image and confirms it **in disposable
state only** after a successful guest self-test. `--scenario fallback` boots the
pending image twice **without confirmation**, then verifies that the subsequent
QEMU boot uses the old confirmed image. `both` runs each independently.

Every scenario copies the original A/B metadata, images and data disk into
separate temporary directories. The guest harness also makes its own QEMU disk
copies. The original `out/ab` state and persistent data disk are not changed.
This can need significant free disk space and time; each root filesystem may be
copied multiple times.

The runner fails on invalid hashes, mismatched slot/version reported by the
guest, signed bundle rejection, or a nonzero guest self-test. Failed QEMU boots
are never confirmed. No private signing key is needed during verification.

## What this does NOT test

- Native guest-side staging and image installer (v0.27/v0.28) end-to-end.
- Real block-partition writes or durable bootloader slot selection.
- Power interruption, physical storage endurance, or secure boot.
- Concurrent mutations to the supplied A/B source state: stop interactive QEMU
  and update tools during acceptance.

Host orchestrator tests use an injected stub in place of real QEMU and therefore
must not be described as an actual ARM64 boot result. The real boot acceptance
is available only when the command above runs on a compatible QEMU/WSL build.
