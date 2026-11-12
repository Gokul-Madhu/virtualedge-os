# VirtualEdge OS v0.36 — baseline-first QEMU A/B acceptance

The default `scripts/accept-qemu-ota.py` workflow now boots and tests the
**confirmed baseline slot** before starting update confirmation/fallback.
The baseline boot uses the same `scripts/test-qemu.py` runner, kernel, QEMU
machine, data-disk arrangement, and guest `/proc/cmdline` slot/version checks
as the OTA test. The confirmed slot and version are obtained from the
existing format-2 A/B manager state. The runner copies both images into
temporary files and cannot deliberately mutate the original baseline.

This addresses a specific failure mode: a candidate test may fail because
the baseline QEMU configuration is broken, making it unclear whether the
update was responsible. A baseline smoke failure now stops acceptance before
staging a candidate; it does **not** create a passing OTA report.

## Requirements

- A successfully built ARM64 Buildroot QEMU guest (`Image`, rootfs) with
  functioning `virtualedge-selftest`.
- An initialized and audited `out/ab` format-2 state with no pending update.
- A powered-off QEMU guest; do not test a mounted live persistent data image.
- A properly signed QEMU update bundle and independently trusted public key.

## One command (from Ubuntu WSL)

```bash
cd ~/dev/virtualedge-os
mkdir -p "$HOME/virtualedge-test-reports"
python3 scripts/accept-qemu-ota.py \
  --state-dir out/ab \
  --data-image out/persistent/virtualedge-data.ext4 \
  --bundle out/ota-demo/virtualedge-test-0.33.0.tar \
  --public-key "$HOME/virtualedge-private-keys/dev-ed25519.pub.pem" \
  --scenario both --timeout 240 \
  --report "$HOME/virtualedge-test-reports/ota-v036.json"
```

Sequence: signed input preflight → real ARM64 confirmed-baseline smoke boot →
real ARM64 candidate confirmation boot → two unconfirmed candidate boots →
real confirmed-slot fallback boot → strict JSON evidence validation.

Five QEMU boots are expected for `--scenario both` with smoke enabled.

Use `--skip-baseline-smoke` only for focused debugging after baseline boot is
already proven. `--preflight-only` performs no boot, even with smoke enabled.

## Limits

Host regression tests validate command construction and rejection paths.
They do NOT execute ARM64 QEMU in this packaging environment. Do not consider
v0.36 real-boot verified until the actual WSL command succeeds. A labeled
0.33.0 image that contains identical code to the baseline proves update
mechanics, not an application upgrade. The A/B manager is host-side; physical
bootloader integration, secure boot, raw partition updates and power-loss
qualification remain pending.
