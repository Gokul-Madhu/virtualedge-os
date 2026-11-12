# VirtualEdge OS v0.22 — two-boot CRL acceptance

This development-only check exercises the **real ARM64 QEMU native mTLS service** twice. It creates a disposable development CA and three individual client credentials under a temporary directory (never inside the source tree):

1. Create a fresh CA and signed CRL, issue **alpha** and **bravo**.
2. Build a disposable, read-only TLS credential ext4 disk from that CA.
3. Boot the existing ARM64 root filesystem in a disposable QEMU copy and require both clients to receive `/ready` HTTP 200. Anonymous access must fail.
4. Rotate alpha to **charlie**, signing a new CRL that revokes alpha.
5. Build another credential ext4 disk, leaving the original disk untouched.
6. Boot QEMU a second time and require bravo and charlie to receive HTTP 200. Alpha and anonymous clients must not receive a ready HTTP 200 response.
7. Clean up the two guest processes, copied root filesystems, development certificate keys and temporary images.

This tests certificate authorization and guest **revocation enforcement after reboot**, not unattended CRL delivery or secure persistent storage. Keys on the disposable ext4 images are **unencrypted**. Never use production keys in this workflow.

## Prerequisites — Ubuntu WSL

- Complete the v0.21 instructions for enabling OpenSSL in Buildroot.
- Run `./scripts/build-and-test.sh --qemu` successfully, using v0.22 source (no embedded TLS key). The compiled ARM64 guest image must include the `virtualedge-tls` service.
- Install `openssl`, `e2fsprogs`, and `qemu-system-aarch64` as needed; the test can also use Buildroot's host QEMU binary.
- Ensure the QEMU HTTPS forwarding port **18444** is not in use. Stop any interactive QEMU instance first.
- Rootfs `out/buildroot/images/rootfs.ext4` and `out/buildroot/images/Image` must exist.

## Run the two-boot acceptance test

```bash
cd ~/dev/virtualedge-os
python3 tests/test-qemu-crl-lifecycle.py
python3 scripts/test-qemu-crl-lifecycle.py --timeout 180
```

The final line `PASS: Real ARM64 QEMU TLS CRL rotation and revocation lifecycle` means both QEMU boots and all authentication checks succeeded. These are **expected outputs, not preverified results** for your machine.

## Run a single QEMU TLS check with explicit clients

```bash
python3 scripts/test-qemu-native-tls.py \
  --credentials "$HOME/.virtualedge/tls-v019-dev" \
  --tls-image out/persistent/virtualedge-tls-dev.ext4 \
  --approved "$HOME/.virtualedge/tls-v019-dev/clients/bravo/client.pem" "$HOME/.virtualedge/tls-v019-dev/clients/bravo/client.key" \
  --revoked "$HOME/.virtualedge/tls-v019-dev/clients/alpha/client.pem" "$HOME/.virtualedge/tls-v019-dev/clients/alpha/client.key"
```

The single-run example requires those specific identities and a disk with the corresponding updated signed CRL. Use the automated lifecycle command for a clean, reproducible test instead.

## Limits and interpretation

- Rejection means a revoked client **did not receive** an authenticated readiness HTTP 200; the script does not distinguish a revocation alert from all other TLS handshake failures. An approved client passing with the same CA and guest significantly strengthens the check, but the server's specific X.509 error can be diagnosed separately.
- The disk and CA are disposable; successful testing does not deliver or renew certificates on deployed devices.
- The server's security depends on its clock, OpenSSL configuration, trusted CA and CRL freshness. Real device deployment needs secure time, provisioning, rotation and compromise recovery.
- QEMU does not simulate electrical power loss, flash wear or secure hardware key storage.
