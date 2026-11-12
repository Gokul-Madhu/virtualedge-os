# VirtualEdge OS v0.7 — local device management

## Trust boundary

The network API remains **read-only**. It does not expose settings mutation, remote command execution, or shell operations. By default, it binds to guest `127.0.0.1:8080`. For controlled QEMU demonstrations only, `/etc/default/virtualedge-api` can enable `VE_LISTEN_ANY=1`; use localhost-only QEMU `hostfwd` and an isolated, trusted development system. No TLS, authentication or production-grade remote access is claimed.

## Read-only endpoints

- `GET /api/v1/device`: hostname, target architecture, API version, sensor mode, and `control_api_enabled:false`.
- `GET /api/v1/config`: validated active threshold values, validity flag, and revision counter.
- Existing `/dashboard`, `/health`, `/api/v1/telemetry`, `/api/v1/diagnostics`, `/api/v1/events` remain available.

The UI's system information panel shows the hostname, revision, and whether the active configuration is valid.

## Changing diagnostics thresholds inside QEMU

Log in to the **guest** as root and run:

```sh
virtualedge-config show
virtualedge-config validate
virtualedge-config set max_temperature_c 32.5
# Reload the running C daemon without restarting its supervisor
killall -HUP virtualedge-api
wget -q -O - http://127.0.0.1:8080/api/v1/config
```

Supported settings:

| Key | Allowed range | Default |
|---|---:|---:|
| max_temperature_c | -50 to 150 | 35 |
| max_vibration_g | 0 to 20 | 0.30 |
| min_voltage_v | 0 to 24 | 3.00 |

`virtualedge-config` performs strict numeric validation, refuses unrecognized keys, retains other values, writes a same-directory temporary file, flushes it to disk and atomically renames it over `diagnostics.conf`. It is intended for privileged local use, not remote execution. On SIGHUP, the service parses the entire file and only commits a fully valid configuration; malformed updates preserve the last valid threshold set and set `config_valid:false`.

To reset to defaults, set the three values back to 35, 0.3 and 3 and send another SIGHUP.

### Persistence caveat

The QEMU guest uses a writable ext4 root filesystem; updates can survive reboot **of that same disk image**. Buildroot image regeneration replaces the root filesystem from the overlay and can restore packaged defaults. For production deployments, configuration should live on a separately managed persistent partition with an explicit migration and recovery policy.

### Security caveat

These features do **not** provide TLS, user authentication, audited RBAC, secure provisioning, secure OTA, physical sensor compatibility, secure boot, safety certifications or an industrial deployment guarantee. They form a local management foundation only.
