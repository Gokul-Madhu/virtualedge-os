#!/usr/bin/env python3
"""v0.18 secret-disk isolation tests (host-only; live ext4/ARM64 tests separate)."""
import importlib.util
from pathlib import Path
from unittest import TestCase, main, mock
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('tls_image', ROOT/'tools/virtualedge_tls_image.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class DiskTests(TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.addCleanup(self.t.cleanup)
        self.tmp = Path(self.t.name)
        self.creds = self.tmp/'creds'
        self.creds.mkdir(mode=0o700)
        for f in module.FILES:
            p = self.creds/f
            p.write_text(f + ' test content')
            p.chmod(0o600)
        self.out = self.tmp/'tls.ext4'

    def fake_run(self, args, **kwargs):
        if '-d' in args:
            # Mimic image preparation, without relying on mkfs.ext4 being installed.
            Path(args[-1]).write_bytes(b'EXT4-TEST-FIXTURE')
        return subprocess.CompletedProcess(args, 0, '', '')

    def test_disk_created_exclusively(self):
        with mock.patch.object(module.shutil, 'which', return_value='/usr/sbin/mkfs.ext4'), \
             mock.patch.object(module.subprocess, 'run', side_effect=self.fake_run):
            module.create(self.creds, self.out)
        self.assertEqual(self.out.read_bytes(), b'EXT4-TEST-FIXTURE')
        self.assertEqual(self.out.stat().st_mode & 0o777, 0o600)

    def test_existing_disk_not_overwritten(self):
        self.out.write_bytes(b'critical existing data')
        with self.assertRaisesRegex(ValueError, 'Refusing to overwrite'):
            module.create(self.creds, self.out)
        self.assertEqual(self.out.read_bytes(), b'critical existing data')

    def test_missing_key_rejected(self):
        (self.creds/'server.key').unlink()
        with self.assertRaisesRegex(ValueError, 'Missing or symlinked'):
            module.create(self.creds, self.out)

    def test_symlink_key_rejected(self):
        (self.creds/'server.key').unlink()
        (self.creds/'server.key').symlink_to(self.creds/'ca.pem')
        with self.assertRaisesRegex(ValueError, 'Missing or symlinked'):
            module.create(self.creds, self.out)

    def test_audit_failure_rejected(self):
        with mock.patch.object(module.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1, '', 'invalid cert')):
            with self.assertRaisesRegex(ValueError, 'audit failed'):
                module.create(self.creds, self.out)
        self.assertFalse(self.out.exists())

    def test_no_mkfs_rejected(self):
        with mock.patch.object(module.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, '', '')), \
             mock.patch.object(module.shutil, 'which', return_value=None):
            with self.assertRaisesRegex(RuntimeError, 'mkfs.ext4 missing'):
                module.create(self.creds, self.out)

    def test_service_requires_separate_disk(self):
        service = (ROOT/'board/virtualedge/rootfs-overlay/etc/init.d/S97virtualedge-tls').read_text()
        mount = (ROOT/'board/virtualedge/rootfs-overlay/etc/init.d/S21virtualedge-tls-disk').read_text()
        self.assertIn('/run/virtualedge-tls/server.key', service)
        self.assertIn('/dev/vdc', mount)
        self.assertIn('ro,nosuid,nodev,noexec', mount)
        self.assertIn('ve_tls_dev=1', service)

    def test_build_rejects_legacy_keys(self):
        build = (ROOT/'scripts/build-and-test.sh').read_text()
        self.assertIn('Legacy firmware-embedded TLS credential directory', build)
        self.assertIn('obsolete TLS secrets exist in Buildroot target', build)
        self.assertIn("-name '*.key'", build)

    def test_qemu_launcher_uses_readonly_secret_disk(self):
        launch = (ROOT/'scripts/run-qemu-native-tls.sh').read_text()
        runner = (ROOT/'scripts/test-qemu-native-tls.py').read_text()
        self.assertIn('readonly=on', launch)
        self.assertIn('readonly=on', runner)
        self.assertIn('ve_tls_dev=1', launch)
        self.assertIn('ve_tls_dev=1', runner)
        self.assertNotIn('18080', launch)

if __name__ == '__main__':
    main(verbosity=2)
