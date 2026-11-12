#!/usr/bin/env python3
"""v0.30: disposable QEMU A/B OTA acceptance, not an on-device updater.

Exercises signed staging, candidate guest boot/self-test, explicit confirmation,
and two unconfirmed attempts followed by verified fallback. NEVER modifies the
supplied A/B state or persistent data image. Requires a real built QEMU guest.
"""
import argparse
import hashlib
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
MANAGER = ROOT / 'tools/virtualedge_ab.py'
GUEST_TEST = ROOT / 'scripts/test-qemu.py'
MAX_IMAGE = 1024 * 1024 * 1024


def safe_image(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= MAX_IMAGE:
        raise ValueError(f'unsafe or missing image: {path}')
    return path


def sha256_file(path):
    """Bounded SHA-256 of a regular file; avoid symlinked source images."""
    path = safe_image(path)
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def source_fingerprints(original, data):
    """Record exact original bytes for a later non-mutation assertion."""
    state = original / 'state.json'
    if state.is_symlink() or not state.is_file() or state.stat().st_size > 4096:
        raise ValueError('unsafe original A/B state metadata')
    original_state = status(original)
    fingerprints = {'state.json': sha256_file(state),
                    'data.ext4': sha256_file(data)}
    for slot in ('A', 'B'):
        if original_state['versions'][slot] is not None:
            fingerprints[f'rootfs-{slot}.ext4'] = sha256_file(original / f'rootfs-{slot}.ext4')
    return fingerprints


def report_destination_safe(destination, state_dir, data_image, bundle, public_key):
    """Reject report paths inside input trees and paths that alias input files."""
    destination = Path(destination).absolute()
    protected = [Path(state_dir).resolve(), Path(data_image).resolve(),
                 Path(bundle).resolve(), Path(public_key).resolve()]
    for source in protected:
        if destination == source or source in destination.parents:
            raise ValueError('report destination overlaps protected OTA input')
    # Do not permit an output directory that is itself a symlink, including
    # an ancestor: the report can otherwise escape to an input location.
    for ancestor in (destination.parent, *destination.parent.parents):
        if ancestor.is_symlink():
            raise ValueError('report destination has symlinked ancestor')
    # Existing hard links to protected files are rejected by write_report.
    return destination


def write_report(path, report):
    """Write a machine-readable acceptance report without following a target symlink."""
    destination = Path(path)
    if destination.is_symlink() or destination.exists():
        raise ValueError('report already exists; refusing to overwrite it')
    if not destination.parent.is_dir() or destination.parent.is_symlink():
        raise ValueError('report parent directory must exist and not be a symlink')
    fd, temporary = tempfile.mkstemp(prefix='.ve-ota-report-', dir=destination.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            os.fchmod(stream.fileno(), 0o600)
            json.dump(report, stream, indent=2, sort_keys=True)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        # link() is non-overwriting; rename would silently replace a report.
        os.link(temporary, destination, follow_symlinks=False)
        parent_fd = os.open(destination.parent, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def run_manager(state, *args):
    result = subprocess.run([sys.executable, str(MANAGER), '--state-dir', str(state), *args],
                            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            check=True, timeout=100)
    return result.stdout.strip()


def status(state):
    return json.loads(run_manager(state, 'status'))


def guest_boot(state, disk, timeout, runner):
    """Boot selected A/B slot; consumes an attempt if candidate selected."""
    selected = run_manager(state, 'boot').split(' ', 2)
    if len(selected) != 3:
        raise RuntimeError('unexpected A/B boot selection')
    slot, version, image = selected
    expected = state / f'rootfs-{slot}.ext4'
    if Path(image).resolve() != expected.resolve():
        raise RuntimeError('boot selection escaped disposable A/B directory')
    safe_image(expected)
    runner(slot, version, expected, disk, timeout)
    return slot, version


def qemu_runner(slot, version, rootfs, data, timeout):
    subprocess.run([sys.executable, str(GUEST_TEST), '--rootfs', str(rootfs),
                    '--data-image', str(data), '--expected-slot', slot,
                    '--expected-version', version, '--timeout', str(timeout)],
                   check=True, timeout=timeout + 20)


def prepare_state(base, original):
    """Copy only recognized regular state files, never mutable originals or symlinks."""
    if original.is_symlink() or not original.is_dir():
        raise ValueError('A/B directory must exist and not be a symlink')
    source = status(original)
    if source['format'] != 2 or source['pending'] is not None:
        raise ValueError('requires format-2 A/B state with no pending update')
    run_manager(original, 'audit')
    state = base / 'ab'
    state.mkdir(mode=0o700)
    meta = safe_image(original / 'state.json')
    if meta.stat().st_size > 4096:
        raise ValueError('A/B metadata too large')
    shutil.copyfile(meta, state / 'state.json')
    for slot in ('A', 'B'):
        if source['versions'][slot] is not None:
            shutil.copyfile(safe_image(original / f'rootfs-{slot}.ext4'),
                            state / f'rootfs-{slot}.ext4')
    run_manager(state, 'audit')
    return state, source


def scenario(original, data, bundle, key, timeout, confirm, runner=qemu_runner, evidence=None):
    """Exercise one scenario; runner injection exists only for host unit tests."""
    safe_image(data)
    safe_image(bundle)
    safe_image(key)
    baseline_files = source_fingerprints(original, data)
    if evidence is not None:
        evidence['input_sha256'] = baseline_files.copy()
        evidence['scenario'] = 'confirm' if confirm else 'fallback'
    if evidence is not None:
        evidence['boots'] = []
        evidence['promotion'] = 'not_attempted'
        evidence['execution'] = 'qemu-arm64' if runner is qemu_runner else 'host-test-stub'
    try:
        _run_scenario(original, data, bundle, key, timeout, confirm, runner, evidence)
    finally:
        # This includes the failure path: a failing test still must never mutate
        # the caller's A/B images, metadata or persistent data volume.
        if source_fingerprints(original, data) != baseline_files:
            raise RuntimeError('original A/B metadata, slot image or data disk changed during acceptance')
        if evidence is not None:
            evidence['original_inputs_unchanged'] = True


def _run_scenario(original, data, bundle, key, timeout, confirm, runner, evidence=None):
    with tempfile.TemporaryDirectory(prefix='virtualedge-ota-accept-') as temp:
        base = Path(temp)
        state, baseline = prepare_state(base, original)
        disk = base / 'test-data.ext4'
        shutil.copyfile(data, disk)
        run_manager(state, 'stage', '--bundle', str(bundle), '--public-key', str(key))
        staged = status(state)
        pending = staged['pending']
        if pending is None or staged['confirmed'] != baseline['confirmed'] or staged['attempts_left'] != 2:
            raise RuntimeError('unexpected staged A/B state')
        run_manager(state, 'audit')
        if confirm:
            try:
                slot, version = guest_boot(state, disk, timeout, runner)
                if evidence is not None:
                    evidence['boots'].append({'slot': slot, 'version': version, 'selftest': 'pass'})
                if slot != pending:
                    raise RuntimeError('trial boot selected wrong slot')
            except Exception:
                # Never confirm a guest that failed its self-test.
                if status(state)['confirmed'] != baseline['confirmed']:
                    raise RuntimeError('failed guest boot unexpectedly promoted candidate')
                raise
            run_manager(state, 'confirm', '--slot', slot, '--guest-selftest-passed')
            if evidence is not None:
                evidence['promotion'] = 'confirmed_after_selftest'
            result = status(state)
            if result['confirmed'] != pending or result['pending'] is not None:
                raise RuntimeError('candidate promotion failed')
            run_manager(state, 'audit')
            print(f'PASS: disposable QEMU candidate {slot} {version} confirmed after guest self-test', flush=True)
        else:
            # A/B attempts are consumed by boot selection; no explicit confirmation.
            # Checking real candidate boots twice is important: both attempts must pass
            # guest self-test before a later boot demonstrates fallback selection.
            for attempt in (1, 2):
                slot, version = guest_boot(state, disk, timeout, runner)
                if evidence is not None:
                    evidence['boots'].append({'slot': slot, 'version': version, 'selftest': 'pass', 'attempt': attempt})
                if slot != pending:
                    raise RuntimeError(f'attempt {attempt} did not boot pending slot')
            slot, version = guest_boot(state, disk, timeout, runner)
            if evidence is not None:
                evidence['boots'].append({'slot': slot, 'version': version, 'selftest': 'pass', 'role': 'fallback'})
                evidence['promotion'] = 'not_confirmed_fallback'
            if slot != baseline['confirmed'] or version != baseline['versions'][slot]:
                raise RuntimeError('unconfirmed candidate failed to fall back')
            result = status(state)
            if result['confirmed'] != baseline['confirmed'] or result['pending'] is not None:
                raise RuntimeError('fallback modified confirmed slot unexpectedly')
            run_manager(state, 'audit')
            print('PASS: two unconfirmed trial boots then QEMU fallback to verified confirmed slot', flush=True)
        # Original state and data disk were only read; all guest boots receive
        # their own copies via test-qemu.py.
        if status(original) != baseline:
            raise RuntimeError('original A/B state was modified')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-dir', type=Path, default=ROOT / 'out/ab')
    parser.add_argument('--data-image', type=Path, default=ROOT / 'out/persistent/virtualedge-data.ext4')
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--public-key', type=Path, required=True)
    parser.add_argument('--timeout', type=int, default=180)
    parser.add_argument('--scenario', choices=('confirm', 'fallback', 'both'), default='both')
    parser.add_argument('--report', type=Path,
                        help='Write a new JSON acceptance report (never overwrites existing reports)')
    args = parser.parse_args()
    if not 10 <= args.timeout <= 1200:
        parser.error('--timeout must be between 10 and 1200')
    report = {'schema': 2, 'release': '0.32', 'result': 'fail',
              'verification': 'QEMU guest (only if this command finishes successfully)',
              'created_at_utc': datetime.now(timezone.utc).isoformat(),
              'scenarios': []}
    error = None
    try:
        for confirm in ((True, False) if args.scenario == 'both' else (args.scenario == 'confirm',)):
            entry = {'result': 'fail', 'scenario': 'confirm' if confirm else 'fallback'}
            report['scenarios'].append(entry)
            try:
                scenario(args.state_dir.absolute(), args.data_image.absolute(),
                         args.bundle.absolute(), args.public_key.absolute(), args.timeout,
                         confirm, evidence=entry)
                entry['result'] = 'pass'
            except Exception as exc:
                entry['error'] = str(exc)
                raise
        report['result'] = 'pass'
        print('PASS: isolated v0.31 OTA acceptance complete; original inputs SHA-256 checked')
    except (ValueError, RuntimeError, OSError, subprocess.CalledProcessError,
            subprocess.TimeoutExpired) as exc:
        error = str(exc)
        report['error'] = error
        print(f'FAIL: OTA acceptance: {exc}', file=sys.stderr)
    if args.report is not None:
        try:
            report_destination_safe(args.report, args.state_dir, args.data_image,
                                    args.bundle, args.public_key)
            write_report(args.report, report)
            print(f'Acceptance report: {args.report}')
        except (OSError, ValueError) as exc:
            print(f'FAIL: unable to write acceptance report: {exc}', file=sys.stderr)
            return 1
    return 1 if error is not None else 0


if __name__ == '__main__':
    sys.exit(main())
