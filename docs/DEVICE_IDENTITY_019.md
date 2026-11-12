# v0.19 — Development client identity enrollment and revocation

The v0.19 tooling issues *unique client certificates* from the existing development CA and maintains an OpenSSL-backed enrollment database. The native C TLS service supports an optional **signed Certificate Revocation List (CRL)** via `VE_TLS_CRL_FILE`. If that file is configured but missing/invalid, TLS startup fails. A revoked client certificate is rejected during TLS verification; an unaffected client certificate continues to work.

**Important security boundary:** This is a development proof of concept. `ca.key` is held on the provisioning host and must never be placed on the QEMU credential disk or firmware image. Client keys are generated and kept on that same host for demonstration, not on securely provisioned hardware. The guest's TLS credential disk contains the server key and optional public CRL. CRL updates require rebuilding the disposable TLS disk and restarting the gateway. There is no online revocation, enrollment server, device-bound key, audit service, enrollment policy, trusted time setup, or automatic lifecycle management.

## Provision isolated client identities

Run in Ubuntu WSL after installing v0.19:

```bash
cd ~/dev/virtualedge-os
python3 tools/virtualedge_tls_provision.py --output "$HOME/.virtualedge/tls-v019-dev"
python3 tools/virtualedge_identity.py --ca "$HOME/.virtualedge/tls-v019-dev" init
python3 tools/virtualedge_identity.py --ca "$HOME/.virtualedge/tls-v019-dev" issue workshop-laptop
python3 tools/virtualedge_identity.py --ca "$HOME/.virtualedge/tls-v019-dev" issue sensor-test-01
```

The issued client certificates live under the CA folder's `clients/<identity>/`. Client private keys are mode 0600, and the whole provisioning directory must remain owner-only. **Do not upload this directory to GitHub, and do not use it with real production devices.**

## Rebuild disposable TLS disk

```bash
python3 tools/virtualedge_tls_audit.py --credentials "$HOME/.virtualedge/tls-v019-dev"
python3 tools/virtualedge_tls_image.py \
  --credentials "$HOME/.virtualedge/tls-v019-dev" \
  --output out/persistent/virtualedge-tls-v019.ext4
VE_TLS_IMAGE="$PWD/out/persistent/virtualedge-tls-v019.ext4" ./scripts/run-qemu-native-tls.sh
```

The optional CRL is copied from `client-revocations.pem` into the credential disk after cryptographic verification. At guest startup, `S97virtualedge-tls` sets `VE_TLS_CRL_FILE` if the CRL is present. The server loads and checks it. The original CA-trusted development client certificate remains valid until specifically revoked or expired.

From another WSL shell, test an individual enrolled client:

```bash
curl --noproxy '*' \
  --cacert "$HOME/.virtualedge/tls-v019-dev/ca.pem" \
  --cert "$HOME/.virtualedge/tls-v019-dev/clients/workshop-laptop/client.pem" \
  --key "$HOME/.virtualedge/tls-v019-dev/clients/workshop-laptop/client.key" \
  https://localhost:18444/ready
```

## Revoke one identity

```bash
python3 tools/virtualedge_identity.py --ca "$HOME/.virtualedge/tls-v019-dev" revoke workshop-laptop
```

**Critical:** Revocation does not take effect on a running guest until a fresh credential disk is created using `--output out/persistent/virtualedge-tls-v019-revoked.ext4`, QEMU is shut down, and restarted using `VE_TLS_IMAGE=... ./scripts/run-qemu-native-tls.sh`. The server loads the CRL only at process startup. The CRL is valid for seven days by default; regenerate it before expiration using `python3 tools/virtualedge_identity.py --ca ... crl`, then rebuild the disk and restart. Incorrect clock time can break certificate validation. This is intentionally a manual, offline revocation procedure.

## Test

```bash
python3 tests/test-device-identity.py
python3 tests/test-native-tls.py
python3 tests/test-tls-disk.py
./scripts/test-host.sh
```

Live WSL ARM64 boot and persistent-disk integration still require your verification. A production design needs protected per-device keys, provisioning approval, certificate renewal, revocation update distribution, trusted time, audit, and security assessment.
