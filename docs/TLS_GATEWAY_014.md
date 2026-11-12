# v0.14 — Local development mutual TLS gateway

**Scope:** The TLS gateway runs on the Ubuntu WSL **host**, not in the VirtualEdge
ARM64 guest. It is a laboratory security boundary, not a network deployment.
The QEMU upstream remains plaintext and is restricted to `127.0.0.1:18080`.
Mutual TLS ensures an HTTPS client must present a certificate signed by the
local development CA. The gateway is **read only** and restricts routes to
existing VirtualEdge monitoring endpoints. It forwards HTTP Basic auth only if
explicitly started with `--forward-basic`.

## Prerequisites

Python 3 and OpenSSL 3 on Ubuntu WSL. Boot the QEMU guest with the existing
loopback-only 18080 forwarding configured, and verify:

```sh
curl --noproxy '*' -i http://127.0.0.1:18080/health
```

If using the persistent QEMU launcher, enable forwarding with:

```sh
VE_FORWARD_DASHBOARD=1 ./scripts/run-qemu-persistent.sh
```

The guest must listen on its network interface when QEMU forwarding is enabled
(`VE_LISTEN_ANY=1` in its local development settings). Do not bind the QEMU
host forwarding endpoint to an externally reachable interface.

## Generate LOCAL credentials (once)

```sh
cd ~/dev/virtualedge-os
python3 tools/virtualedge_tls_provision.py --output "$HOME/.virtualedge/tls-dev"
```

The tool refuses to overwrite existing certificates. Keep the CA private key
(`ca.key`) and client private key (`client.key`) secret and outside source
control. Server and client certificates are intentionally short-lived (30
calendar days), and CA expires after 90 days. To rotate in development,
create an entirely new private directory and deliberately distribute the new
CA and client credentials. No private keys are included in the release archive.

## Start the gateway in a SEPARATE WSL terminal

```sh
cd ~/dev/virtualedge-os
python3 tools/virtualedge_tls_gateway.py \
  --credentials "$HOME/.virtualedge/tls-dev" \
  --port 18443 --upstream-port 18080
```

Test with a **client certificate** from WSL:

```sh
curl --noproxy '*' --cacert "$HOME/.virtualedge/tls-dev/ca.pem" \
  --cert "$HOME/.virtualedge/tls-dev/client.pem" \
  --key "$HOME/.virtualedge/tls-dev/client.key" \
  https://localhost:18443/ready
```

Without the client certificate, the TLS handshake should fail:

```sh
curl --noproxy '*' --cacert "$HOME/.virtualedge/tls-dev/ca.pem" \
  https://localhost:18443/ready
```

### Browser access

A browser needs to trust the generated **development CA** and import a client
certificate with its private key. Do not import a development CA into your
system-wide trusted-root store unless you understand the consequences. You can
instead use the `curl` workflow above. If using a browser, create a password-
protected PKCS#12 bundle for the browser's *personal certificate* store:

```sh
openssl pkcs12 -export \
  -inkey "$HOME/.virtualedge/tls-dev/client.key" \
  -in "$HOME/.virtualedge/tls-dev/client.pem" \
  -certfile "$HOME/.virtualedge/tls-dev/ca.pem" \
  -out "$HOME/.virtualedge/tls-dev/browser-client.p12"
```

Import only if you trust the device where the browser runs. TLS server name
validation still requires the development CA trust configuration. Alternatively,
keep using the original localhost HTTP dashboard for development.

## Known limitations

- Host-side TLS, **not** an in-guest TLS server or a production ingress.
- Plaintext QEMU upstream remains reachable locally; no protection against
  other programs/users who can access that same host loopback endpoint.
- No authentication roles, auditable user identities, enrollment, revocation,
  session management, rate limiting or device certificate lifecycle.
- No remote exposure, secure boot, hardware credentials or industrial
  qualification. Never forward this listener publicly as a production service.
- Verification performed using a stub API and host OpenSSL/Python; actual WSL
  to QEMU secure-path acceptance remains pending.

Run `python3 tests/test-tls-gateway.py` to test TLS enforcement, route
allowlisting, prohibited methods, key permissions and certificate provisioning.
