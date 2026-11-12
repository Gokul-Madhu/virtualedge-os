#!/usr/bin/env python3
"""Test v0.11 host candidate acceptance with a stub guest harness; no QEMU needed."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
MANAGER = ROOT / 'tools/virtualedge_ab.py'
SIGNER = ROOT / 'tools/virtualedge_release.py'
CHECK = ROOT / 'scripts/check-ab-candidate.py'
TEST_QEMU = ROOT / 'scripts/test-qemu.py'


def cmd(script, *args, success=True):
    p = subprocess.run([sys.executable, str(script), *map(str,args)],
                       capture_output=True, text=True)
    if success and p.returncode:
        raise AssertionError(p.stderr + p.stdout)
    if not success and p.returncode == 0:
        raise AssertionError('Expected failure')
    return p.stdout.strip()


spec = importlib.util.spec_from_file_location('qemu_test', TEST_QEMU)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
mod.verify_cmdline('root=/dev/vda console=ttyAMA0 ve.slot=B ve.version=0.11.0\n', 'B','0.11.0')
for content, slot, version in [
    ('root=/dev/vda ve.slot=A ve.version=0.11.0\n', 'B','0.11.0'),
    ('root=/dev/vda ve.slot=B ve.version=0.10.0\n', 'B','0.11.0'),
    ('root=/dev/vda ve.slot=B ve.version=0.11.0\nroot=/dev/vda ve.slot=B ve.version=0.11.0\n', 'B','0.11.0'),
    ('root=/dev/vda\n', 'B','0.11.0')]:
    try:
        mod.verify_cmdline(content, slot, version)
    except RuntimeError:
        pass
    else:
        raise AssertionError('Incorrect guest slot evidence accepted')
print('PASS: guest boot marker parsing rejects mismatch and ambiguous reports')

spec = importlib.util.spec_from_file_location('acceptance', CHECK)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
with tempfile.TemporaryDirectory() as tmp:
    directory = Path(tmp)
    state = directory / 'slots'
    rootfs = directory / 'current.ext4'
    image = directory / 'candidate.ext4'
    data = directory / 'persistent.ext4'
    priv, pub = directory / 'key.pem', directory / 'key.pub.pem'
    bundle = directory / 'release.tar'
    rootfs.write_bytes(b'confirmed-image' * 1024)
    image.write_bytes(b'candidate-image' * 1024)
    data.write_bytes(b'userdata' * 1024)
    cmd(SIGNER, 'keygen', '--private-key', priv, '--public-key', pub)
    cmd(SIGNER, 'pack', '--image', image, '--private-key', priv,
        '--board', 'qemu-aarch64', '--version', '0.11.0', '--output', bundle)
    def ab(*arguments):
        return cmd(MANAGER, '--state-dir', state, *arguments)
    ab('init', '--image', rootfs, '--version', '0.10.0')
    ab('stage', '--bundle', bundle, '--public-key', pub)

    fail = directory / 'fake-fail.py'
    fail.write_text('import sys\nsys.exit(1)\n')
    try:
        module.check_candidate(state, data, 20, True, fail)
    except subprocess.CalledProcessError:
        pass
    else:
        raise AssertionError('Guest test failure was accepted')
    s = json.loads(ab('status'))
    assert s['confirmed']=='A' and s['pending']=='B' and s['attempts_left']==1
    print('PASS: failed guest self-test does not confirm candidate; boot attempt decremented')

    success = directory / 'fake-pass.py'
    success.write_text('''import sys
args=sys.argv
for expected in ('--rootfs','--data-image','--expected-slot','--expected-version'):
    assert expected in args
assert args[args.index('--expected-slot')+1]=='B'
assert args[args.index('--expected-version')+1]=='0.11.0'
''')
    module.check_candidate(state, data, 20, True, success)
    s = json.loads(ab('status'))
    assert s['confirmed']=='B' and s['pending'] is None
    assert (state/'rootfs-A.ext4').read_bytes()==rootfs.read_bytes()
    print('PASS: confirmed slot changes only after success path; previous image preserved')

    try:
        module.check_candidate(state,data,20,True,success)
    except RuntimeError:
        pass
    else:
        raise AssertionError('Accepted candidate with no pending update')
    print('PASS: cannot re-confirm without a pending update')
print('All A/B guest-acceptance host tests passed.')
