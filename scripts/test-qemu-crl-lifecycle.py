#!/usr/bin/env python3
"""Exercise CRL rotation with two real QEMU ARM64 boots and temporary TLS disks.

Requires a previously built native-TLS ARM64 image, QEMU and mkfs.ext4.
All CA keys and generated credential disks are disposable and live in /tmp.
The guest disks supplied to QEMU are mounted read-only where appropriate.
"""
import argparse
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / 'tools'
SCRIPTS = ROOT / 'scripts'


def execute(*args):
    subprocess.run([str(arg) for arg in args], check=True)


def client(ca: Path, name: str):
    base = ca / 'clients' / name
    return (base / 'client.pem', base / 'client.key')


def lifecycle(timeout=180, port=18444):
    # Keep credentials off the rootfs overlay and out of the repository.
    with tempfile.TemporaryDirectory(prefix='ve22-qemu-crl-') as tmp:
        base = Path(tmp)
        ca = base / 'ca'
        before = base / 'before.ext4'
        after = base / 'after.ext4'
        provision = TOOLS / 'virtualedge_tls_provision.py'
        identity = TOOLS / 'virtualedge_identity.py'
        image = TOOLS / 'virtualedge_tls_image.py'
        qemu = SCRIPTS / 'test-qemu-native-tls.py'

        execute(sys.executable, provision, '--output', ca)
        execute(sys.executable, identity, '--ca', ca, 'init')
        execute(sys.executable, identity, '--ca', ca, 'issue', 'alpha')
        execute(sys.executable, identity, '--ca', ca, 'issue', 'bravo')
        execute(sys.executable, image, '--credentials', ca, '--output', before)
        print('=== QEMU boot 1: alpha and bravo authorized ===', flush=True)
        execute(sys.executable, qemu, '--credentials', ca, '--tls-image', before,
                '--timeout', timeout, '--port', port,
                '--approved', *client(ca, 'alpha'), '--approved', *client(ca, 'bravo'))

        # Credential disk before rotation stays intact, so the second boot
        # tests a new signed CRL rather than a modified disk in place.
        execute(sys.executable, identity, '--ca', ca, 'rotate', 'alpha', 'charlie')
        execute(sys.executable, image, '--credentials', ca, '--output', after)
        print('=== QEMU boot 2: revoked alpha refused; bravo and charlie authorized ===', flush=True)
        execute(sys.executable, qemu, '--credentials', ca, '--tls-image', after,
                '--timeout', timeout, '--port', port,
                '--approved', *client(ca, 'bravo'), '--approved', *client(ca, 'charlie'),
                '--revoked', *client(ca, 'alpha'))
        print('PASS: Real ARM64 QEMU TLS CRL rotation and revocation lifecycle', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--timeout', type=int, default=180, help='Seconds allowed per QEMU boot')
    parser.add_argument('--port', type=int, default=18444)
    args = parser.parse_args()
    if not 10 <= args.timeout <= 1800 or not 1024 <= args.port <= 65535:
        parser.error('Invalid timeout or port')
    try:
        lifecycle(args.timeout, args.port)
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f'FAIL: {exc}\n')
