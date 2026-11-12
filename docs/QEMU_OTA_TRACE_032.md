# VirtualEdge OS v0.32 — QEMU OTA acceptance trace

v0.32 strengthens the host-side QEMU OTA acceptance report. It does not implement guest-side block-device flashing, trusted boot, or real power-loss safety.

## Improvements

- Schema-2 JSON reports identify each tested scenario and record chronological guest boot selections (`slot`, `version`, and successful self-test outcome).
- Trial boots record attempt numbers. The fallback boot is separately labeled.
- The report records `promotion` as `confirmed_after_selftest`, `not_confirmed_fallback`, or `not_attempted`.
- Internal host regression tests label the runner `host-test-stub`. Actual `scripts/test-qemu-ota.py` invocations use the QEMU runner, but a successful report still requires running the command on a built ARM64 image.
- Report creation remains mode 0600, non-overwriting, and fsyncs the report and containing directory. The CLI rejects report paths overlapping the A/B state directory, persistent data image, signed bundle or trusted public key, and rejects symlinked output ancestors.
- Original slot metadata, slot images, and data disk still undergo SHA-256 comparison before and after each acceptance scenario, including on failure.

## Host tests

```bash
python3 tests/test-ota-trace.py
python3 tests/test-ota-evidence.py
```

`test-ota-trace.py` uses the real signed release and A/B manager, but **replaces actual guest execution with a test stub**. It is not evidence that QEMU boots.

## Real QEMU acceptance (Ubuntu WSL)

First build VirtualEdge with `./scripts/build-and-test.sh --qemu`, initialize A/B state and a separate data ext4 image, and prepare a *newer bootable* signed firmware bundle. Shut down any interactive QEMU session before starting acceptance:

```bash
mkdir -p "$HOME/virtualedge-test-reports"
python3 scripts/test-qemu-ota.py \
  --state-dir out/ab \
  --data-image out/persistent/virtualedge-data.ext4 \
  --bundle "$HOME/virtualedge-qemu-update.tar" \
  --public-key "$HOME/virtualedge-private-keys/dev-ed25519.pub.pem" \
  --timeout 180 --scenario both \
  --report "$HOME/virtualedge-test-reports/ota-v032.json"
python3 -m json.tool "$HOME/virtualedge-test-reports/ota-v032.json"
```

The bundle and public key filenames are illustrative. If you have not created an updated bootable image, do not run the command with a dummy bundle and expect success. Use a new report filename for each acceptance run.

**Not supplied:** signed report attestation, TPM-backed measurements, physical flash writes, bootloader verification, and real interruption/restore acceptance.
