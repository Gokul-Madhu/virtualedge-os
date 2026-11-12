# VirtualEdge v0.26 — native signed-image preflight

## Scope

`virtualedge-update-verify` is a **C/OpenSSL tool** intended to run in the ARM64 guest. It checks the exact Ed25519 signature over the canonical release manifest and streams SHA-256 over the image. It additionally enforces board identity, a minimum release version, size limits, and rejects symlink input for manifest/signature/image.

**It does not install to a block device, update the bootloader, commit A/B metadata, download an update, unpack archives, manage trust anchors, or guarantee crash safety.** The host-managed QEMU A/B workflow remains independent.

## Build

Enable OpenSSL in Buildroot, then rebuild:

```bash
./scripts/enable-native-tls.sh
./scripts/build-and-test.sh --qemu
```

The tool is only compiled when `BR2_PACKAGE_LIBOPENSSL=y`. Native TLS is bundled in the same opt-in build path. The tool needs `libcrypto` at runtime.

## Development test with host compiler

```bash
python3 tests/test-guest-update-verify.py
```

For a guest test, use a **disposable** release bundle and a **trusted public key already provisioned** on the guest. The format from `tools/virtualedge_release.py pack` is an uncompressed tar with `manifest.json`, `manifest.sig`, and `image.bin`. Extract it only to a controlled local directory; the native verifier accepts these three individual regular files, NOT a tar path.

Inside the guest (after transferring the extracted files and public key into guest storage):

```sh
virtualedge-update-verify \
  /tmp/update/manifest.json \
  /tmp/update/manifest.sig \
  /tmp/update/image.bin \
  /etc/virtualedge/release-trust.pub.pem \
  qemu-aarch64 0.25.0
```

An accepted result states `NO installation performed`. All errors are nonzero and fail closed.

### Security boundaries

- The trusted public key must be installed by a trusted provisioning process, not accepted from the same untrusted update transport.
- This tool does not create an immutable trust root or store a monotonic anti-rollback counter. The `MIN_VERSION` input must come from independent trusted device state; taking it from the update itself defeats rollback protection.
- Verification and any future installation must consume **the exact same verified bytes**; do not verify a file then reopen a mutable source for installation.
- Image verification is not secure boot: the kernel and bootloader are not verified by this utility.
- Never test installing to `/dev/vda`, `/dev/vdb`, or any real device using this version. No block writes are implemented.
