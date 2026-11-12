# VirtualEdge v0.20 — Development identity rotation and CRL freshness

Scope: **host-side development credentials only**. Not cloud enrollment, automated renewal, hardware-backed key storage, dynamic CRL push, or certified OTA.

## Rotate a client identity

Use a NEW identity name for each replacement. Never reuse or overwrite an existing private key.

```bash
cd ~/dev/virtualedge-os
CA="$HOME/.virtualedge/tls-v019-dev"
python3 tools/virtualedge_identity.py --ca "$CA" rotate sensor-test-01 sensor-test-02
```

The command validates the old identity, issues a fresh P-256 private key and clientAuth certificate, verifies the new cert against the development CA and current CRL, then revokes the old certificate and regenerates the signed CRL. If issuance or verification fails, the old identity remains valid. If CRL publication fails after revocation, inspect the local CA database before trying again; recovery is **not automatic**.

**Deployment caveat:** This is an operator-driven rotation. It does not transport the new private key to the client or update live QEMU trust. It can cause downtime if the updated CRL is deployed before the replacement credentials reach the client. Securely distribute the new client identity and coordinate CRL deployment before retiring the previous one. The CA private key must stay on the host.

## Rebuild the development credential disk

```bash
mkdir -p out/persistent
python3 tools/virtualedge_tls_image.py \
    --credentials "$CA" \
    --output out/persistent/virtualedge-tls-rotated.ext4
```

The image builder refuses an expired or not-yet-valid signed CRL; a CRL generated with `default_crl_days = 7` must be refreshed before its nextUpdate. Never delete a live credential disk while QEMU is using it. Shut down QEMU and carefully install the newly built disk through the development launcher; avoid overwriting the old file until the new disk has been tested. Exact QEMU disk path and migration are covered in `docs/TLS_DISK_018.md` and `docs/DEVICE_IDENTITY_019.md`.

**Security warning:** The disk contains an unencrypted server private key and is not suitable for production. A QEMU boot/mount/revocation acceptance test on WSL is still required. Real hardware needs secure per-device provisioning, CRL distribution, certificate rollover policy and recovery testing.

## Host tests

```bash
python3 tests/test-identity-rotation.py
python3 tests/test-device-identity.py
python3 tests/test-tls-disk.py
python3 tests/test-native-tls.py
```
