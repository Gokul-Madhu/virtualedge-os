#!/usr/bin/env python3
"""Host acceptance checks for QEMU-only A/B manager."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
MANAGER = ROOT / 'tools/virtualedge_ab.py'
SIGNER = ROOT / 'tools/virtualedge_release.py'

def run(*args, ok=True):
    p = subprocess.run([sys.executable, str(args[0]), *map(str, args[1:])], capture_output=True, text=True)
    if ok and p.returncode:
        raise AssertionError(f'failed: {args}\n{p.stdout}\n{p.stderr}')
    if not ok and p.returncode == 0:
        raise AssertionError(f'expected failure: {args}')
    return p.stdout.strip()

with tempfile.TemporaryDirectory() as td:
    work = Path(td)
    slots = work / 'ab'
    original = work / 'original.img'
    update = work / 'update.img'
    original.write_bytes(b'ROOT_A\0' * 4096)
    update.write_bytes(b'ROOT_B\0' * 4096)
    private, public = work/'private.pem', work/'public.pem'
    bundle = work / 'signed.tar'
    run(SIGNER, 'keygen', '--private-key', private, '--public-key', public)
    run(SIGNER, 'pack', '--image', update, '--private-key', private, '--board', 'qemu-aarch64', '--version','0.10.0','--output',bundle)
    def ab(*args, ok=True):
        return run(MANAGER, '--state-dir', slots, *args, ok=ok)
    ab('init', '--image', original, '--version', '0.9.0')
    assert (slots/'rootfs-A.ext4').read_bytes() == original.read_bytes()
    assert ab('boot').split()[0] == 'A'
    ab('stage', '--bundle', bundle, '--public-key', public)
    s = json.loads(ab('status'))
    assert s['pending'] == 'B' and s['attempts_left'] == 2
    assert (slots/'rootfs-A.ext4').read_bytes() == original.read_bytes()
    assert (slots/'rootfs-B.ext4').read_bytes() == update.read_bytes()
    ab('stage', '--bundle', bundle, '--public-key', public, ok=False)
    ab('confirm', '--slot','B', ok=False)
    assert ab('boot').split()[0] == 'B'
    assert ab('boot').split()[0] == 'B'
    assert ab('boot').split()[0] == 'A'
    assert json.loads(ab('status'))['confirmed'] == 'A'
    print('PASS: unconfirmed candidate exhausts attempts and falls back to A')
    ab('stage', '--bundle', bundle, '--public-key', public)
    assert ab('boot').split()[0] == 'B'
    ab('confirm', '--slot','B','--guest-selftest-passed')
    assert ab('boot').split()[0] == 'B'
    assert json.loads(ab('status'))['confirmed'] == 'B'
    ab('stage', '--bundle', bundle, '--public-key', public, ok=False)
    print('PASS: confirmation and rollback floor prevent same-version update')
    with tempfile.TemporaryDirectory() as td2:
        alt = Path(td2)
        wrong_bundle = alt/'wrong.tar'
        run(SIGNER, 'pack', '--image', original, '--private-key', private, '--board','raspberrypi4','--version','0.11.0','--output',wrong_bundle)
        ab('stage', '--bundle',wrong_bundle, '--public-key',public,ok=False)
        print('PASS: wrong board identity rejected')
    later = work/'later.tar'
    run(SIGNER, 'pack', '--image',original,'--private-key',private,'--board','qemu-aarch64','--version','0.11.0','--output',later)
    ab('stage', '--bundle',later,'--public-key',public)
    ab('abort')
    assert json.loads(ab('status'))['confirmed'] == 'B'
    print('PASS: abort leaves confirmed slot intact')
    assert original.read_bytes().startswith(b'ROOT_A')
    print('PASS: slot images remain independent')
print('All QEMU A/B host tests passed.')
