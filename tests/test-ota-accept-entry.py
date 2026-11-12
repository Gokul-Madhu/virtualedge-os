#!/usr/bin/env python3
"""Fast behavioral tests: acceptance entry point must not mutate input paths."""
import argparse
import importlib.util
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('entry', ROOT / 'scripts/accept-qemu-ota.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

with tempfile.TemporaryDirectory() as temp:
    root = Path(temp)
    state = root / 'ab'
    state.mkdir()
    data, bundle, key, report = [root / n for n in ('data.ext4', 'bundle.tar', 'key.pub', 'report.json')]
    for f in (data, bundle, key):
        f.write_bytes(b'test')
    args = argparse.Namespace(state_dir=state, data_image=data, bundle=bundle,
                              public_key=key, report=report, scenario='both',
                              timeout=180, preflight_only=False)
    history = []
    def fake_call(cmd, **kwargs):
        assert kwargs['check'] is True
        history.append(cmd)
        if 'test-qemu-ota.py' in cmd[1]:
            import json
            report.write_text(json.dumps({"result":"pass", "scenarios":[
                {"scenario":"confirm", "result":"pass", "execution":"qemu-arm64",
                 "original_inputs_unchanged":True, "promotion":"confirmed_after_selftest",
                 "boots":[{"slot":"B", "version":"0.35.0", "selftest":"pass"}]},
                {"scenario":"fallback", "result":"pass", "execution":"qemu-arm64",
                 "original_inputs_unchanged":True, "promotion":"not_confirmed_fallback",
                 "boots":[{"slot":"B", "version":"0.35.0", "selftest":"pass", "attempt":1}, {"slot":"B", "version":"0.35.0", "selftest":"pass", "attempt":2},
                          {"slot":"A", "version":"0.34.0", "selftest":"pass", "role":"fallback"}]}
            ]}))
    mod.execute(args, call=fake_call, running=lambda: False)
    assert len(history)==2
    assert history[0][1].endswith('preflight-qemu-ota.py')
    assert history[1][1].endswith('test-qemu-ota.py')
    assert history[1][history[1].index('--scenario')+1]=='both'
    print('PASS: preflight runs before disposable QEMU acceptance and a report is required')
    import json
    fake = json.loads(report.read_text())
    fake['scenarios'][0]['execution'] = 'host-test-stub'
    report.write_text(json.dumps(fake))
    try:
        mod.validate_report(report, 'both')
    except RuntimeError:
        pass
    else:
        raise AssertionError('stub results accepted as real ARM64 evidence')
    print('PASS: host stubs cannot be reported as successful real QEMU boots')
    fake['scenarios'][0]['execution'] = 'qemu-arm64'
    fake['scenarios'][1]['boots'].pop()
    report.write_text(json.dumps(fake))
    try:
        mod.validate_report(report, 'both')
    except RuntimeError:
        pass
    else:
        raise AssertionError('incomplete fallback accepted')
    print('PASS: incomplete fallback trace rejected')
    report.unlink()
    history.clear()
    args.preflight_only = True
    mod.execute(args, call=fake_call, running=lambda: False)
    assert len(history)==1 and not report.exists()
    print('PASS: preflight-only does not boot QEMU or create acceptance report')
    args.preflight_only = False
    history.clear()
    try:
        mod.execute(args, call=fake_call, running=lambda: True)
    except RuntimeError:
        assert not history
    else:
        raise AssertionError('running QEMU permitted')
    print('PASS: running QEMU blocks acceptance before any commands')
    try:
        mod.path_check(state,data,bundle,key,data)
    except ValueError:
        pass
    else:
        raise AssertionError('report overwrites an input')
    print('PASS: report cannot overwrite protected inputs')
    report.write_text('old-report')
    try:
        mod.path_check(state,data,bundle,key,report)
    except ValueError:
        assert report.read_text()=='old-report'
    else:
        raise AssertionError('report overwrite permitted')
    report.unlink()
    print('PASS: existing acceptance reports are never overwritten')
    (root/'link-key').symlink_to(key)
    try:
        mod.path_check(state,data,bundle,root/'link-key',report)
    except ValueError:
        pass
    else:
        raise AssertionError('symlinked trust key accepted')
    print('PASS: symlinked trust keys are rejected')
    def bad_call(cmd, **kwargs):
        raise __import__('subprocess').CalledProcessError(1, cmd)
    history.clear()
    try:
        mod.execute(args, call=bad_call, running=lambda: False)
    except __import__('subprocess').CalledProcessError:
        assert not report.exists()
    else:
        raise AssertionError('failed preflight allowed acceptance')
    print('PASS: failed preflight never runs QEMU')
print('All OTA entry-point safety tests passed.')
