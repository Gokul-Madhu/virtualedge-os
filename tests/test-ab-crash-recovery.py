#!/usr/bin/env python3
"""Crash-injection tests for v0.25 QEMU-hosted A/B staging.

Uses tiny disposable files and private signing keys, never physical disks.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
AB = ROOT / 'tools' / 'virtualedge_ab.py'
REL = ROOT / 'tools' / 'virtualedge_release.py'
POINTS = ('snapshot_fsynced', 'slot_temp_fsynced', 'slot_replaced', 'metadata_committed')


def execute(program, *args, env=None, rc=0):
    p = subprocess.run([sys.executable, str(program), *map(str, args)],
                       env=env, text=True, capture_output=True, timeout=30)
    assert p.returncode == rc, f'{args}: exit={p.returncode}\n{p.stdout}\n{p.stderr}'
    return p


with tempfile.TemporaryDirectory(prefix='ve25-ab-fault-') as temp:
    root = Path(temp)
    old = root / 'old.ext4'; old.write_bytes(b'KNOWN-GOOD-ROOTFS' * 512)
    candidate = root / 'candidate.ext4'; candidate.write_bytes(b'SIGNED-CANDIDATE' * 512)
    private = root / 'sign.key.pem'; public = root / 'sign.pub.pem'
    bundle = root / 'candidate.tar'
    execute(REL, 'keygen', '--private-key', private, '--public-key', public)
    execute(REL, 'pack', '--image', candidate, '--private-key', private,
            '--board', 'qemu-aarch64', '--version', '0.25.0', '--output', bundle)
    old_hash = hashlib.sha256(old.read_bytes()).hexdigest()
    candidate_hash = hashlib.sha256(candidate.read_bytes()).hexdigest()
    for point in [p for p in POINTS if not os.environ.get("VE_ONLY_POINT") or p == os.environ["VE_ONLY_POINT"]]:
        state = root / point
        def ab(*args, rc=0, env=None):
            return execute(AB, '--state-dir', state, *args, rc=rc, env=env)
        ab('init', '--image', old, '--version', '0.24.0')
        env = os.environ.copy()
        env.update(VE_TEST_FAULTS='I_UNDERSTAND_THIS_KILLS_THE_PROCESS',
                   VE_TEST_CRASH_POINT=point)
        ab('stage', '--bundle', bundle, '--public-key', public, env=env, rc=77)
        before = json.loads(ab('status').stdout)
        assert before['confirmed'] == 'A'
        assert (state / 'rootfs-A.ext4').read_bytes() == old.read_bytes()
        assert before['hashes']['A'] == old_hash
        assert list(state.glob('.ve-*')), 'expected orphan temp file after crash'
        ab('recover')
        after = json.loads(ab('status').stdout)
        assert before == after, 'recovery must not change metadata'
        assert not [x for x in state.iterdir() if x.name.startswith(('.ve-bundle-', '.ve-stage-', '.ve-image-', '.ve-state-'))]
        ab('audit')
        if point != 'metadata_committed':
            assert after['pending'] is None, point
            assert ab('boot').stdout.split()[0] == 'A'
            ab('stage', '--bundle', bundle, '--public-key', public)
        else:
            assert after['pending'] == 'B'
        current = json.loads(ab('status').stdout)
        assert current['pending'] == 'B'
        assert current['hashes']['B'] == candidate_hash
        assert (state / 'rootfs-B.ext4').read_bytes() == candidate.read_bytes()
        ab('audit')
        print(f'PASS: crash at {point}; confirmed A remains valid, recovery and verified retry succeed')

    # An orphan symlink must not be traversed or deleted automatically.
    state = root / 'unsafe-temp'; execute(AB, '--state-dir', state,
                                         'init', '--image', old, '--version', '0.24.0')
    (state / '.ve-stage-untrusted').symlink_to(old)
    execute(AB, '--state-dir', state, 'recover', rc=1)
    assert (state / '.ve-stage-untrusted').is_symlink()
    print('PASS: unsafe symlink prevents automatic orphan cleanup')

    # A corrupted confirmed image must prevent recovery; no masking corruption.
    state = root / 'bad-confirmed'; execute(AB, '--state-dir', state,
                                           'init', '--image', old, '--version', '0.24.0')
    (state / 'rootfs-A.ext4').write_bytes(b'CORRUPTED')
    execute(AB, '--state-dir', state, 'recover', rc=1)
    print('PASS: recovery refuses corrupted confirmed slot')
print('All v0.25 controlled A/B crash recovery tests passed.')
