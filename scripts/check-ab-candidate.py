#!/usr/bin/env python3
"""QEMU-only A/B candidate acceptance; optionally confirm after guest self-test.

This runs on the trusted HOST, not inside the guest. It does not prove secure
boot, power-loss durability, or firmware authenticity at boot time.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
MANAGER = ROOT / 'tools/virtualedge_ab.py'
QEMU_TEST = ROOT / 'scripts/test-qemu.py'
DEFAULT_STATE = ROOT / 'out/ab'
DEFAULT_DATA = ROOT / 'out/persistent/virtualedge-data.ext4'


def manager(state, *args):
    return subprocess.run(
        [sys.executable, str(MANAGER), '--state-dir', str(state), *args],
        check=True, text=True, capture_output=True).stdout.strip()


def check_candidate(state, data, timeout, confirm=False, test_script=QEMU_TEST):
    # This intentionally consumes one pending boot attempt; failed tests do
    # not mark success. The host administrator may retry remaining attempts.
    current = json.loads(manager(state, 'status'))
    if current['pending'] is None:
        raise RuntimeError('No pending update; stage a verified candidate first')
    if not data.is_file() or data.is_symlink():
        raise RuntimeError('Missing or unsafe persistent QEMU disk')

    selected = manager(state, 'boot').split(' ', 2)
    if len(selected) != 3:
        raise RuntimeError('Invalid slot selector response')
    slot, version, rootfs = selected
    if slot != current['pending'] or version != current['versions'][slot]:
        raise RuntimeError('Candidate no longer selected; check A/B state')
    rootfs_path = Path(rootfs)
    if rootfs_path.resolve() != (state / f'rootfs-{slot}.ext4').resolve():
        raise RuntimeError('Selected slot path unexpected')
    args = [sys.executable, str(test_script), '--timeout', str(timeout),
            '--rootfs', str(rootfs_path), '--data-image', str(data),
            '--expected-slot', slot, '--expected-version', version]
    print(f'QEMU validating candidate slot {slot}, version {version}', flush=True)
    subprocess.run(args, check=True)
    if confirm:
        latest = json.loads(manager(state, 'status'))
        if latest['pending'] != slot or latest['versions'][slot] != version:
            raise RuntimeError('A/B state changed during validation; refusing confirmation')
        manager(state, 'confirm', '--slot', slot, '--guest-selftest-passed')
        print(f'PASS: Host confirmed QEMU candidate slot {slot} after guest self-test', flush=True)
    else:
        print('PASS: QEMU guest self-test. Candidate remains pending (no confirmation requested).', flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--state-dir', type=Path, default=DEFAULT_STATE)
    p.add_argument('--data-image', type=Path, default=DEFAULT_DATA)
    p.add_argument('--timeout', type=int, default=180)
    p.add_argument('--confirm-on-pass', action='store_true')
    args = p.parse_args()
    if not 10 <= args.timeout <= 1200:
        p.error('timeout must be between 10 and 1200 seconds')
    try:
        check_candidate(args.state_dir.resolve(), args.data_image.resolve(),
                        args.timeout, args.confirm_on_pass)
    except (RuntimeError, OSError, ValueError, subprocess.CalledProcessError) as e:
        print(f'FAIL: Candidate NOT confirmed: {e}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
