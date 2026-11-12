# Signed offline release workflow (v0.8)

This is the **host-side artifact authentication foundation** for future OTA.
It DOES NOT install images or enable A/B updates, safe rollback, secure boot,
or any network-facing update endpoint.

## Dependencies

Python 3 and `openssl` with Ed25519 support (OpenSSL 3 recommended).
Do not commit signing private keys, and use a separate secure host for production
signing. The `keygen` example is intended for local development only.

## Create development key (outside the repository)

```bash
mkdir -p "$HOME/virtualedge-private-keys"
python3 tools/virtualedge_release.py keygen \
  --private-key "$HOME/virtualedge-private-keys/dev-ed25519.pem" \
  --public-key "$HOME/virtualedge-private-keys/dev-ed25519.pub.pem"
```

## Sign an existing QEMU root filesystem image

Do this **after the ARM64 build succeeds and QEMU is shut down**.
The board ID `qemu-aarch64` is a label; do not use this image on Raspberry Pi hardware.

```bash
python3 tools/virtualedge_release.py pack \
  --image out/buildroot/images/rootfs.ext4 \
  --private-key "$HOME/virtualedge-private-keys/dev-ed25519.pem" \
  --board qemu-aarch64 --version 0.8.0 \
  --output "$HOME/virtualedge-v0.8.0-qemu-release.tar"
```

## Verify without modifying the installed OS

```bash
python3 tools/virtualedge_release.py verify \
  --bundle "$HOME/virtualedge-v0.8.0-qemu-release.tar" \
  --public-key "$HOME/virtualedge-private-keys/dev-ed25519.pub.pem" \
  --board qemu-aarch64 --min-version 0.7.0
```

The trust model requires a **trusted, independently distributed public key**.
Do not treat the public key packed by an untrusted updater as authoritative.
Version checks use a **caller-supplied minimum**; a future installer must keep
an anti-rollback counter in trustworthy persistent storage or equivalent
hardware. Version checks here do not provide a secure boot chain.

The tool deliberately refuses archive overwrite, tar links, unexpected members,
path traversal, invalid metadata, size mismatch and digest mismatch. It never
extracts archive entries to arbitrary paths during verification.

## Still required for true secure OTA

1. Board-specific boot chain and immutable trust anchor
2. Hardware-backed/securely provisioned signing public key and rollback policy
3. Independent inactive A/B rootfs slots with explicit state transitions
4. Crash-safe installation journal, fsync and integrity checking
5. Watchdog/boot-success confirmation and automatic rollback
6. Real power-cut, corruption, and network interruption test campaigns
7. Remote transport, authentication, TLS, safe provisioning and fleet management

Do **not** run the generated tar file as an installer or replace a live root
filesystem while the OS is running.
