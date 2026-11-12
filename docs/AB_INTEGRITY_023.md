# VirtualEdge OS v0.23 — Host-side A/B image integrity

The v0.23 QEMU A/B manager records SHA-256 digests for rootfs slot images in
`out/ab/state.json` (`format: 2`). It rehashes the relevant image before staging,
boot selection, and candidate confirmation. A corrupt pending slot is rejected,
the pending state cleared, and the previously confirmed slot selected if its
hash is valid. If the confirmed slot is corrupt, boot selection stops instead
of trusting the candidate as a recovery path.

**Security boundary:** this is host-side corruption detection, *not* secure or
measured boot. Both the image files and their expected hashes are editable by
the same host; a compromised host can change both. The Linux kernel loaded by
QEMU is still outside the signed image bundle. This does not protect physical
flash, power-loss durability, or a device's own bootloader.

## Install and verify

Shut down QEMU before changing slot images or source. Do not delete `out/ab`.

```sh
cd ~/dev/virtualedge-os
python3 tests/test-ab-integrity.py
python3 tests/test-ab-slots.py
python3 tools/virtualedge_ab.py --state-dir out/ab status
```

If `out/ab/state.json` is format `1` (created by v0.10–v0.22), inspect the
images, ensure the guest is powered off, then explicitly record those current
bytes as the migration baseline:

```sh
python3 tools/virtualedge_ab.py --state-dir out/ab enroll
```

This does **not** verify those historical images are genuine: it trusts the
operator's current offline baseline. If format is already `2`, `enroll` refuses
to run. For brand-new `init`, v0.23 creates format `2` automatically.

Check each recorded image against its digest:

```sh
python3 tools/virtualedge_ab.py --state-dir out/ab audit
```

A mismatched or missing image makes `audit` fail. Do **not** automatically
re-enroll hashes after a mismatch. Investigate and restore from a known-good
verified bundle or backup. The A/B launcher runs the check during `boot`.

## Corruption test (disposable state only)

Run `python3 tests/test-ab-integrity.py`. This creates fresh temporary disk
files, alters them, and confirms corruption rejection. **Never intentionally
corrupt `out/ab` or a real device to demonstrate this.**

## Remaining gaps

- No immutable trust anchor, protected anti-rollback counter, secure boot,
  signed kernel or verified root filesystem in the guest.
- No power-loss-qualified block-device update or actual on-device installer.
- QEMU guest acceptance, rollback and power-loss tests must run in Ubuntu WSL.
