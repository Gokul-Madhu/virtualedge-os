#!/usr/bin/env python3
"""Non-mutating preflight for the host-managed VirtualEdge QEMU OTA acceptance.

Checks are advisory for QEMU acceptance; NOT a secure-boot or OTA trust anchor.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[1]
MANAGER = ROOT / 'tools/virtualedge_ab.py'
RELEASE = ROOT / 'tools/virtualedge_release.py'
MAX_BUNDLE = 1024**3 + 8 * 1024**2


def regular(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError(f'missing or unsafe regular file: {path}')
    return path


def ext4_superblock(path):
    path = regular(path)
    if path.stat().st_size < 2 * 1024**2:
        raise ValueError(f'filesystem image too small: {path}')
    with path.open('rb') as stream:
        stream.seek(1080)  # ext superblock starts at 1024; s_magic at +56
        if stream.read(2) != b'\x53\xef':
            raise ValueError(f'image has no ext2/3/4 superblock: {path}')


def sha(path):
    digest = hashlib.sha256()
    with regular(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def run(state_dir, data_image, bundle, public_key, *, root=ROOT, output=print):
    state_dir = Path(state_dir)
    data_image, bundle, public_key = map(regular, (data_image, bundle, public_key))
    if not state_dir.is_dir() or state_dir.is_symlink():
        raise ValueError('A/B state directory missing or symlinked')
    if not 0 < bundle.stat().st_size <= MAX_BUNDLE:
        raise ValueError('signed release bundle exceeds size limit')
    output('PASS: OTA input files and A/B directory are regular')
    ext4_superblock(data_image)
    output('PASS: persistent data image has a recognized ext filesystem superblock')

    manager = root / 'tools/virtualedge_ab.py'
    release = root / 'tools/virtualedge_release.py'
    base = [sys.executable, str(manager), '--state-dir', str(state_dir)]
    status = json.loads(subprocess.check_output(base + ['status'], text=True, timeout=30))
    if status['format'] != 2 or status['pending'] is not None:
        raise ValueError('A/B state must be format 2 with no pending update')
    subprocess.run(base + ['audit'], check=True, timeout=90, capture_output=True, text=True)
    slot = status['confirmed']
    confirmed = state_dir / f'rootfs-{slot}.ext4'
    ext4_superblock(confirmed)
    output(f'PASS: confirmed slot {slot} has a valid filesystem superblock and matching stored digest')

    subprocess.run([sys.executable, str(release), 'verify', '--bundle', str(bundle),
                    '--public-key', str(public_key), '--board', 'qemu-aarch64',
                    '--min-version', status['versions'][slot]],
                   check=True, timeout=90, capture_output=True, text=True)
    output('PASS: release signature, image digest, board and minimum version verified')
    with tarfile.open(bundle, 'r') as tf:
        members = tf.getmembers()
        if len(members) != 3 or {m.name for m in members} != {'image.bin', 'manifest.json', 'manifest.sig'} or not all(m.isfile() for m in members):
            raise ValueError('unexpected release bundle members')
        image = tf.getmember('image.bin')
        if image.size < 2 * 1024**2:
            raise ValueError('candidate image too small')
        stream = tf.extractfile(image)
        if stream is None:
            raise ValueError('missing candidate image data')
        stream.seek(1080)
        if stream.read(2) != b'\x53\xef':
            raise ValueError('candidate image has no ext filesystem superblock')
        stream.seek(0)
        digest = hashlib.sha256()
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    output('PASS: candidate contains an ext filesystem image')
    if digest.hexdigest() == sha(confirmed):
        output('NOTICE: candidate bytes equal confirmed slot; tests update mechanics, not a new software version')
    else:
        output('INFO: candidate bytes differ from confirmed slot (boot compatibility still needs QEMU testing)')

    # A/B acceptance copies: both state slots plus data; ensure a reasonable floor
    # for temporary storage without requiring arbitrary free-space thresholds.
    required = (2 * image.size + data_image.stat().st_size + confirmed.stat().st_size) + 64 * 1024**2
    free = shutil.disk_usage(root).free
    if free < required:
        raise ValueError(f'not enough WSL filesystem space: need about {required // 1024**2} MiB, free {free // 1024**2} MiB')
    output(f'PASS: temporary QEMU test space available ({free // 1024**2} MiB free)')
    output('PASS: non-mutating QEMU OTA preflight completed; ARM64 boot/rollback not yet tested')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-dir', type=Path, default=ROOT / 'out/ab')
    parser.add_argument('--data-image', type=Path, default=ROOT / 'out/persistent/virtualedge-data.ext4')
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--public-key', type=Path, required=True)
    args = parser.parse_args()
    try:
        run(args.state_dir, args.data_image, args.bundle, args.public_key)
    except (ValueError, OSError, KeyError, subprocess.CalledProcessError, subprocess.TimeoutExpired, tarfile.TarError) as exc:
        print(f'FAIL: QEMU OTA preflight: {exc}', file=sys.stderr)
        return 1
    return 0

if __name__ == '__main__':
    sys.exit(main())
