# VirtualEdge OS v0.32 — integrated QEMU release

This consolidated source release includes fixes confirmed or uncovered in the user's real ARM64 development environment:

1. QEMU serial-console CR handling for automated self-tests.
2. Correct QEMU virtio-mmio disk attachment ordering: data before root (and credentials before data before root for the TLS launcher).
3. Disposable rootfs copies in interactive persistent and A/B launchers so booting does not mutate the Buildroot signing source or hash-protected A/B images. **Persistent `/data` still persists across reboots.**
4. Signed release packaging dereferences Buildroot's `rootfs.ext4` symlink to include real image bytes, not a symlink tar entry.
5. New `scripts/run-qemu-dashboard.sh` to start QEMU, forward localhost:18080 -> guest:8080, wait for the health API, and open the browser on Windows.
6. QEMU-only `VE_LISTEN_ANY=1` defaults to allow the guest HTTP listener to accept host-forwarded connections. Host forwarding itself binds only 127.0.0.1. Do not expose the plain HTTP API to untrusted networks.

## Installation and verification

Stop QEMU first and **back up the source and out/ab and out/persistent**. Extract archive over existing `~/dev/virtualedge-os`. This source package excludes `out/`, keys, and private credentials.

```sh
cd ~/dev/virtualedge-os
python3 tests/test-release-integration.py
python3 tests/test-signed-release.py
./scripts/build-and-test.sh --qemu
./scripts/run-qemu-dashboard.sh
```

After QEMU boots, Windows should open `http://127.0.0.1:18080/dashboard`. If browser launching is unavailable, open the same URL manually. The QEMU console is still interactive.

### OTA acceptance

The v0.33.0 bundle in the earlier test is a **development label** for the same 60 MiB rootfs, not a distinct application release. The A/B runner uses disposable copies of `out/ab` and `out/persistent/virtualedge-data.ext4`.

```sh
python3 tools/virtualedge_ab.py --state-dir out/ab audit
python3 scripts/test-qemu-ota.py --state-dir out/ab \
    --data-image out/persistent/virtualedge-data.ext4 \
    --bundle out/ota-demo/virtualedge-test-0.33.0.tar \
    --public-key "$HOME/virtualedge-private-keys/dev-ed25519.pub.pem" \
    --timeout 240 --scenario both \
    --report "$HOME/virtualedge-test-reports/ota-final-first-run.json"
```

Use a fresh report filename on every run. Never reset existing A/B metadata without inspecting/backing it up. Actual QEMU confirmation/fallback with this consolidated release still needs to be run on WSL.

### Trust key storage

`/etc/virtualedge` is bind-mounted from `/data/virtualedge/config` on the persistence guest. To provision `release-trust.pub.pem`, store the public key at `/data/virtualedge/config/release-trust.pub.pem`, not under `/data/etc/virtualedge`. Private signing keys must stay outside the firmware and version control.

### Scope and limitations

Host-tested code and prior QEMU guest API/self-test, persistence, and native regular-file OTA verification/staging/install steps have been demonstrated. This release has not been fully cross-built or QEMU-booted in the packaging environment. Actual physical partition OTA, immutable secure boot, live CRL distribution, factory provisioning, secure key storage and industrial endurance qualification are **not complete**. Buildroot and large output images are not part of the source archive.
