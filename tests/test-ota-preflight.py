#!/usr/bin/env python3
"""Fast, host-only tests of non-mutating signed QEMU OTA preflight."""
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('ota_preflight', ROOT / 'scripts/preflight-qemu-ota.py')
preflight = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preflight)


def shell(*args, ok=True):
    proc = subprocess.run([sys.executable, *map(str, args)], text=True, capture_output=True)
    if (proc.returncode == 0) != ok:
        raise AssertionError(f'unexpected return code {proc.returncode}: {proc.stdout}\n{proc.stderr}')
    return proc


def filesystem(path, marker=True):
    with path.open('wb') as f:
        f.truncate(4 * 1024 * 1024)
        if marker:
            f.seek(1080)
            f.write(b'\x53\xef')


with tempfile.TemporaryDirectory() as td:
    p = Path(td)
    current, newer, data = p/'current.ext4', p/'new.ext4', p/'data.ext4'
    filesystem(current)
    filesystem(newer)
    filesystem(data)
    with newer.open('r+b') as f:
        f.seek(2048)
        f.write(b'new candidate data')
    ab = p/'ab'
    keys = [p/'private.pem', p/'public.pem']
    bundle = p/'release.tar'
    release = ROOT/'tools/virtualedge_release.py'
    manager = ROOT/'tools/virtualedge_ab.py'
    shell(release, 'keygen', '--private-key', keys[0], '--public-key', keys[1])
    shell(manager, '--state-dir', ab, 'init', '--image', current, '--version', '0.32.0')
    shell(release, 'pack', '--image', newer, '--private-key', keys[0],
          '--board', 'qemu-aarch64', '--version', '0.33.0', '--output', bundle)
    lines = []
    preflight.run(ab, data, bundle, keys[1], output=lines.append)
    assert any('non-mutating QEMU OTA preflight' in line for line in lines)
    assert any('candidate bytes differ' in line for line in lines)
    assert preflight.sha(ab/'rootfs-A.ext4') == preflight.sha(current)
    print('PASS: signed candidate, baseline, filesystem and disk-space preflight')

    # Same bytes with a higher signed version is a mechanism test, not an upgrade.
    same_bundle = p/'same.tar'
    shell(release, 'pack', '--image', current, '--private-key', keys[0],
          '--board', 'qemu-aarch64', '--version', '0.33.0', '--output', same_bundle)
    lines = []
    preflight.run(ab, data, same_bundle, keys[1], output=lines.append)
    assert any('candidate bytes equal confirmed slot' in line for line in lines)
    print('PASS: identical-image test is clearly identified')

    wrong = p/'bad.ext4'
    filesystem(wrong, marker=False)
    try:
        preflight.run(ab, wrong, bundle, keys[1], output=lambda _: None)
    except ValueError as exc:
        assert 'superblock' in str(exc)
    else:
        raise AssertionError('missing ext superblock accepted')
    print('PASS: bad ext filesystem superblock rejected')

    tampered = p/'tampered.tar'
    contents = bytearray(bundle.read_bytes())
    # Mutate the image payload, not the archive headers.
    pos = contents.find(b'new candidate data')
    assert pos > 0
    contents[pos] ^= 1
    tampered.write_bytes(contents)
    try:
        preflight.run(ab, data, tampered, keys[1], output=lambda _: None)
    except subprocess.CalledProcessError:
        pass
    else:
        raise AssertionError('tampered signed release accepted')
    print('PASS: tampered image rejected by original signed-release verifier')

    symlink = p/'link.tar'
    symlink.symlink_to(bundle)
    try:
        preflight.run(ab, data, symlink, keys[1], output=lambda _: None)
    except ValueError:
        pass
    else:
        raise AssertionError('symlinked bundle accepted')
    print('PASS: unsafe symbolic-link input rejected')
print('All QEMU OTA preflight tests passed.')
