#!/usr/bin/env python3
"""v0.29: guest-exported image -> signed host A/B handoff tests."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SIGN = ROOT / 'tools/virtualedge_release.py'
AB = ROOT / 'tools/virtualedge_ab.py'
IMPORT = ROOT / 'tools/virtualedge_ab_import.py'


def command(*args, good=True):
    p = subprocess.run([sys.executable, str(args[0]), *map(str, args[1:])],
                       capture_output=True, text=True, timeout=45)
    if (p.returncode == 0) != good:
        raise AssertionError(f'Unexpected exit={p.returncode}: {args}\n{p.stdout}\n{p.stderr}')
    return p.stdout


with tempfile.TemporaryDirectory() as tmp:
    base = Path(tmp)
    a, b = base / 'base.img', base / 'upgrade.img'
    a.write_bytes(b'ROOTFS_OLD' * 3000)
    b.write_bytes(b'ROOTFS_NEW' * 3000)
    private, pub = base / 'private.pem', base / 'public.pem'
    signed = base / 'release.tar'
    command(SIGN, 'keygen', '--private-key', private, '--public-key', pub)
    command(SIGN, 'pack', '--image', b, '--private-key', private, '--board', 'qemu-aarch64',
            '--version', '0.29.0', '--output', signed)
    state = base / 'ab'
    command(AB, '--state-dir', state, 'init', '--image', a, '--version', '0.28.0')
    candidate = base / 'candidate'
    candidate.mkdir(mode=0o700)
    with tarfile.open(signed) as tar:
        for name in ('manifest.json', 'manifest.sig', 'image.bin'):
            (candidate / name).write_bytes(tar.extractfile(name).read())
    exported = base / 'inactive-slot.img'
    shutil.copyfile(candidate / 'image.bin', exported)

    def handoff(good=True, cand=None, image=None, key=None):
        return command(IMPORT, '--state-dir', state, '--candidate-dir', cand or candidate,
                       '--inactive-image', image or exported, '--public-key', key or pub, good=good)

    # Detect mismatch before any slot metadata change.
    tampered = base / 'tampered.img'
    tampered.write_bytes(b'CORRUPTED' * 200)
    handoff(good=False, image=tampered)
    assert json.loads(command(AB, '--state-dir', state, 'status'))['pending'] is None
    assert (state / 'rootfs-A.ext4').read_bytes() == a.read_bytes()
    print('PASS: mismatched exported inactive image rejected without changing A/B state')

    # No symlinks, even when contents match.
    link = base / 'link.img'
    link.symlink_to(exported)
    handoff(good=False, image=link)
    print('PASS: symlinked image rejected')

    # Cryptographic signature must still verify, not just candidate vs output hash.
    bad_candidate = base / 'bad-candidate'
    shutil.copytree(candidate, bad_candidate)
    (bad_candidate / 'manifest.sig').write_bytes(b'bad-signature')
    handoff(good=False, cand=bad_candidate)
    assert json.loads(command(AB, '--state-dir', state, 'status'))['pending'] is None
    print('PASS: untrusted candidate rejected by independent signature verification')

    handoff()
    state_json = json.loads(command(AB, '--state-dir', state, 'status'))
    assert state_json['confirmed'] == 'A' and state_json['pending'] == 'B'
    assert state_json['attempts_left'] == 2
    assert (state / 'rootfs-A.ext4').read_bytes() == a.read_bytes()
    assert (state / 'rootfs-B.ext4').read_bytes() == b.read_bytes()
    command(AB, '--state-dir', state, 'audit')
    print('PASS: matching, valid guest image staged into inactive slot with integrity metadata')

    handoff(good=False)
    assert json.loads(command(AB, '--state-dir', state, 'status'))['pending'] == 'B'
    print('PASS: existing pending update cannot be overwritten')

    assert command(AB, '--state-dir', state, 'boot').split()[0] == 'B'
    assert command(AB, '--state-dir', state, 'boot').split()[0] == 'B'
    assert command(AB, '--state-dir', state, 'boot').split()[0] == 'A'
    assert json.loads(command(AB, '--state-dir', state, 'status'))['confirmed'] == 'A'
    print('PASS: unconfirmed guest image falls back to original confirmed slot')

print('All v0.29 guest-to-host A/B handoff tests passed')
