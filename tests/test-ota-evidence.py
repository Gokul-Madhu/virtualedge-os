#!/usr/bin/env python3
"""v0.31 host evidence checks; no QEMU boot is claimed."""
import importlib.util
import json
from pathlib import Path
from unittest.mock import patch
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('ve_ota_evidence', ROOT / 'scripts/test-qemu-ota.py')
OTA = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(OTA)
AB = ROOT / 'tools/virtualedge_ab.py'

with tempfile.TemporaryDirectory() as temp:
    base = Path(temp)
    img = base / 'old.ext4'
    img.write_bytes(b'OLDOS' * 200)
    data = base / 'data.ext4'
    data.write_bytes(b'DATA' * 200)
    bundle = base / 'bundle.tar'
    bundle.write_bytes(b'not-important-to-mocked-tests')
    key = base / 'trusted.pem'
    key.write_bytes(b'test-key')
    state = base / 'ab'
    result = subprocess.run([sys.executable, str(AB), '--state-dir', str(state), 'init',
                             '--image', str(img), '--version', '0.30.0'],
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    original_metadata = (state / 'state.json').read_bytes()
    original_slot = (state / 'rootfs-A.ext4').read_bytes()
    evidence = {}
    with patch.object(OTA, '_run_scenario', lambda *_: None):
        OTA.scenario(state, data, bundle, key, 30, True, evidence=evidence)
    assert evidence['original_inputs_unchanged'] is True
    assert evidence['scenario'] == 'confirm'
    assert len(evidence['input_sha256']['state.json']) == 64
    print('PASS: hash evidence is recorded for unchanged A/B metadata, slot and persistent data')

    def change_data(*_):
        data.write_bytes(b'MODIFIED-DATA')
    with patch.object(OTA, '_run_scenario', change_data):
        try:
            OTA.scenario(state, data, bundle, key, 30, True)
        except RuntimeError as exc:
            assert 'original A/B' in str(exc)
        else:
            raise AssertionError('original data corruption went undetected')
    data.write_bytes(b'DATA' * 200)
    print('PASS: detects unexpected mutation of original persistent data')

    def change_slot(*_):
        (state / 'rootfs-A.ext4').write_bytes(b'MODIFIED-ROOTFS')
    with patch.object(OTA, '_run_scenario', change_slot):
        try:
            OTA.scenario(state, data, bundle, key, 30, True)
        except RuntimeError as exc:
            assert 'original A/B' in str(exc)
        else:
            raise AssertionError('original slot mutation went undetected')
    (state / 'rootfs-A.ext4').write_bytes(original_slot)
    assert (state / 'state.json').read_bytes() == original_metadata
    print('PASS: detects unexpected mutation of original confirmed slot')

    report = base / 'acceptance.json'
    OTA.write_report(report, {'schema': 1, 'result': 'pass', 'scenarios': [evidence]})
    assert json.loads(report.read_text())['result'] == 'pass'
    assert report.stat().st_mode & 0o777 == 0o600
    try:
        OTA.write_report(report, {'result': 'fail'})
    except ValueError:
        pass
    else:
        raise AssertionError('existing report overwritten')
    print('PASS: secure JSON report creation refuses overwrite')

    symlink = base / 'unsafe-report.json'
    symlink.symlink_to(report)
    try:
        OTA.write_report(symlink, {})
    except ValueError:
        pass
    else:
        raise AssertionError('symlinked report destination accepted')
    print('PASS: symlink report target refused')
print('All v0.31 OTA evidence checks passed (no QEMU guest run)')
