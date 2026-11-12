# VirtualEdge OS v0.31: QEMU OTA acceptance evidence

This release adds SHA-256 non-mutation checks and machine-readable reports to the
v0.30 disposable QEMU acceptance runner. It **does not** install onto a raw
block device, validate real hardware, or replace trusted/verified boot.

## Acceptance prerequisites

The A/B directory must be format 2 with a confirmed image and no pending
update. It must pass `virtualedge_ab.py ... audit`. The separate data disk must
exist. The bundle must be signed for `qemu-aarch64` by an independently trusted
Ed25519 key and contain a genuinely bootable, updated ARM64 filesystem.

Stop other QEMU instances that may use the same host resources. Build the ARM64
image first using `./scripts/build-and-test.sh --qemu` in the existing WSL
Buildroot environment.

## Commands

```bash
cd ~/dev/virtualedge-os
python3 tests/test-ota-evidence.py
python3 tests/test-qemu-ota.py

mkdir -p "$HOME/virtualedge-test-reports"
python3 scripts/test-qemu-ota.py \
  --state-dir out/ab \
  --data-image out/persistent/virtualedge-data.ext4 \
  --bundle "$HOME/virtualedge-qemu-update-0.31.0.tar" \
  --public-key "$HOME/virtualedge-private-keys/dev-ed25519.pub.pem" \
  --timeout 180 \
  --scenario both \
  --report "$HOME/virtualedge-test-reports/ota-v031.json"
cat "$HOME/virtualedge-test-reports/ota-v031.json"
```

The bundle and public-key paths above are examples; create a real update release
using your own offline key and known-good Buildroot image. The acceptance report
must not exist beforehand. Existing reports are never overwritten.

## Evidence semantics

Each scenario report includes SHA-256 fingerprints for the *original* A/B
metadata, original populated slot image(s), and original persistent data image.
After the temporary test environment is discarded, hashes are recomputed for
the originals. A mismatch fails acceptance. The JSON report records pass/fail
for each scenario, and the first error where available. Report permissions are
mode 0600. The report itself is **local diagnostic evidence, not a signed
attestation**. A hostile host can forge the report or manipulate the QEMU
execution environment. The baseline fingerprints are not a boot trust anchor.

The suite `tests/test-qemu-ota.py` uses a fake guest runner and does not prove
that ARM64 boot works. Only a successful execution of
`scripts/test-qemu-ota.py` with the real `scripts/test-qemu.py` runner provides
QEMU guest acceptance evidence.

## Limitations

The QEMU kernel is provided from the build output, not from the candidate's
signed root filesystem. The guest-reported slot/version is based on the QEMU
kernel command line and does not constitute cryptographic attestation of the
root filesystem. Other devices on the machine, secure boot, disk power-failure
behavior and full production OTA remain unverified.
