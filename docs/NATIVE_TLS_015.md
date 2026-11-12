# v0.15 — native guest mTLS (development mode)

This release adds a **native C/OpenSSL TLS server** inside the ARM64 Linux guest
on TCP port **8443**, forwarding only allowlisted GET requests to the local
C API at `127.0.0.1:8080`. Mutual TLS with a trusted client certificate is
mandatory. The service starts **disabled** and source does not contain keys.

## WSL build and QEMU smoke test

Run **from Ubuntu WSL**. Stop QEMU first.

```bash
cd ~/dev/virtualedge-os
./scripts/enable-native-tls.sh
python3 tests/test-native-tls.py
python3 tools/virtualedge_tls_provision.py --output "$HOME/.virtualedge/tls-native-dev"
# Explicitly opt-in to putting disposable credentials in the QEMU image:
./scripts/stage-native-tls-dev-certs.sh "$HOME/.virtualedge/tls-native-dev"
./scripts/build-and-test.sh --qemu
```

**Important:** The staging script copies `server.key` into the rootfs overlay,
thus the resulting root filesystem image contains the server's private key.
That is **not secure key provisioning**, and the image must **never** be shared
as a production firmware or published to GitHub. `.gitignore` protects source
control but not archives made with `tar` or copies of your image. Do not use
real device credentials for this development exercise. For a deployable
solution, keys must be provisioned separately into protected device storage.

Launch the updated guest with **TLS-only port forwarding** (rather than
running the original `start-qemu.sh`):

```bash
./scripts/run-qemu-native-tls.sh
```

This temporary launcher exposes only `127.0.0.1:18444 -> guest:8443` and does
not forward the unauthenticated HTTP port 8080. It does not modify the
Buildroot-generated launcher.

With guest `VE_TLS_LISTEN_ANY=1` (set by the staging script), you can test from
WSL while QEMU runs in another WSL terminal:

```bash
curl --noproxy '*' \
  --cacert "$HOME/.virtualedge/tls-native-dev/ca.pem" \
  --cert "$HOME/.virtualedge/tls-native-dev/client.pem" \
  --key "$HOME/.virtualedge/tls-native-dev/client.key" \
  https://localhost:18444/ready
```

To confirm client authentication is enforced, repeat without `--cert` and
`--key`; the request must fail.

Check **port 18080 remains unforwarded** in any security evaluation. If the
plaintext HTTP port remains forwarded, users on the host can bypass TLS by
accessing `http://127.0.0.1:18080/dashboard` directly. The API remains
available on `127.0.0.1:8080` inside QEMU; use guest loopback only.

If you previously enabled HTTP Basic authentication, the new mTLS proxy does
not forward the `Authorization` header. Disable HTTP Basic for this isolated
mTLS test, or use the previous host gateway's `--forward-basic` option.

## Limits and next work

- The new C server is single-threaded and serves one HTTPS client at a time.
- The HTTP parser caps headers at 8 KiB; supported routes are read-only.
- Response forwarding is bounded to 1 MiB but does not enforce upstream
  response Content-Length or provide full reverse-proxy hardening.
- The guest does not manage renewals, revocation, time synchronization or
  encrypted private-key storage.
- No hardware secure boot, unattended certificate enrollment, production
  OTA installation, or power-loss qualification is implemented.
- Cross-build and live guest TLS still require WSL verification.

For development tests, the gateway logs accepted connections to stderr but
has no audit-grade structured security log. It does not replace a mature,
reviewed web server for a production fleet.
