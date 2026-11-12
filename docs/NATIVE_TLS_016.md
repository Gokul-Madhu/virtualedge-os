# v0.16 — Live native TLS guest acceptance

v0.15 added the C/OpenSSL mTLS guest gateway. Host TLS tests alone cannot establish
whether the ARM64 binary links, starts under Buildroot, accepts a QEMU forwarded
connection, and actually serves readiness. v0.16 adds that acceptance path.

## Acceptance sequence (Ubuntu WSL)

Do not run a second QEMU on the same forwarded port. First run the standard build
and serial QEMU self-test, then run the native HTTPS smoke test:

```bash
cd ~/dev/virtualedge-os
python3 tests/test-native-tls.py
./scripts/build-and-test.sh --qemu
python3 scripts/test-qemu-native-tls.py --credentials "$HOME/.virtualedge/tls-native-dev"
```

The HTTPS check is intentionally a **separate opt-in** command because it requires a
TLS-enabled image containing development-only server credentials. It copies rootfs.ext4
into a temporary directory, boots QEMU from that copy, and terminates the guest even
when the test fails. It uses port 18444 by default. Specify `--port 18445` if needed.
A successful result proves client-certificate mTLS and `/ready` work in a real guest.
The anonymous-client probe must not receive an HTTP 200 response.

## Guest server time validation

The C server refuses to start if the certificate's NotBefore/NotAfter does not
contain the guest clock time. QEMU must have a trustworthy date before the service
starts; this release does not establish a secure clock. Certificate chain validation
uses the normal OpenSSL checks, including time checks, for connecting clients.

## What this does **not** certify

The test does not cover long-duration reliability, field certificates, revocation,
secure time bootstrap, rate limiting, secure private-key storage, physical ARM boards,
or production secure boot/OTA. The test does not use or modify your A/B slot state.
