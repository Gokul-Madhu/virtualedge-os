# QEMU OTA preflight — v0.33

Use the preflight **before** an expensive multi-boot QEMU OTA acceptance run.

## Prerequisites

- Shut down any interactive QEMU instance; do not mount the same data image in WSL while QEMU is using it.
- Use a format-2 A/B state (`out/ab`) with an initialized and audited confirmed slot; never re-run `init` on an existing state.
- Use an Ed25519-signed release that was independently verified by the VirtualEdge release tool.
- Keep release **private** signing keys outside the project and the guest.
- Ensure the persistent data disk contains the expected configuration (the acceptance runner copies it).

## Preflight command

```bash
cd ~/dev/virtualedge-os
python3 tests/test-ota-preflight.py
python3 scripts/preflight-qemu-ota.py \
    --state-dir out/ab \
    --data-image out/persistent/virtualedge-data.ext4 \
    --bundle out/ota-demo/virtualedge-test-0.33.0.tar \
    --public-key "$HOME/virtualedge-private-keys/dev-ed25519.pub.pem"
```

The preflight checks original A/B digests, ext filesystem magic in the A/B baseline, update image and data volume, verifies signed release using the existing original verifier, and estimates disk space for disposable QEMU copies. It does not modify inputs, create images, select slots or claim that an ext filesystem will boot. An ext superblock alone does **not** establish a complete working Linux root filesystem.

A notice about equal candidate/baseline hashes means a **version-label-only test**; no application change is demonstrated. If the hashes differ, QEMU boot compatibility still needs testing.

## Real QEMU acceptance (separate)

```bash
mkdir -p ~/virtualedge-test-reports
python3 scripts/test-qemu-ota.py \
    --state-dir out/ab \
    --data-image out/persistent/virtualedge-data.ext4 \
    --bundle out/ota-demo/virtualedge-test-0.33.0.tar \
    --public-key "$HOME/virtualedge-private-keys/dev-ed25519.pub.pem" \
    --timeout 240 --scenario both \
    --report "$HOME/virtualedge-test-reports/ota-v033.json"
```

Use a **new report path** for each invocation. Boot success, readiness, candidate confirmation and fallback only count after this real QEMU run succeeds and the report confirms `execution: qemu-arm64`. Host test stubs or signed-bundle preflight cannot substitute for that evidence.

## Remaining work

No raw block-device writes, hardware bootloader recovery, secure boot, or physical power-loss qualification are provided by this QEMU test system.
