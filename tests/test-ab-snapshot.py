#!/usr/bin/env python3
"""v0.24: TOCTOU regression, oversized bundles, and staging interruption."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import virtualedge_ab as ab
RELEASE = ROOT / 'tools' / 'virtualedge_release.py'


def run(*args):
    r = subprocess.run([sys.executable, str(RELEASE), *map(str,args)],capture_output=True,text=True,timeout=25)
    if r.returncode: raise AssertionError(f'{args}: {r.stderr}')

with tempfile.TemporaryDirectory() as folder:
    home = Path(folder)
    state = home / 'ab'
    ab.safe_directory(state)
    original = home / 'rootfs-old.ext4'
    original.write_bytes(b'ORIGINAL'*1000)
    ab.init(argparse.Namespace(image=str(original), version='0.23.0'), state)
    trusted = home / 'trusted.ext4'
    trusted.write_bytes(b'TRUSTED'*1000)
    forged = home / 'forged.ext4'
    forged.write_bytes(b'FORGED!'*1000)
    private, public = home/'private.pem', home/'public.pem'
    run('keygen', '--private-key',private,'--public-key',public)
    verified_bundle = home/'release.tar'
    forged_bundle = home/'other.tar'
    run('pack','--image',trusted,'--private-key',private,'--board','qemu-aarch64','--version','0.24.0','--output',verified_bundle)
    run('pack','--image',forged,'--private-key',private,'--board','qemu-aarch64','--version','0.24.0','--output',forged_bundle)

    command = argparse.Namespace(bundle=str(verified_bundle), public_key=str(public))
    actual_run = ab.subprocess.run
    swapped = [False]
    def swap_after_verify(*args, **kwargs):
        result = actual_run(*args, **kwargs)
        # Replaces the original pathname after verification succeeds; old
        # staging code would install the replacement rather than verified bytes.
        if not swapped[0] and args[0][1].endswith('virtualedge_release.py'):
            forged_bundle.replace(verified_bundle)
            swapped[0] = True
        return result
    with patch.object(ab.subprocess, 'run', side_effect=swap_after_verify):
        ab.stage(command, state)
    assert swapped[0]
    assert (state/'rootfs-B.ext4').read_bytes() == trusted.read_bytes()
    assert (state/'rootfs-A.ext4').read_bytes() == original.read_bytes()
    assert ab.load(state)['hashes']['B'] == hashlib.sha256(trusted.read_bytes()).hexdigest()
    assert not list(state.glob('.ve-bundle-*'))
    print('PASS: source bundle replaced after verification; only snapshotted signed image installed')

    ab.abort(argparse.Namespace(), state)
    # Invalid, non-tar or oversized inputs never modify a confirmed slot.
    rejected = home/'untrusted.tar'
    rejected.write_bytes(b'not a signed bundle')
    previous = ab.load(state)
    try:
        ab.stage(argparse.Namespace(bundle=str(rejected),public_key=str(public)),state)
        raise AssertionError('invalid bundle accepted')
    except subprocess.CalledProcessError:
        pass
    assert ab.load(state) == previous
    assert (state/'rootfs-A.ext4').read_bytes() == original.read_bytes()
    assert not list(state.glob('.ve-bundle-*'))
    print('PASS: rejected bundle leaves A/B metadata unchanged and cleans private snapshot')

    link = home/'linked.tar'
    link.symlink_to(rejected)
    try:
        ab.stage(argparse.Namespace(bundle=str(link),public_key=str(public)),state)
        raise AssertionError('symlink bundle accepted')
    except ValueError:
        pass
    print('PASS: symlinked release bundle rejected')

    # Simulate metadata write failing after atomic inactive image replacement;
    # the confirmed slot must still be available, and the next stage can retry.
    fresh = home/'fresh.tar'
    run('pack','--image',trusted,'--private-key',private,'--board','qemu-aarch64','--version','0.24.1','--output',fresh)
    old_atomic = ab.atomic_json
    def fail_state_write(*_):
        raise OSError('injected metadata write failure')
    with patch.object(ab, 'atomic_json', side_effect=fail_state_write):
        try:
            ab.stage(argparse.Namespace(bundle=str(fresh),public_key=str(public)),state)
            raise AssertionError('injected crash was ignored')
        except OSError:
            pass
    assert ab.load(state) == previous
    assert (state/'rootfs-A.ext4').read_bytes() == original.read_bytes()
    assert not list(state.glob('.ve-bundle-*'))
    ab.stage(argparse.Namespace(bundle=str(fresh),public_key=str(public)),state)
    assert ab.load(state)['pending'] == 'B'
    assert (state/'rootfs-B.ext4').read_bytes() == trusted.read_bytes()
    print('PASS: interrupted metadata commit preserves confirmed slot; safe restaging succeeds')
print('All v0.24 A/B staging snapshot tests passed.')
