#!/usr/bin/env python3
"""v0.32 host-only A/B evidence trace. Stub runner is NOT a QEMU guest."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('ve_ota_trace', ROOT / 'scripts/test-qemu-ota.py')
ota = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ota)


def command(script, *args):
    result = subprocess.run([sys.executable, str(ROOT / script), *map(str, args)],
                            capture_output=True, text=True, timeout=40)
    assert result.returncode == 0, result.stderr

with tempfile.TemporaryDirectory() as tmp:
    base = Path(tmp)
    data, old, new = base / 'data.ext4', base / 'old.ext4', base / 'new.ext4'
    data.write_bytes(b'D' * 4096)
    old.write_bytes(b'A' * 4096)
    new.write_bytes(b'B' * 4096)
    private, public = base / 'private.pem', base / 'public.pem'
    bundle, state = base / 'update.tar', base / 'ab'
    command('tools/virtualedge_release.py', 'keygen', '--private-key', private, '--public-key', public)
    command('tools/virtualedge_release.py', 'pack', '--image', new, '--private-key', private,
            '--board', 'qemu-aarch64', '--version', '0.32.0', '--output', bundle)
    command('tools/virtualedge_ab.py', '--state-dir', state, 'init', '--image', old, '--version', '0.31.0')
    boots = []
    def stub(slot, version, image, disk, timeout):
        boots.append((slot, version))

    confirm = {}
    ota.scenario(state, data, bundle, public, 30, True, runner=stub, evidence=confirm)
    assert confirm['execution'] == 'host-test-stub'
    assert confirm['promotion'] == 'confirmed_after_selftest'
    assert [(b['slot'], b['version']) for b in confirm['boots']] == [('B','0.32.0')]
    assert confirm['original_inputs_unchanged']
    print('PASS: confirmation trace records selected candidate slot and simulated health pass', flush=True)

    fallback = {}
    ota.scenario(state, data, bundle, public, 30, False, runner=stub, evidence=fallback)
    assert fallback['promotion'] == 'not_confirmed_fallback'
    assert [b['slot'] for b in fallback['boots']] == ['B','B','A']
    assert [b.get('attempt') for b in fallback['boots']][:2] == [1, 2]
    print('PASS: fallback trace records two attempts and confirmed-slot return', flush=True)

    def fail(*args):
        raise RuntimeError('guest rejected candidate')
    broken = {}
    with patch.object(ota, '_run_scenario', side_effect=RuntimeError('guest rejected candidate')):
      try:
        ota.scenario(state, data, bundle, public, 30, True, runner=fail, evidence=broken)
      except RuntimeError as exc:
        assert 'guest rejected' in str(exc)
      else:
        raise AssertionError('failed guest unexpectedly accepted')
    assert broken['promotion'] == 'not_attempted'
    assert broken['original_inputs_unchanged']
    print('PASS: failed guest test cannot produce promotion evidence', flush=True)

    for unsafe in [state / 'report.json', data, bundle, public]:
        try:
            ota.report_destination_safe(unsafe, state, data, bundle, public)
        except ValueError:
            pass
        else:
            raise AssertionError(f'protected input accepted as report: {unsafe}')
    print('PASS: report cannot overwrite or live within protected inputs', flush=True)

    output = base / 'evidence.json'
    assert ota.report_destination_safe(output, state, data, bundle, public) == output
    ota.write_report(output, {'schema': 2, 'result': 'pass', 'scenarios': [confirm, fallback]})
    assert json.loads(output.read_text())['scenarios'][1]['boots'][2]['slot'] == 'A'
    assert output.stat().st_mode & 0o777 == 0o600
    print('PASS: mode-0600 JSON report contains reproducible boot trace', flush=True)

print('All v0.32 OTA trace tests passed (host stub, NOT real QEMU)')
