#!/usr/bin/env bash
# Opt-in: install libopenssl into the existing ARM64 Buildroot output.
set -euo pipefail
PROJECT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILDROOT="${BUILDROOT_DIR:-$HOME/tools/buildroot-2026.08.1}"
CONFIG="$PROJECT/out/buildroot/.config"
test -f "$CONFIG" || { echo "Missing $CONFIG" >&2; exit 1; }
test -f "$BUILDROOT/Makefile" || { echo "Missing $BUILDROOT/Makefile" >&2;exit 1; }
cp -n "$CONFIG" "$CONFIG.before-native-tls" || true
python3 - "$CONFIG" <<'PY'
from pathlib import Path
import sys
p=Path(sys.argv[1])
s=p.read_text()
for symbol in ('BR2_PACKAGE_OPENSSL','BR2_PACKAGE_LIBOPENSSL'):
    import re
    s=re.sub(r'(?m)^# '+symbol+r' is not set\n','',s)
    s=re.sub(r'(?m)^'+symbol+r'=.*\n','',s)
    s+='\n'+symbol+'=y\n'
p.write_text(s)
PY
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
make -C "$BUILDROOT" O="$PROJECT/out/buildroot" olddefconfig
for symbol in BR2_PACKAGE_OPENSSL BR2_PACKAGE_LIBOPENSSL; do
    grep -qx "$symbol=y" "$CONFIG" || { echo "Buildroot rejected $symbol" >&2;exit 1; }
done
printf '%s\n' 'Enabled native TLS OpenSSL libraries in Buildroot .config.' 'Run ./scripts/build-and-test.sh --qemu to rebuild image.'
