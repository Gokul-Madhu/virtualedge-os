#!/usr/bin/env python3
"""v0.23 A/B integrity behavior: corruption, fallback, confirmation, migration."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
AB = ROOT / 'tools' / 'virtualedge_ab.py'
RELEASE = ROOT / 'tools' / 'virtualedge_release.py'


def call(cmd, success=True):
    r = subprocess.run([sys.executable, *map(str, cmd)], text=True, capture_output=True, timeout=30)
    if (r.returncode == 0) != success:
        raise AssertionError(f"unexpected return {r.returncode}: {cmd}\n{r.stdout}\n{r.stderr}")
    return r

with tempfile.TemporaryDirectory() as t:
    tmp = Path(t)
    a = tmp/'initial.img'; a.write_bytes(b'A'*8192)
    b = tmp/'candidate.img'; b.write_bytes(b'B'*8192)
    prv=tmp/'sign.pem'; pub=tmp/'sign.pub.pem'; bundle=tmp/'release.tar'
    call([RELEASE,'keygen','--private-key',prv,'--public-key',pub])
    call([RELEASE,'pack','--image',b,'--private-key',prv,'--board','qemu-aarch64','--version','0.23.0','--output',bundle])
    state = tmp/'ab'
    def ab(*args, success=True):
        return call([AB,'--state-dir',state,*args], success)
    ab('init','--image',a,'--version','0.22.0')
    assert json.loads(ab('status').stdout)['format']==2
    ab('audit')
    ab('stage','--bundle',bundle,'--public-key',pub)
    ab('audit')
    # Corrupt pending image; boot must not select it and must not promote it.
    (state/'rootfs-B.ext4').write_bytes(b'X'*8192)
    ab('audit',success=False)
    ab('confirm','--slot','B','--guest-selftest-passed',success=False)
    assert ab('boot').stdout.split()[0]=='A'
    status = json.loads(ab('status').stdout)
    assert status['confirmed']=='A' and status['pending'] is None
    print('PASS: candidate corruption fails audit and confirmation; automatic fallback keeps A')
    # Verified restaging can recover slot B after corruption.
    ab('stage','--bundle',bundle,'--public-key',pub)
    assert ab('boot').stdout.split()[0]=='B'
    ab('confirm','--slot','B','--guest-selftest-passed')
    ab('audit')
    print('PASS: verified candidate can be confirmed and audited')
    # Corrupt confirmed image; refuse selection (no vulnerable fallback).
    before=json.loads(ab('status').stdout)
    (state/'rootfs-B.ext4').write_bytes(b'T'*8192)
    ab('audit',success=False)
    ab('boot',success=False)
    assert json.loads(ab('status').stdout)==before
    print('PASS: corruption of confirmed image refuses boot with state unchanged')
    # Legacy state migration requires explicit enrollment.
    old=tmp/'old'; old.mkdir()
    (old/'rootfs-A.ext4').write_bytes(b'LEGACY')
    (old/'state.json').write_text(json.dumps({'format':1,'confirmed':'A','pending':None,
        'attempts_left':0,'versions':{'A':'0.22.0','B':None}}))
    def legacy(*args, success=True):
        return call([AB,'--state-dir',old,*args],success)
    legacy('audit',success=False)
    legacy('enroll')
    legacy('audit')
    legacy('enroll',success=False)
    print('PASS: legacy v1 integrity enrollment explicit and repeat-safe')
print('All v0.23 A/B integrity checks passed.')
