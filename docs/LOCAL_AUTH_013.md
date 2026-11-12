# v0.13: Opt-in local HTTP authentication (NOT TLS)

The VirtualEdge web server now supports an optional HTTP Basic challenge for **all**
HTTP routes (dashboard, health, readiness, telemetry, diagnostics, config, metrics,
events). Missing, incorrect, duplicate credentials return HTTP 401 and a
`WWW-Authenticate` header. An explicit `VE_AUTH_FILE` setting combined with a
missing, malformed or group/world-accessible credential file prevents startup.

**Scope:** HTTP Basic sends credentials in reversible Base64. It is **not HTTPS**,
not suitable for an untrusted network, and not protection against eavesdropping.
Do not forward or expose this service publicly. The safe default stays guest
loopback-only. Use localhost-limited QEMU forwarding for local development; for
real remote devices, first add authenticated TLS termination, provisioning,
secret storage, rate limits, and access controls.

## Provision inside an interactive development guest

Run as root:

```sh
virtualedge-auth-setup
sync
reboot
```

Save the displayed random password securely. Browser visits to `/dashboard`
will ask for username `virtualedge` and that password. The provisioner sets
`VE_AUTH_FILE=/etc/virtualedge/http-basic.auth` in `/etc/default/virtualedge-api`
and saves the Base64 credential with mode `0600`.

For command-line testing from the Windows or WSL host:

```sh
curl --user 'virtualedge:YOUR_PASSWORD' http://127.0.0.1:18080/health
```

**Important caveat:** the unmodified `virtualedge-selftest` and QEMU automated
acceptance harness use anonymous requests and therefore expect authentication
**disabled**. Use the default unprovisioned guest for automated release tests;
manual authenticated access is a separate opt-in test. The generated credentials
are stored on the guest root filesystem unless a secure, persistent credential
volume is designed; rebuilding/reflashing the rootfs may erase them.

The credential file is not a hash. Restrict permissions and filesystem access.
There is no user-role system, lockout or rate limiter in this release. The
service should not be deployed beyond a controlled laboratory environment.

## Verification and troubleshooting

- Without provisioning, `/health` and `/dashboard` still work as before.
- With provisioning enabled and a reboot, anonymous requests receive `401`.
- A valid Basic Authorization header receives normal responses.
- A file permission change to `0644` causes daemon startup to fail.
- Deleting the file **without removing** `VE_AUTH_FILE` causes startup to fail.
- Removing auth intentionally requires removing the explicit `VE_AUTH_FILE`
  setting from `/etc/default/virtualedge-api` and restarting the service.

Host tests: `python3 tests/test-auth.py`.
