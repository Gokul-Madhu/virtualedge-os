# VirtualEdge OS v0.9 — Optional QEMU Persistent Data Volume

## Scope

This milestone provides a separate **ext4 data disk** for a QEMU ARM64 guest. A boot-time init script mounts `/dev/vdb` at `/data` and bind-mounts its directories onto `/etc/virtualedge` and `/var/log/virtualedge` **before** the native API starts. Threshold configuration and event logs can therefore survive guest shutdowns and changes to the root filesystem image.

The standard single-disk QEMU launcher remains supported; without `/dev/vdb`, the boot script logs a message and retains the original rootfs behavior.

**This is not yet A/B rootfs switching, OTA, secure boot, or qualified power-failure safety.** Do not point the launcher at any physical disk or a production filesystem.

## Build on Ubuntu WSL

```bash
cd ~/dev/virtualedge-os
./scripts/test-host.sh
./scripts/build-and-test.sh --qemu
```

The `--qemu` test continues to verify the existing single-rootfs boot; the new persistence path must also be verified using the separate acceptance procedure below. Make sure QEMU is stopped before rebuilding.

## First persistent boot

```bash
cd ~/dev/virtualedge-os
# Install formatter if necessary: sudo apt-get install e2fsprogs
./scripts/run-qemu-persistent.sh
```

On first use, this creates `out/persistent/virtualedge-data.ext4` (64 MiB). Subsequent launches **reuse** it without formatting. Do not delete this file if you want your settings/logs to survive. The file is intentionally excluded from Git.

Inside the guest as root:

```sh
mount | grep -E '/data|/etc/virtualedge|/var/log/virtualedge'
virtualedge-config show
virtualedge-config set max_temperature_c 31.5
killall -HUP virtualedge-api
virtualedge-config show
wget -q -O - http://127.0.0.1:8080/api/v1/config; echo
sync
poweroff
```

Reopen with `./scripts/run-qemu-persistent.sh` and verify `virtualedge-config show` still reports `31.5`. Next simulate a diagnostic transition and check that `/var/log/virtualedge/events.log` persists after another normal reboot. Fault injection mode remains in `/run` and intentionally does **not** persist.

## Host dashboard forwarding (optional)

Only enable forwarding in a trusted local QEMU test configuration with the API explicitly listening on the guest network interface; this API is **unauthenticated**.

```bash
VE_FORWARD_DASHBOARD=1 ./scripts/run-qemu-persistent.sh
```

Access `http://127.0.0.1:18080/dashboard` from Windows if WSL localhost forwarding works. Do not forward the API from untrusted networks. If it fails, verify `/etc/default/virtualedge-api` enables the guest listener and check port 18080 is unused.

## Notes and limitations

- The data volume is **not encrypted**, and the QEMU sample uses root-owned services and files. No physical secure storage or key provisioning exists yet.
- `/etc/virtualedge` and `/var/log/virtualedge` are bind-mounted only if the data volume mounts successfully; a corrupt or missing data image is **never auto-formatted** by the guest.
- Test results from a host shell cannot prove bind-mount behavior; run the actual QEMU acceptance steps.
- Back up `out/persistent/virtualedge-data.ext4` only with the guest shut down (or using a filesystem-consistent snapshot).
- A/B system slots, on-device Ed25519 verification, rollback and real-hardware validation remain future work.
