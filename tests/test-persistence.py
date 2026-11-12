#!/usr/bin/env python3
"""Host-only tests of persistent-image setup and safe boot-script properties."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

project = Path(__file__).resolve().parents[1]
launcher = project / 'scripts/run-qemu-persistent.sh'
init = project / 'board/virtualedge/rootfs-overlay/etc/init.d/S20virtualedge-data'

for script in (launcher, init):
    subprocess.run(['bash', '-n', str(script)] if script == launcher else ['sh', '-n', str(script)], check=True)

startup = init.read_text()
assert 'mount --bind "$DATA_MOUNT/virtualedge/config" "$CONFIG_TARGET"' in startup
assert 'mount --bind "$DATA_MOUNT/virtualedge/log" "$LOG_TARGET"' in startup
assert 'mount -t ext4 -o nosuid,nodev,noexec' in startup
assert 'mkfs' not in startup, 'Never format guest disks automatically'
assert 'if [ ! -b "$DATA_DEV" ]' in startup

# Exercise launcher without needing a real Buildroot build: fake QEMU prints arguments.
with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    (root / 'scripts').mkdir()
    (root / 'out/buildroot/images').mkdir(parents=True)
    (root / 'out/buildroot/host/bin').mkdir(parents=True)
    shutil.copy2(launcher, root / 'scripts/run-qemu-persistent.sh')
    (root / 'out/buildroot/images/Image').write_bytes(b'kernel-test')
    (root / 'out/buildroot/images/rootfs.ext4').write_bytes(b'rootfs-test')
    qemu = root / 'out/buildroot/host/bin/qemu-system-aarch64'
    qemu.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\n')
    qemu.chmod(0o755)
    image = root / 'out/persistent/virtualedge-data.ext4'
    env = dict(os.environ, VE_DATA_IMAGE=str(image), VE_DATA_SIZE_MB='8')
    if shutil.which('mkfs.ext4'):
        first = subprocess.run([str(root / 'scripts/run-qemu-persistent.sh')],
                               env=env, capture_output=True, text=True, check=True)
        assert image.exists() and image.stat().st_size == 8 * 1024 * 1024
        assert 'file=' + str(image) in first.stdout
        # Ensure second launch does not reformat and retains bytes.
        with image.open('r+b') as handle:
            handle.seek(7 * 1024 * 1024)
            handle.write(b'PERSIST-TEST')
        second = subprocess.run([str(root / 'scripts/run-qemu-persistent.sh')],
                                env=env, capture_output=True, text=True, check=True)
        assert 'Reusing existing data volume' in second.stdout
        with image.open('rb') as handle:
            handle.seek(7 * 1024 * 1024)
            assert handle.read(12) == b'PERSIST-TEST'
    else:
        # Mock the image formatter to exercise creation/reuse behavior even on
        # minimal CI environments without e2fsprogs. This is not an ext4 test.
        fakebin = root / 'fakebin'
        fakebin.mkdir()
        formatter = fakebin / 'mkfs.ext4'
        formatter.write_text('#!/bin/sh\nexit 0\n')
        formatter.chmod(0o755)
        env['PATH'] = str(fakebin) + os.pathsep + env.get('PATH', '')
        first = subprocess.run([str(root / 'scripts/run-qemu-persistent.sh')],
                               env=env, capture_output=True, text=True, check=True)
        assert image.is_file() and image.stat().st_size == 8 * 1024 * 1024
        assert 'file=' + str(image) in first.stdout
        with image.open('r+b') as handle:
            handle.seek(7 * 1024 * 1024)
            handle.write(b'PERSIST-TEST')
        second = subprocess.run([str(root / 'scripts/run-qemu-persistent.sh')],
                                env=env, capture_output=True, text=True, check=True)
        assert 'Reusing existing data volume' in second.stdout
        with image.open('rb') as handle:
            handle.seek(7 * 1024 * 1024)
            assert handle.read(12) == b'PERSIST-TEST'
        print('NOTE: mkfs.ext4 absent; tested launcher with mock formatter, not filesystem mounting')
print('PASS: Persistent disk launcher and early boot service source checks')
