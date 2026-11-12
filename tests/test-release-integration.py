#!/usr/bin/env python3
"""Source-level regression checks for consolidated v0.32 fixes."""
from pathlib import Path
import subprocess
import tempfile
import tarfile
import os
R = Path(__file__).resolve().parents[1]
def read(name): return (R/name).read_text()
tester=read('scripts/test-qemu.py')
assert "replace('\\r', '')" in tester
assert tester.index("f'file={data_disk},if=none") < tester.index("f'file={disk},if=none")
assert 'dereference=True' in read('tools/virtualedge_release.py')
persistent=read('scripts/run-qemu-persistent.sh')
assert persistent.index('file=$DATA_IMAGE,if=none') < persistent.index('file=$BOOT_DIR/rootfs.ext4,if=none')
assert 'cp -- "$ROOTFS" "$BOOT_DIR/rootfs.ext4"' in persistent
ab=read('scripts/run-qemu-ab.sh')
assert ab.index('id=data') < ab.index('id=rootfs')
assert 'cp -- "$ROOTFS" "$BOOT_DIR/boot-rootfs.ext4"' in ab
assert 'VE_LISTEN_ANY=1' in read('board/virtualedge/rootfs-overlay/etc/default/virtualedge-api')
assert 'file=$BOOT_DIR/rootfs.ext4,if=none' in read('scripts/run-qemu-native-tls.sh')
assert 'VE_FORWARD_DASHBOARD=1' in read('scripts/run-qemu-dashboard.sh')
with tempfile.TemporaryDirectory() as t:
    tmp=Path(t);(tmp/'actual').write_bytes(b'virtualedge test rootfs')
    (tmp/'link').symlink_to(tmp/'actual')
    with tarfile.open(tmp/'release.tar','w',dereference=True) as tar: tar.add(tmp/'link',arcname='image.bin')
    with tarfile.open(tmp/'release.tar','r') as tar:
        entry=tar.getmember('image.bin')
        assert entry.isfile() and tar.extractfile(entry).read()==b'virtualedge test rootfs'
for path in ['scripts/run-qemu-persistent.sh','scripts/run-qemu-ab.sh','scripts/run-qemu-native-tls.sh','scripts/run-qemu-dashboard.sh']:
    subprocess.run(['bash','-n',str(R/path)],check=True)
for path in ['scripts/test-qemu.py','tools/virtualedge_release.py']:
    compile((R/path).read_bytes(),str(R/path),'exec')
print('PASS: Final integration, disk ordering, preserved root images, signing symlinks and dashboard launcher')
