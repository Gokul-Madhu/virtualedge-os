# v0.17 — Development TLS credential preflight

Native TLS in v0.15/v0.16 can use disposable CA, server and client certificates.
Until v0.17, the staging command checked only the presence of three files.
It could inadvertently embed an invalid, mismatched or insecure development key.

## Preflight

Generate **development-only** credentials outside the source repository:

```sh
python3 tools/virtualedge_tls_provision.py --output "$HOME/.virtualedge/tls-v017-dev"
python3 tools/virtualedge_tls_audit.py --credentials "$HOME/.virtualedge/tls-v017-dev"
python3 tools/virtualedge_tls_audit.py --credentials "$HOME/.virtualedge/tls-v017-dev" --json
```

The audit validates private directory/key permissions, checks for symlink keys,
checks CA signing constraints, server/client extended key usage, localhost and
127.0.0.1 subject alternative names, certificate dates, SHA-compatible public-key
matching, and the certificate chain. The tool warns by default when a certificate
has fewer than 14 days remaining. For deployment automation, a nonzero exit
status indicates an invalid credential set; warnings do not make it invalid.

The `scripts/stage-native-tls-dev-certs.sh` command now executes this audit
**before** copying a key into the Buildroot rootfs overlay. It will refuse
incomplete or mismatched development credential sets.

```sh
./scripts/stage-native-tls-dev-certs.sh "$HOME/.virtualedge/tls-v017-dev"
```

## Security model and limitations

- Do **not** publish an image containing the development `server.key`.
- Do **not** use the development CA in production. It includes a CA private
  key and is not a secure device-identity enrollment or rotation system.
- This is an **offline preflight**, not proof that a guest's clock is trustworthy,
  that a server cannot be compromised, or that firmware updates are safe.
- The staged rootfs private key remains in the OS disk image; v0.17 does not
  fix that production-key-storage limitation.
- The current native mTLS gateway remains read-only and has not been verified
  on this release in the user's WSL QEMU environment.
- For production work, private keys should be uniquely provisioned per device
  outside a shared firmware image, secured with a hardware-backed keystore
  where possible, and coupled to certificate renewal and revocation.

Run `python3 tests/test-tls-audit.py` for isolated credential-audit tests,
`python3 tests/test-native-tls.py` for C gateway host tests, and
`./scripts/build-and-test.sh --qemu` for the ARM64 guest build/acceptance.
