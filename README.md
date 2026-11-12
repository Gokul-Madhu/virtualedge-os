# VirtualEdge OS

VirtualEdge OS is a Buildroot-based ARM64 Linux system for edge device monitoring and recovery. It boots to a console and serves a local dashboard with Linux system metrics, sensor readings, and diagnostic events. The QEMU build uses simulated temperature, vibration, and voltage alongside measured guest metrics.

## What has been verified

- Clean ARM64 build and QEMU boot with guest service, API, and dashboard self-tests.
- Dashboard and telemetry over localhost, with a separate data disk that survives reboot.
- Signed image verification, candidate confirmation, and fallback after two unconfirmed boots using the QEMU A/B test runner.
- Native mutual TLS with development certificates, including certificate rotation and revocation in QEMU.
- EmbeddedX Android LAN Monitor reading temperature and vibration over USB.

The verified target is QEMU virt. Physical Raspberry Pi support, accelerometer integration, hardware secure boot, and power-loss recovery are future work. The QEMU A/B workflow manages its slots from the host.

## Build and run

Use Ubuntu or Ubuntu WSL with Buildroot 2026.08.1, its [host prerequisites](https://buildroot.org/downloads/manual/manual.html#requirement), Python 3, OpenSSL, e2fsprogs, curl, and qemu-system-aarch64. Keep the project on the Linux filesystem.

From the repository root:

```bash
buildroot="${BUILDROOT_DIR:-$HOME/tools/buildroot-2026.08.1}"
mkdir -p out
sed "s|^BR2_ROOTFS_OVERLAY=.*|BR2_ROOTFS_OVERLAY=\"$PWD/board/virtualedge/rootfs-overlay\"|" \
  configs/virtualedge_defconfig > out/virtualedge-local-defconfig
make -C "$buildroot" O="$PWD/out/buildroot" BR2_DEFCONFIG="$PWD/out/virtualedge-local-defconfig" defconfig
make -C "$buildroot" O="$PWD/out/buildroot" toolchain
BUILDROOT_DIR="$buildroot" bash scripts/build-and-test.sh --qemu
bash scripts/run-qemu-dashboard.sh
```

Open [the local dashboard](http://127.0.0.1:18080/dashboard). Run the host checks independently with `bash scripts/test-host.sh`. The launch script keeps data in `out/persistent` and uses a temporary root filesystem for each boot.

## Documentation

- [Dashboard and telemetry](docs/DASHBOARD.md)
- [Persistent storage](docs/PERSISTENT_DATA.md)
- [Signed releases](docs/SIGNED_RELEASES.md)
- [Five-boot QEMU acceptance](docs/QEMU_BASELINE_SMOKE_036.md)
- [EmbeddedX Android USB demo](docs/EMBEDDEDX.md)
- [Physical hardware roadmap](docs/HARDWARE_SECUREBOOT_POWERLOSS_PLAN_034.md)
- [Release history](docs/RELEASE_HISTORY.md)
