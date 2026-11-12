#!/usr/bin/env python3
"""Fast host tests for QEMU panic detection and strict A/B report sequence."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parents[1]
def load(path, name):
    spec=importlib.util.spec_from_file_location(name, ROOT/path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
qemu=load('scripts/test-qemu.py','qemu_test')
gate=load('scripts/accept-qemu-ota.py','ota_gate')
for message in [
    'Kernel panic - not syncing: No working init found.',
    'VFS: Unable to mount root fs on unknown-block(0,0)',
    'No working init found',
]:
    try: qemu.check_boot_failure(message)
    except RuntimeError: pass
    else: raise AssertionError(f'Panic was not detected: {message}')
qemu.check_boot_failure('PASS: VirtualEdge QEMU guest service')
print('PASS: QEMU fatal boot errors reported early, ordinary boot output accepted')

report={'result':'pass','scenarios':[
    {'scenario':'confirm','result':'pass','execution':'qemu-arm64',
     'original_inputs_unchanged':True,'promotion':'confirmed_after_selftest',
     'boots':[{'slot':'B','version':'0.35.0','selftest':'pass'}]},
    {'scenario':'fallback','result':'pass','execution':'qemu-arm64',
     'original_inputs_unchanged':True,'promotion':'not_confirmed_fallback',
     'boots':[{'slot':'B','version':'0.35.0','selftest':'pass','attempt':1},
              {'slot':'B','version':'0.35.0','selftest':'pass','attempt':2},
              {'slot':'A','version':'0.34.0','selftest':'pass','role':'fallback'}]},
]}
with tempfile.TemporaryDirectory() as tmp:
    f=Path(tmp)/'evidence.json'
    def check(data, expected):
        f.write_text(json.dumps(data))
        try: gate.validate_report(f,'both')
        except RuntimeError:
            if expected: raise
            return
        if not expected: raise AssertionError('Invalid boot evidence was accepted')
    check(report,True)
    variants=[]
    a=copy.deepcopy(report);a['scenarios'][1]['boots'][1]['slot']='A';variants.append(a)
    a=copy.deepcopy(report);a['scenarios'][1]['boots'][1]['attempt']=1;variants.append(a)
    a=copy.deepcopy(report);a['scenarios'][1]['boots'][2]['slot']='B';variants.append(a)
    a=copy.deepcopy(report);a['scenarios'][1]['boots'][2]['role']='candidate';variants.append(a)
    a=copy.deepcopy(report);a['scenarios'][1]['boots'][1]['version']='0.99.0';variants.append(a)
    a=copy.deepcopy(report);a['scenarios'][0]['boots'][0]['version']='0.99.0';variants.append(a)
    a=copy.deepcopy(report);a['scenarios'][0]['boots'][0].pop('version');variants.append(a)
    a=copy.deepcopy(report);a['scenarios'][1]['execution']='host-test-stub';variants.append(a)
    a=copy.deepcopy(report);a['scenarios'][1]['original_inputs_unchanged']=False;variants.append(a)
    for variant in variants:check(variant,False)
print(f'PASS: strict A/B trace validation rejects {len(variants)} invalid reports')
