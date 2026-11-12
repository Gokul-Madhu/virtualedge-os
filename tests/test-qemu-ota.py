#!/usr/bin/env python3
"""Host-only v0.30 orchestration tests using REAL A/B manager and signed bundles.

Only the QEMU boot runner is replaced with a stub; no test proves ARM64 boot.
"""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'scripts/test-qemu-ota.py'
SPEC = importlib.util.spec_from_file_location('ve_ota', SOURCE)
OTA = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(OTA)
RELEASE = ROOT / 'tools/virtualedge_release.py'
AB = ROOT / 'tools/virtualedge_ab.py'


def cmd(script, *argv):
    result = subprocess.run([sys.executable, str(script), *map(str, argv)],
                            capture_output=True, text=True, timeout=45)
    if result.returncode:
        raise AssertionError(result.stderr + result.stdout)
    return result.stdout


with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    old, new = root / 'old.ext4', root / 'new.ext4'
    old.write_bytes(b'VE_OLD' * 5000)
    new.write_bytes(b'VE_NEW' * 5000)
    private, public = root / 'secret.pem', root / 'public.pem'
    bundle = root / 'signed.tar'
    data = root / 'data.ext4'
    data.write_bytes(b'VE_DATA' * 5000)
    cmd(RELEASE, 'keygen', '--private-key', private, '--public-key', public)
    cmd(RELEASE, 'pack', '--image', new, '--private-key', private,
        '--board', 'qemu-aarch64', '--version', '0.30.0', '--output', bundle)
    live = root / 'live-ab'
    cmd(AB, '--state-dir', live, 'init', '--image', old, '--version', '0.29.0')
    initial_state = (live / 'state.json').read_bytes()
    initial_img = (live / 'rootfs-A.ext4').read_bytes()
    seen = []

    def passed(slot, version, rootfs, disk, timeout):
        seen.append((slot, version))
        assert rootfs.is_file() and disk.is_file()
        assert rootfs.parent != live
        assert disk != data
        assert timeout == 30

    OTA.scenario(live, data, bundle, public, 30, True, passed)
    assert seen == [('B', '0.30.0')]
    assert (live / 'state.json').read_bytes() == initial_state
    print('PASS: real signed staging + simulated guest pass confirms disposable candidate only')

    seen.clear()
    OTA.scenario(live, data, bundle, public, 30, False, passed)
    assert seen == [('B', '0.30.0'), ('B', '0.30.0'), ('A', '0.29.0')]
    print('PASS: two simulated guest boots then confirmed-slot fallback')

    def failure(*_):
        raise RuntimeError('injected guest self-test failure')

    try:
        OTA.scenario(live, data, bundle, public, 30, True, failure)
    except RuntimeError as exc:
        assert 'injected' in str(exc)
    else:
        raise AssertionError('guest failure unexpectedly accepted')
    assert (live / 'state.json').read_bytes() == initial_state
    print('PASS: guest failure cannot confirm or alter live A/B state')

    corrupted = root / 'corrupted.tar'
    blob = bytearray(bundle.read_bytes())
    blob[512] ^= 1
    corrupted.write_bytes(blob)
    try:
        OTA.scenario(live, data, corrupted, public, 30, True, passed)
    except subprocess.CalledProcessError:
        pass
    else:
        raise AssertionError('tampered bundle was accepted')
    print('PASS: modified signed bundle rejected before guest boot')

    with tempfile.TemporaryDirectory() as temp:
        temp_dir = Path(temp)
        state, _ = OTA.prepare_state(temp_dir, live)
        assert json.loads(cmd(AB, '--state-dir', state, 'status'))['confirmed'] == 'A'
        assert (state / 'rootfs-A.ext4').read_bytes() == initial_img
    print('PASS: verified state cloning keeps source images unchanged')

    link = root / 'unsafe.ext4'
    link.symlink_to(data)
    try:
        OTA.scenario(live, link, bundle, public, 30, True, passed)
    except ValueError:
        pass
    else:
        raise AssertionError('symlink data disk was accepted')
    assert (live / 'state.json').read_bytes() == initial_state
    print('PASS: symlinked data images refused')

print('All v0.30 host OTA-orchestration tests passed (no QEMU execution)')
