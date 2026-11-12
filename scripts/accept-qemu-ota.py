#!/usr/bin/env python3
"""Safe entry point for VirtualEdge QEMU A/B acceptance.

Preflights signed inputs, refuses concurrent QEMU, then delegates to the
existing disposable A/B test runner. No block-device writes or real OTA.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
PREFLIGHT = ROOT / 'scripts/preflight-qemu-ota.py'
ACCEPT = ROOT / 'scripts/test-qemu-ota.py'
GUEST_TEST = ROOT / 'scripts/test-qemu.py'
AB_MANAGER = ROOT / 'tools/virtualedge_ab.py'


def path_check(state, data, bundle, key, report):
    state, data, bundle, key, report = map(lambda p: Path(p).absolute(),
                                           (state, data, bundle, key, report))
    if not state.is_dir() or state.is_symlink():
        raise ValueError('A/B state directory is missing or is a symlink')
    for label, src in (('data image', data), ('signed bundle', bundle), ('public key', key)):
        if src.is_symlink() or not src.is_file():
            raise ValueError(f'{label} missing or symlinked: {src}')
    if report.exists() or report.is_symlink():
        raise ValueError('report already exists (choose a new filename)')
    if not report.parent.is_dir() or report.parent.is_symlink():
        raise ValueError('report parent directory missing or symlinked')
    protected = [state.resolve(), data.resolve(), bundle.resolve(), key.resolve()]
    for src in protected:
        if report == src or src in report.parents:
            raise ValueError('report destination overlaps a protected input')
    for parent in (report.parent, *report.parent.parents):
        if parent.is_symlink():
            raise ValueError('report path has symlinked ancestor')
    return state, data, bundle, key, report


def qemu_running():
    """Do not copy a live mutable data image while QEMU may be writing it."""
    # /proc excludes our own python process and avoids matching this source name.
    proc = Path('/proc')
    if not proc.is_dir():
        return False
    for entry in proc.iterdir():
        if not entry.name.isdecimal():
            continue
        try:
            name = (entry / 'comm').read_text().strip()
            if name.startswith('qemu-system-'):
                return True
        except (OSError, PermissionError):
            continue
    return False


def validate_report(path, scenario):
    """Require a complete, coherent *real QEMU* boot trace for each scenario.

    Reports are local diagnostic evidence, not signed remote attestation.
    The underlying runner checks guest /proc/cmdline for every boot.
    """
    try:
        report = json.loads(Path(path).read_text())
    except (OSError, ValueError) as exc:
        raise RuntimeError(f'unreadable acceptance evidence: {exc}') from exc
    expected = ['confirm', 'fallback'] if scenario == 'both' else [scenario]
    if report.get('result') != 'pass' or not isinstance(report.get('scenarios'), list):
        raise RuntimeError('QEMU acceptance did not produce a passing report')
    scenarios = report['scenarios']
    if len(scenarios) != len(expected):
        raise RuntimeError('missing acceptance scenarios in report')
    for entry, name in zip(scenarios, expected):
        if (entry.get('scenario') != name or entry.get('result') != 'pass'
                or entry.get('execution') != 'qemu-arm64'
                or entry.get('original_inputs_unchanged') is not True):
            raise RuntimeError('report lacks successful real QEMU evidence')
        boots = entry.get('boots', [])
        if len(boots) != (1 if name == 'confirm' else 3):
            raise RuntimeError('report contains incomplete QEMU boot trace')
        if any(b.get('selftest') != 'pass' or b.get('slot') not in ('A', 'B')
               or not isinstance(b.get('version'), str) or not b['version'] for b in boots):
            raise RuntimeError('report contains failed or invalid QEMU boot evidence')
        # The confirmation and fallback scenarios use separate snapshots of
        # the same starting A/B state. Both must boot the same candidate, and
        # fallback must return to the other confirmed slot/version.
        candidate = boots[0]
        if name == 'confirm':
            if len(boots[0].keys() & {'attempt', 'role'}) != 0:
                raise RuntimeError('unexpected confirmation boot metadata')
        else:
            if not (boots[0].get('attempt') == 1 and boots[1].get('attempt') == 2
                    and boots[2].get('role') == 'fallback'
                    and boots[0]['slot'] == boots[1]['slot']
                    and boots[0]['version'] == boots[1]['version']
                    and boots[2]['slot'] != boots[0]['slot']):
                raise RuntimeError('invalid candidate retry/fallback slot sequence')
        wanted = 'confirmed_after_selftest' if name == 'confirm' else 'not_confirmed_fallback'
        if entry.get('promotion') != wanted:
            raise RuntimeError('report lacks required confirmation/fallback evidence')
    if scenario == 'both':
        confirm, fallback = (entry['boots'] for entry in scenarios)
        if confirm[0]['slot'] != fallback[0]['slot'] or confirm[0]['version'] != fallback[0]['version']:
            raise RuntimeError('confirmation and fallback did not test the same candidate')
    return report


def baseline_smoke_command(state, data, timeout, *, check=subprocess.run):
    """Boot the *confirmed* image before starting candidate/rollback testing.

    The QEMU runner makes private copies of both images. Query the A/B manager
    instead of trusting a guessed slot filename or a version supplied by hand.
    """
    result = check([sys.executable, str(AB_MANAGER), '--state-dir', str(state),
                    'status'], check=True, capture_output=True, text=True)
    status = json.loads(result.stdout)
    if status.get('format') != 2 or status.get('pending') is not None:
        raise RuntimeError('baseline smoke requires clean format-2 A/B state')
    slot = status.get('confirmed')
    if slot not in ('A', 'B'):
        raise RuntimeError('invalid confirmed baseline slot')
    version = status.get('versions', {}).get(slot)
    if not isinstance(version, str) or not version:
        raise RuntimeError('missing confirmed baseline version')
    image = state / f'rootfs-{slot}.ext4'
    if image.is_symlink() or not image.is_file():
        raise RuntimeError('confirmed baseline image is missing or symlinked')
    return [sys.executable, str(GUEST_TEST), '--rootfs', str(image),
            '--data-image', str(data), '--expected-slot', slot,
            '--expected-version', version, '--timeout', str(timeout)]


def execute(args, *, call=subprocess.run, running=qemu_running):
    state, data, bundle, key, report = path_check(
        args.state_dir, args.data_image, args.bundle, args.public_key, args.report)
    if running():
        raise RuntimeError('QEMU is running; power off the guest before acceptance')
    preflight = [sys.executable, str(PREFLIGHT), '--state-dir', str(state),
                 '--data-image', str(data), '--bundle', str(bundle),
                 '--public-key', str(key)]
    print('=== 1/2: Non-mutating signed OTA preflight ===', flush=True)
    call(preflight, check=True)
    if args.preflight_only:
        print('PASS: preflight-only; no QEMU boots or A/B changes performed', flush=True)
        return 0
    if running():
        raise RuntimeError('QEMU became active after preflight; aborting')
    if getattr(args, 'baseline_smoke', False):
        print('=== 2/3: Real ARM64 confirmed-baseline boot smoke test ===', flush=True)
        smoke = baseline_smoke_command(state, data, args.timeout, check=call)
        if running():
            raise RuntimeError('QEMU became active before baseline smoke; aborting')
        call(smoke, check=True)
        if running():
            raise RuntimeError('QEMU still running after baseline smoke; aborting')
        print('PASS: confirmed baseline boot/self-test completed before OTA', flush=True)
    command = [sys.executable, str(ACCEPT), '--state-dir', str(state),
               '--data-image', str(data), '--bundle', str(bundle),
               '--public-key', str(key), '--scenario', args.scenario,
               '--timeout', str(args.timeout), '--report', str(report)]
    print('=== OTA: Disposable actual ARM64 QEMU acceptance ===', flush=True)
    call(command, check=True)
    validate_report(report, args.scenario)
    print(f'PASS: QEMU acceptance completed; report: {report}', flush=True)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-dir', type=Path, default=ROOT / 'out/ab')
    parser.add_argument('--data-image', type=Path, default=ROOT / 'out/persistent/virtualedge-data.ext4')
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--public-key', type=Path, required=True)
    parser.add_argument('--scenario', choices=('confirm', 'fallback', 'both'), default='both')
    parser.add_argument('--timeout', type=int, default=240)
    parser.add_argument('--report', type=Path, required=True,
                        help='New JSON report filename (must not exist)')
    parser.add_argument('--preflight-only', action='store_true')
    parser.add_argument('--skip-baseline-smoke', action='store_true',
                        help='Skip the extra real QEMU baseline boot (not recommended for first acceptance)')
    args = parser.parse_args(argv)
    args.baseline_smoke = not args.skip_baseline_smoke
    if not 10 <= args.timeout <= 1200:
        parser.error('timeout must be between 10 and 1200 seconds')
    try:
        return execute(args)
    except (ValueError, RuntimeError, OSError, subprocess.CalledProcessError) as exc:
        print(f'FAIL: QEMU OTA acceptance: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
