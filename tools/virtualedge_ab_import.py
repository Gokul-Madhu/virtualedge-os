#!/usr/bin/env python3
"""Offline handoff of v0.28 guest-installed file into QEMU-only A/B manager.

Host development tool, NOT an OTA block writer. Takes candidate manifest/signature
and exported inactive-slot.img, makes a private bounded snapshot, verifies the
signed bundle by the existing A/B staging code, and updates host A/B state.
"""
import argparse
import hashlib
import os
from pathlib import Path
import stat
import subprocess
import sys
import tarfile
import tempfile

MAX_IMAGE = 1024 * 1024 * 1024
MAX_META = {"manifest.json": 4096, "manifest.sig": 128}


def private_copy(source: Path, target: Path, maximum: int):
    """Use O_NOFOLLOW and copy only bounded regular files into a private snapshot."""
    fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= maximum:
            raise ValueError(f"invalid/unsafe input: {source}")
        sha = hashlib.sha256()
        size = 0
        with os.fdopen(os.dup(fd), 'rb') as input_stream, open(target, 'xb') as dest:
            os.chmod(target, 0o600)
            while chunk := input_stream.read(min(1024 * 1024, maximum + 1 - size)):
                size += len(chunk)
                if size > maximum or size > info.st_size:
                    raise ValueError(f"input grew during snapshot: {source}")
                sha.update(chunk)
                dest.write(chunk)
            if size != info.st_size:
                raise ValueError(f"input changed during snapshot: {source}")
            dest.flush()
            os.fsync(dest.fileno())
        return sha.hexdigest(), size
    finally:
        os.close(fd)


def run(args):
    state = Path(args.state_dir).absolute()
    candidate = Path(args.candidate_dir)
    exported = Path(args.inactive_image)
    key = Path(args.public_key)
    if not candidate.is_dir() or candidate.is_symlink():
        raise ValueError("candidate directory is missing or symlinked")
    if not state.is_dir() or state.is_symlink():
        raise ValueError("initialize a non-symlink A/B state directory first")
    if key.is_symlink() or not key.is_file():
        raise ValueError("trusted public key missing or symlinked")
    if exported.parent.is_symlink():
        raise ValueError("exported image parent must not be a symlink")
    manager = Path(__file__).with_name('virtualedge_ab.py')
    with tempfile.TemporaryDirectory(prefix='.ve-import-', dir=state) as tmp:
        folder = Path(tmp)
        os.chmod(folder, 0o700)
        for name, cap in MAX_META.items():
            private_copy(candidate / name, folder / name, cap)
        # Both candidate/image.bin and exported inactive-slot.img must match.
        # Import the exported image, never the original mutable guest path.
        c_hash, c_size = private_copy(candidate / 'image.bin', folder / 'candidate-image.bin', MAX_IMAGE)
        e_hash, e_size = private_copy(exported, folder / 'image.bin', MAX_IMAGE)
        if (c_hash, c_size) != (e_hash, e_size):
            raise ValueError('exported inactive-slot.img differs from signed candidate/image.bin')
        bundle = folder / 'import.tar'
        with tarfile.open(bundle, mode='w') as tar:
            for name in ('manifest.json', 'manifest.sig', 'image.bin'):
                tar.add(folder / name, arcname=name, recursive=False)
        os.chmod(bundle, 0o600)
        with bundle.open('rb') as stream:
            os.fsync(stream.fileno())
        code = subprocess.run([sys.executable, str(manager), '--state-dir', str(state),
                               'stage', '--bundle', str(bundle), '--public-key', str(key)],
                              check=False)
        if code.returncode:
            raise ValueError('A/B import rejected; confirmed slot was not promoted')
    print('PASS: guest-exported image independently verified and staged in inactive QEMU A/B slot')
    print('NEXT: test candidate boot and self-test before explicit confirmation')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-dir', required=True)
    parser.add_argument('--candidate-dir', required=True)
    parser.add_argument('--inactive-image', required=True)
    parser.add_argument('--public-key', required=True)
    args = parser.parse_args()
    try:
        run(args)
    except (ValueError, OSError, tarfile.TarError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
