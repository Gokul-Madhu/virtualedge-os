# Automated QEMU verification

From Ubuntu WSL, **with the existing QEMU guest shut down**:

```bash
cd ~/dev/virtualedge-os
./scripts/test-host.sh
./scripts/build-and-test.sh --qemu
```

Alternatively, for an image that is already built:

```bash
python3 scripts/test-qemu.py --timeout 240
```

The runner starts QEMU with 256 MiB, attaches a serial console, boots the kernel from `out/buildroot/images/Image`, and attaches a **temporary copy** of `rootfs.ext4` instead of modifying the master image. It logs in as the configured root user, invokes `virtualedge-selftest` and requires both the guest's pass marker and exit code 0. There is a configurable timeout; diagnostics stream to your terminal.

The root login must be passwordless for this **development test image**. Production images must not retain passwordless root console access. Failure to recognize a serial prompt results in a timeout, not a false pass.

If QEMU cannot boot under WSL (or the guest config differs), inspect serial output, run `./start-qemu.sh` manually, log in as root, then run `virtualedge-selftest`.

This checks boot and local API functionality; it does not test real sensors, TLS/OTA, industrial safety, network threats or power-failure endurance.
