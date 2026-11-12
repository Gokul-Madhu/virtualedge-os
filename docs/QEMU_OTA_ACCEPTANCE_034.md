# VirtualEdge OS v0.34 — QEMU A/B acceptance runbook

## Scope

`accept-qemu-ota.py` verifies the existing signed release and host-managed A/B
state *before* booting any QEMU guest. It then runs the disposable `test-qemu-ota.py`
confirmation and fallback scenarios and verifies that the resulting JSON report
contains explicit **real QEMU ARM64** boot evidence rather than a host stub.
It does **not** install an image on a physical partition, alter a bootloader,
provide verified/secure boot or demonstrate electrical power-cut tolerance.

## Preconditions (Ubuntu WSL)

- Buildroot ARM64 kernel and ext filesystem already built; ordinary guest self-test passed.
- `out/ab/state.json` is initialized with format-2 state and **no pending update**.
- Confirmed A/B image must be a real regular file (copy Buildroot's symlink using `cp -L`).
- Separate persistent `out/persistent/virtualedge-data.ext4` file exists.
- Ed25519 private signing key remains outside the source tree; `--public-key` points to the trusted corresponding public key.
- QEMU must be stopped; the acceptance runner clones the root and data images.
- The candidate release must target `qemu-aarch64` and have a higher version than the confirmed baseline.
- Use a **new** report filename for each attempt.

## One command

```bash
cd ~/dev/virtualedge-os
mkdir -p "$HOME/virtualedge-test-reports"
python3 scripts/accept-qemu-ota.py \
  --state-dir out/ab \
  --data-image out/persistent/virtualedge-data.ext4 \
  --bundle out/ota-demo/virtualedge-test-0.33.0.tar \
  --public-key "$HOME/virtualedge-private-keys/dev-ed25519.pub.pem" \
  --scenario both --timeout 240 \
  --report "$HOME/virtualedge-test-reports/ota-accept-01.json"
```

Use `--preflight-only` to check inputs without launching QEMU or producing a report.

**Successful acceptance requires FOUR real guest boots:** a candidate confirmed
after its self-test in the confirmation scenario, and in the independent fallback
scenario two unconfirmed candidate boots followed by a boot of the original
confirmed slot. Every guest boot must return a passing self-test, and the JSON
report must show unchanged hashes for original data and A/B state.

Inspect with:

```bash
python3 -m json.tool "$HOME/virtualedge-test-reports/ota-accept-01.json"
python3 tools/virtualedge_ab.py --state-dir out/ab audit
```

A failed run might still write a **failure** report. Never treat existence of a
report as evidence of success. Don't rerun `init`, overwrite the baseline, or
rename a failing report to make the test appear successful.

## Known caveats

- A `0.33.0` signature on the current rootfs tests A/B mechanics, **not** the
  behavior of a new firmware build.
- Rootfs images and host-side metadata are software files in WSL; the host is
  part of the trust boundary. SHA-256 metadata is not a secure-boot trust anchor.
- Linux virtio device enumeration varies. Launchers in this release attach data
  first and root second to obtain `root=/dev/vda` in the previously tested setup.
  Verify `cat /proc/cmdline` and `mount` on each target QEMU version.
- QEMU `-nographic` guest is shut down by the acceptance tester. Do not run a
  separate QEMU against the persistent data image while acceptance is executing.
