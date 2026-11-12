# VirtualEdge OS v0.11 — QEMU candidate acceptance

## What changed

- `scripts/test-qemu.py` accepts `--rootfs`, `--data-image`, `--expected-slot` and `--expected-version`.
- All test disk files are copied to a temporary directory. The persistent data volume and staged candidate are **not** written during the test.
- The guest boots with an explicit slot/version marker in `/proc/cmdline`, which the harness checks via serial before running `virtualedge-selftest`.
- `scripts/check-ab-candidate.py` consumes one pending A/B boot attempt, runs the real QEMU guest self-test against the candidate, and **only** calls the host-side `confirm` command with `--confirm-on-pass` when the check succeeds.
- A failed boot, unexpected slot/version, missing data disk, or failing self-test leaves the confirmed slot unchanged.

## Setup and acceptance in VirtualEdge-Ubuntu (WSL)

Before using this procedure, **power off any running QEMU guest**. Install the source archive into `~/dev/virtualedge-os`, preserve the existing `out/` tree, and build:

```sh
cd ~/dev/virtualedge-os
./scripts/test-host.sh
./scripts/build-and-test.sh --qemu
```

The `--qemu` argument above validates the *current Buildroot image*. It does not stage or confirm an update.

For an existing A/B setup (initialize it only once, as documented in `docs/AB_QEMU.md`), stage a **newer signed image** into the inactive slot:

```sh
python3 tools/virtualedge_ab.py --state-dir out/ab status
python3 tools/virtualedge_ab.py --state-dir out/ab stage \
  --bundle ~/virtualedge-candidate-qemu.tar \
  --public-key ~/virtualedge-private-keys/dev.pub.pem
```

Test the pending candidate without promotion:

```sh
python3 scripts/check-ab-candidate.py
python3 tools/virtualedge_ab.py --state-dir out/ab status
```

To confirm a still-pending candidate **only if the QEMU guest test passes**, run:

```sh
python3 scripts/check-ab-candidate.py --confirm-on-pass
python3 tools/virtualedge_ab.py --state-dir out/ab status
```

Each test consumes a pending boot attempt even if unsuccessful. The default budget is two. To validate and confirm in one attempt, use `--confirm-on-pass` on the first call after staging, but only when you intentionally want that promotion. With no attempts remaining, the next `boot` action falls back to the confirmed slot.

## Safety boundaries

This is a **host-side QEMU demonstration**, not an on-device bootloader or firmware installer. The untrusted guest is given a slot/version string by the host kernel command line: it is useful acceptance evidence but is not a cryptographic binding to the rootfs image. The kernel itself is loaded from the Buildroot output tree, not signed by the release bundle. The host state manager's `--guest-selftest-passed` flag remains an operator attestation and should only be used after genuine verification. Rootfs and persistent disk copies protect the real QEMU test images against normal guest writes, not against a compromised host.

The tests do **not** demonstrate power-loss atomicity, secure boot, device-side OTA, or physically verified rollback. Do not deploy this flow on a physical device or use it for safety-critical operation.
