# VirtualEdge v0.18 — isolated development TLS credential disk

**Scope:** QEMU ARM64 development only. This is NOT production key security: the ext4 disk is unencrypted, guest root can read its keys, and neither TPM/secure element, secure boot, revocation nor rotation is implemented.

## Why this change

v0.15–v0.17 allowed the server's private TLS key to be copied into the firmware root filesystem. Such an image must never be shared. v0.18 disables that legacy operation and refuses a build if the overlay or Buildroot target contains the old credential folder.

## Migration from v0.17

1. Power off the old QEMU guest. Save old images only in a private directory; treat them as compromised development credentials.
2. Remove the legacy secret directory from the rootfs overlay and from the old Buildroot target **after preserving anything you actually need in a private location**. Use the targeted commands below; do not delete the entire `out` tree.
3. Revoke/recreate old development certificates if old images were shared. For development, generate a new set with `python3 tools/virtualedge_tls_provision.py --output "$HOME/.virtualedge/tls-v018-dev"`.
4. Verify with `python3 tools/virtualedge_tls_audit.py --credentials "$HOME/.virtualedge/tls-v018-dev"`.
5. Install e2fsprogs if needed: `sudo apt-get install -y e2fsprogs`.
6. Create the independent disk with `mkdir -p out/persistent && python3 tools/virtualedge_tls_image.py --credentials "$HOME/.virtualedge/tls-v018-dev" --output out/persistent/virtualedge-tls-dev.ext4`. It refuses to overwrite an existing disk. This disk holds an **unencrypted** test private key.
7. Enable OpenSSL if not already configured: `./scripts/enable-native-tls.sh`.
8. Rebuild with `./scripts/build-and-test.sh --qemu`. The Buildroot image is not automatically verified free of historical embedded credentials; inspect any image before distributing it.
9. Use `./scripts/run-qemu-native-tls.sh` for interactive HTTPS, or `python3 scripts/test-qemu-native-tls.py --credentials "$HOME/.virtualedge/tls-v018-dev"` for isolated acceptance.

```bash
cd ~/dev/virtualedge-os
# Check before deletion. NEVER run these if QEMU is still using the old image.
ls -ld board/virtualedge/rootfs-overlay/etc/virtualedge/tls out/buildroot/target/etc/virtualedge/tls 2>/dev/null || true
# The paths below contain ONLY the old embedded development TLS credential folders.
rm -rf -- board/virtualedge/rootfs-overlay/etc/virtualedge/tls out/buildroot/target/etc/virtualedge/tls
python3 tests/test-tls-disk.py
```

## Boot design

- vda: rootfs; vdb: persistent device configuration; vdc: dedicated credentials image, mounted read-only at `/run/virtualedge-tls` by `S21virtualedge-tls-disk`.
- The native C TLS service `S97virtualedge-tls` reads credentials from `/run/virtualedge-tls`, not `/etc/virtualedge/tls`.
- The QEMU development launcher adds `ve_tls_dev=1` to the kernel command line, explicitly opting in to the service and allowing HTTPS on guest Ethernet. Default images without this parameter keep native TLS disabled.
- QEMU forwards only `127.0.0.1:18444` to guest port 8443. No guest HTTP port is forwarded.
- Keep the TLS disk and `out/` outside version control. Do not distribute the TLS disk, copy it to a cloud bucket or back it up unencrypted.

## Acceptance

```bash
python3 tests/test-tls-disk.py
python3 tests/test-native-tls.py
./scripts/build-and-test.sh --qemu
python3 scripts/test-qemu-native-tls.py --credentials "$HOME/.virtualedge/tls-v018-dev" --timeout 180
```

The unit tests verify code paths and failures, not ext4 mount semantics or actual QEMU boot. The last command is the real guest-end-to-end check and must be executed in the user's WSL environment. The guest root user still has access to development keys; on actual hardware a secure element and trusted boot should be considered.
