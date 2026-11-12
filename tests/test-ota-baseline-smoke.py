#!/usr/bin/env python3
"""Host-only tests of real-baseline QEMU boot gate. No QEMU required."""
import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('gate', ROOT/'scripts/accept-qemu-ota.py')
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)

with tempfile.TemporaryDirectory() as tmp:
    base=Path(tmp)
    state=base/'ab';state.mkdir()
    (state/'rootfs-A.ext4').write_bytes(b'dummy image')
    data=base/'data.ext4';data.write_bytes(b'data')
    bundle=base/'bundle.tar';bundle.write_bytes(b'bundle')
    key=base/'public.pem';key.write_bytes(b'key')
    report=base/'report.json'
    def status_call(command, **kw):
        assert command[-1]=='status' and kw['check']
        return subprocess.CompletedProcess(command, 0, stdout=json.dumps({
            'format':2, 'confirmed':'A', 'pending':None,
            'versions':{'A':'0.35.0', 'B':None}}))
    cmd=gate.baseline_smoke_command(state, data, 240, check=status_call)
    assert cmd[1].endswith('test-qemu.py')
    assert cmd[cmd.index('--rootfs')+1]==str(state/'rootfs-A.ext4')
    assert cmd[cmd.index('--data-image')+1]==str(data)
    assert cmd[cmd.index('--expected-slot')+1]=='A'
    assert cmd[cmd.index('--expected-version')+1]=='0.35.0'
    print('PASS: confirmed baseline slot/version passed to real QEMU runner')

    (state/'rootfs-A.ext4').unlink()
    (state/'rootfs-A.ext4').symlink_to(bundle)
    try: gate.baseline_smoke_command(state,data,240,check=status_call)
    except RuntimeError: pass
    else: raise AssertionError('symlinked baseline accepted')
    (state/'rootfs-A.ext4').unlink()
    (state/'rootfs-A.ext4').write_bytes(b'image')
    print('PASS: symlinked baseline image rejected')

    def pending_call(command,**kw):
        r=status_call(command,**kw)
        d=json.loads(r.stdout);d['pending']='B'
        r.stdout=json.dumps(d)
        return r
    try: gate.baseline_smoke_command(state,data,240,check=pending_call)
    except RuntimeError: pass
    else: raise AssertionError('pending update accepted as baseline')
    print('PASS: pending state rejected before baseline boot')

    args=argparse.Namespace(state_dir=state,data_image=data,bundle=bundle,public_key=key,
        report=report,scenario='both',timeout=240,preflight_only=False,baseline_smoke=True)
    events=[]
    def failed_baseline(command, **kwargs):
        events.append(command)
        if command[-1]=='status': return status_call(command,**kwargs)
        if command[1].endswith('test-qemu.py'):
            raise subprocess.CalledProcessError(1,command)
        assert command[1].endswith('preflight-qemu-ota.py')
    try: gate.execute(args,call=failed_baseline,running=lambda:False)
    except subprocess.CalledProcessError: pass
    else: raise AssertionError('failed baseline did not block acceptance')
    assert len(events)==3 and not report.exists()
    assert not any(c[1].endswith('test-qemu-ota.py') for c in events)
    print('PASS: failed baseline boot blocks OTA acceptance and report creation')

    args.preflight_only=True
    events.clear()
    gate.execute(args,call=failed_baseline,running=lambda:False)
    assert len(events)==1
    print('PASS: preflight-only skips baseline QEMU smoke')
print('All OTA baseline smoke host tests passed.')

# A valid baseline smoke must finish before invoking the OTA runner.
with tempfile.TemporaryDirectory() as tmp:
    base=Path(tmp)
    state=base/'ab';state.mkdir()
    (state/'rootfs-B.ext4').write_bytes(b'baseline')
    data=base/'data.ext4';data.write_bytes(b'data')
    bundle=base/'bundle.tar';bundle.write_bytes(b'bundle')
    key=base/'key.pub';key.write_bytes(b'key')
    report=base/'result.json'
    args=argparse.Namespace(state_dir=state,data_image=data,bundle=bundle,
        public_key=key,report=report,scenario='confirm',timeout=240,
        preflight_only=False,baseline_smoke=True)
    calls=[]
    def good_call(command, **kwargs):
        calls.append(command)
        if command[-1]=='status':
            return subprocess.CompletedProcess(command,0,stdout=json.dumps({
                'format':2,'confirmed':'B','pending':None,
                'versions':{'A':None,'B':'0.35.0'}}))
        if command[1].endswith('test-qemu-ota.py'):
            report.write_text(json.dumps({'result':'pass','scenarios':[
                {'scenario':'confirm','result':'pass','execution':'qemu-arm64',
                 'original_inputs_unchanged':True,'promotion':'confirmed_after_selftest',
                 'boots':[{'slot':'A','version':'0.36.0','selftest':'pass'}]}]}))
        return subprocess.CompletedProcess(command,0)
    gate.execute(args,call=good_call,running=lambda:False)
    names=[c[1].split('/')[-1] for c in calls]
    assert names==['preflight-qemu-ota.py','virtualedge_ab.py','test-qemu.py','test-qemu-ota.py'],names
    print('PASS: real baseline boot gate precedes disposable OTA acceptance')
