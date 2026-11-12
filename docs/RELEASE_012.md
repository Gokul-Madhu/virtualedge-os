# VirtualEdge OS v0.12 — Health-gated update acceptance

## New features

- `GET /health`: **liveness only**, returns HTTP 200 when the API can respond. This is intentionally not a sensor/device readiness check.
- `GET /ready`: HTTP 200 `status=ready` only when configuration is valid and sensor acquisition is valid; otherwise HTTP 503 `status=not_ready` with explicit `config_valid`, `sensor_acquisition_valid`, and diagnostic bitmask.
- `GET /api/v1/metrics`: small read-only JSON operational summary including uptime, available memory, load, fault mask, config validity, readiness, and in-session diagnostic transition count.
- Guest `virtualedge-selftest` now checks `/ready` and `/api/v1/metrics`. Therefore host-side QEMU A/B acceptance using that selftest will reject an unhealthy candidate image (when the affected checks manifest during its boot).
- Targeted tests cover malformed physical thermal data, recovery, invalid config reload, recovery, and simulated threshold warning semantics.

## Semantics and safety

`/ready` is *not* a comprehensive system integrity attestation. It verifies only in-process configuration validation and input health. Temperature acquisition in QEMU defaults to simulated data. A `503` does not mean the process is dead: the `/health` liveness endpoint can still answer. A normal simulated threshold alert is exposed through diagnostics but does not independently block readiness.

No authentication or TLS is added. The API remains local-only by default. `VE_LISTEN_ANY=1` must only be used in an isolated QEMU/NAT development environment with localhost-only host forwarding. This release is not a production security or OTA solution.

## Upgrade

Back up `board services configs scripts tests docs tools`, power off QEMU, extract this archive over the project, and run:

```bash
cd ~/dev/virtualedge-os
./scripts/test-host.sh
./scripts/build-and-test.sh --qemu
```

If a previous host test is still running, wait for it to finish before starting another. Do not reuse the previous rootfs image during a Buildroot rebuild.

## Quick guest check

```sh
virtualedge-selftest
wget -q -O - http://127.0.0.1:8080/ready; echo
wget -q -O - http://127.0.0.1:8080/api/v1/metrics; echo
```

For WSL/Windows: the optional browser dashboard remains accessible using your existing QEMU forwarding on port 18080; no networking change is needed for this update.

## Verification record

- Strict native GCC compilation: PASS.
- New readiness/recovery host tests: PASS.
- Existing host tests through signed offline release and persistence: PASS in this environment.
- Full aggregated host run: interrupted while running A/B slot tests due to execution time limits. Existing A/B tests were verified previously for v0.11, **not rerun to completion on v0.12**.
- v0.12 ARM64 compilation and actual QEMU acceptance: NOT RUN here; must run in user's WSL.
- Physical board, secure boot, OTA install, power-loss and industrial endurance qualification: NOT VERIFIED.
