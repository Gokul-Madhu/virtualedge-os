# VirtualEdge OS v0.21 — fail-closed revocation acceptance

This update closes a development TLS security gap: an enabled native mTLS guest may no longer silently start without a configured client certificate revocation list (CRL).

## Changes

- The guest startup service `S97virtualedge-tls` requires `client-revocations.pem` on the separate, read-only development credentials disk. If it is missing, native TLS does not start.
- The C OpenSSL gateway supports `VE_TLS_REQUIRE_CRL=1` as a mandatory CRL policy and exits if `VE_TLS_CRL_FILE` is not configured. It still rejects an unsafe/missing CRL file if configured.
- The credential disk builder rejects an identity-initialized CA missing its CRL, *before* producing a disk image. Existing certificate-chain and CRL freshness verification remain.
- New host integration tests cover absent CRLs, fail-closed startup, an actual old-certificate-to-new-certificate rotation, and rejected credential disk packaging.

## Migration from v0.20

**Breaking behavior by design:** v0.21's opt-in native TLS service will not start with a v0.18-style certificate disk that lacks the `client-revocations.pem` file. The basic localhost dashboard and HTTP API are unchanged. An absent CRL should be fixed at the development CA and the credential disk replaced, **not** by disabling the policy.

On Ubuntu WSL, before creating the credentials disk, initialize the CA's identity database if not already initialized:

```bash
cd ~/dev/virtualedge-os
CA="$HOME/.virtualedge/tls-v021-dev"
python3 tools/virtualedge_tls_provision.py --output "$CA"
python3 tools/virtualedge_identity.py --ca "$CA" init
python3 tools/virtualedge_identity.py --ca "$CA" issue operator-laptop
python3 tools/virtualedge_tls_audit.py --credentials "$CA"
mkdir -p out/persistent
python3 tools/virtualedge_tls_image.py --credentials "$CA" \
  --output out/persistent/virtualedge-tls-dev.ext4
```

`virtualedge_tls_image.py` refuses to overwrite an existing image. If the current image already exists, create a separately named image and only switch the QEMU launcher after safely shutting QEMU down. Do not delete a live credential image. Ensure the chosen launcher points to the newly created image; see `docs/TLS_DISK_018.md`.

For an already initialized identity CA, refresh a current signed CRL with:

```bash
python3 tools/virtualedge_identity.py --ca "$CA" crl
```

To test:

```bash
python3 tests/test-crl-enforcement.py
python3 tests/test-native-tls.py
python3 tests/test-device-identity.py
python3 tests/test-tls-disk.py
python3 tests/test-identity-rotation.py
./scripts/build-and-test.sh --qemu
python3 scripts/test-qemu-native-tls.py --credentials "$CA" --timeout 180
```

The QEMU acceptance command requires a functional ARM64 build and appropriate client certificate selection. The default probe uses the original `client.pem/client.key` generated during provisioning, not automatically the new per-client identity. Additional on-guest revocation validation is still required; host tests are not a substitute.

## Security limitations

- Keys and CRLs remain development-only; the TLS disk is **unencrypted**.
- CRLs are loaded at gateway startup, not pushed dynamically. Restart is required after CRL changes.
- A compromised development CA can issue other trusted certificates; trusted time, secure enrollment, recovery, hardware-backed keys and secure boot remain future tasks.
- If the CRL expires, TLS client authentication will fail; refresh and replace the credential disk before expiration.
