#!/usr/bin/env bash
set -euo pipefail

PROJECT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILDROOT="${BUILDROOT_DIR:-$HOME/tools/buildroot-2026.08.1}"
OUTPUT="$PROJECT/out/buildroot"
OVERLAY="$PROJECT/board/virtualedge/rootfs-overlay"

# Buildroot rejects Windows PATH entries with whitespace under WSL.
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
cd "$PROJECT"

echo '=== 1/4 Host compiler checks ==='
./scripts/test-host.sh

# NEVER embed private keys or TLS credentials in the firmware root filesystem.
# Legacy v0.15-v0.17 staging must be removed before this build can proceed.
if [[ -d "$OVERLAY/etc/virtualedge/tls" ]]; then
    echo 'SECURITY ERROR: Legacy firmware-embedded TLS credential directory detected.' >&2
    echo 'Remove board/virtualedge/rootfs-overlay/etc/virtualedge/tls and use v0.18 separate TLS disk.' >&2
    exit 1
fi
if find "$OVERLAY" -type f \( -name '*.key' -o -name '*private*.pem' \) -print -quit | grep -q .; then
    echo 'SECURITY ERROR: private-key-like file detected in firmware overlay.' >&2
    exit 1
fi
# Defense-in-depth: refuse stale credentials in already-built images. An older
# Buildroot target may retain files that were removed from the overlay.
if [[ -d "$OUTPUT/target/etc/virtualedge/tls" ]]; then
    echo 'SECURITY ERROR: obsolete TLS secrets exist in Buildroot target.' >&2
    echo 'Remove out/buildroot/target/etc/virtualedge/tls, rebuild rootfs, and inspect the generated image.' >&2
    exit 1
fi
echo '=== 2/4 Verify Buildroot environment ==='
test -f "$OUTPUT/.config" || { echo 'Missing Buildroot .config (run the original setup first)' >&2; exit 1; }
test -f "$BUILDROOT/Makefile" || { echo "Buildroot source not found: $BUILDROOT" >&2; exit 1; }
CC="$OUTPUT/host/bin/aarch64-buildroot-linux-gnu-gcc"
test -x "$CC" || { echo "Cross compiler not found: $CC" >&2; exit 1; }

# Warn if exported source was unpacked somewhere other than the existing overlay path.
if ! grep -Fq "BR2_ROOTFS_OVERLAY=\"$OVERLAY\"" "$OUTPUT/.config"; then
    echo 'WARNING: Buildroot overlay path does not match this project directory.' >&2
    echo "Expected: $OVERLAY" >&2
    echo 'Check .config or configure the overlay before building.' >&2
    exit 1
fi

echo '=== 3/4 Cross-compile native ARM64 API ==='
# Optional opt-in for Linux kernel thermal sysfs. Example:
# VE_TEMPERATURE_SYSFS_PATH=/sys/class/thermal/thermal_zone0/temp ./scripts/build-and-test.sh
EXTRA_CFLAGS=()
if [[ -n "${VE_TEMPERATURE_SYSFS_PATH:-}" ]]; then
    if [[ ! "$VE_TEMPERATURE_SYSFS_PATH" =~ ^/sys/class/thermal/thermal_zone[0-9]+/temp$ ]]; then
        echo 'Invalid VE_TEMPERATURE_SYSFS_PATH; expected /sys/class/thermal/thermal_zoneN/temp' >&2
        exit 2
    fi
    EXTRA_CFLAGS+=("-DVE_TEMPERATURE_SYSFS=\"$VE_TEMPERATURE_SYSFS_PATH\"")
    echo "Enabling Linux thermal-zone input: $VE_TEMPERATURE_SYSFS_PATH"
fi
"$CC" -std=c11 -O2 -Wall -Wextra -Werror "${EXTRA_CFLAGS[@]}" \
    "$PROJECT/services/telemetry/virtualedge-api.c" \
    -o "$OVERLAY/usr/bin/virtualedge-api"
"$CC" -std=c11 -O2 -Wall -Wextra -Werror \
    "$PROJECT/services/telemetry/virtualedge-config.c" \
    -o "$OVERLAY/usr/bin/virtualedge-config"
chmod 755 "$OVERLAY/usr/bin/virtualedge-config"
chmod 755 "$OVERLAY/usr/bin/virtualedge-api"
file "$OVERLAY/usr/bin/virtualedge-api"

echo '=== 4/4 Rebuild Buildroot image ==='
make -C "$BUILDROOT" O="$OUTPUT" -j"$(nproc)"
test -s "$OUTPUT/images/Image"
test -e "$OUTPUT/images/rootfs.ext4"
# v0.15: opt-in cross-build of the native OpenSSL mTLS server.
# Buildroot must populate the OpenSSL sysroot before compiling the service.
if grep -qx 'BR2_PACKAGE_LIBOPENSSL=y' "$OUTPUT/.config"; then
    echo '=== Cross-compile native ARM64 mTLS service ==='
    "$CC" -std=c11 -O2 -Wall -Wextra -Werror \
        "$PROJECT/services/telemetry/virtualedge-tls.c" \
        -o "$OVERLAY/usr/bin/virtualedge-tls" -lssl -lcrypto
    chmod 755 "$OVERLAY/usr/bin/virtualedge-tls"
    echo '=== Cross-compile native ARM64 signed-image preflight ==='
    "$CC" -std=c11 -O2 -Wall -Wextra -Werror \
        "$PROJECT/services/telemetry/virtualedge-update-verify.c" \
        -o "$OVERLAY/usr/bin/virtualedge-update-verify" -lcrypto
    chmod 755 "$OVERLAY/usr/bin/virtualedge-update-verify"
    echo '=== Cross-compile native ARM64 verified FILE staging utility ==='
    "$CC" -std=c11 -O2 -Wall -Wextra -Werror \
        "$PROJECT/services/telemetry/virtualedge-update-stage.c" \
        -o "$OVERLAY/usr/bin/virtualedge-update-stage"
    chmod 755 "$OVERLAY/usr/bin/virtualedge-update-stage"
    echo '=== Cross-compile native ARM64 regular-file update installer ==='
    "$CC" -std=c11 -O2 -Wall -Wextra -Werror \
        "$PROJECT/services/telemetry/virtualedge-update-install-file.c" \
        -o "$OVERLAY/usr/bin/virtualedge-update-install-file"
    chmod 755 "$OVERLAY/usr/bin/virtualedge-update-install-file"
    make -C "$BUILDROOT" O="$OUTPUT" -j"$(nproc)"
else
    rm -f "$OVERLAY/usr/bin/virtualedge-tls" "$OVERLAY/usr/bin/virtualedge-update-verify" "$OVERLAY/usr/bin/virtualedge-update-stage" "$OVERLAY/usr/bin/virtualedge-update-install-file"
    echo 'Native TLS disabled. Run ./scripts/enable-native-tls.sh to enable it.'
fi
echo 'SUCCESS: Host tests passed and ARM64 images generated.'
echo 'NEXT: Run python3 scripts/test-qemu.py for automated QEMU boot acceptance.'
echo 'NATIVE TLS: python3 scripts/test-qemu-native-tls.py --credentials "$HOME/.virtualedge/tls-native-dev" (requires staged credentials)'
if [[ "${1:-}" == "--qemu" ]]; then
    echo '=== Automated QEMU acceptance ==='
    python3 "$PROJECT/scripts/test-qemu.py"
elif [[ $# -gt 0 ]]; then
    echo 'Usage: ./scripts/build-and-test.sh [--qemu]' >&2
    exit 2
fi
