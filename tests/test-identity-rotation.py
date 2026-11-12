#!/usr/bin/env python3
"""v0.20 identity replacement and CRL freshness acceptance tests (host only)."""
from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import virtualedge_tls_image as disk


def cmd(*parts, check=True):
    return subprocess.run(list(map(str, parts)), capture_output=True, text=True,
                          check=check, timeout=30)

class Rotation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='ve20-rotation-')
        cls.ca = Path(cls.tmp.name) / 'ca'
        cls.script = ROOT / 'tools/virtualedge_identity.py'
        cmd(sys.executable, ROOT / 'tools/virtualedge_tls_provision.py', '--output', cls.ca)
        cmd(sys.executable, cls.script, '--ca', cls.ca, 'init')
        cmd(sys.executable, cls.script, '--ca', cls.ca, 'issue', 'old-unit')

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def checkcert(self, identity):
        return cmd('openssl', 'verify', '-CAfile', self.ca/'ca.pem', '-crl_check',
                   '-CRLfile', self.ca/'client-revocations.pem',
                   self.ca/'clients'/identity/'client.pem', check=False)

    def test_01_rotation_revokes_old_and_keeps_new_valid(self):
        self.assertEqual(self.checkcert('old-unit').returncode, 0)
        cmd(sys.executable, self.script, '--ca', self.ca, 'rotate', 'old-unit', 'new-unit')
        self.assertNotEqual(self.checkcert('old-unit').returncode, 0)
        self.assertEqual(self.checkcert('new-unit').returncode, 0)
        self.assertTrue((self.ca/'clients/new-unit/client.key').stat().st_mode & 0o077 == 0)

    def test_02_refuses_reusing_old_or_existing_name(self):
        for old, new in [('new-unit', 'new-unit'), ('new-unit', 'old-unit')]:
            r = cmd(sys.executable, self.script, '--ca', self.ca, 'rotate', old, new, check=False)
            self.assertNotEqual(r.returncode, 0)
        self.assertEqual(self.checkcert('new-unit').returncode, 0)

    def test_03_refuses_missing_identity_before_issuance(self):
        r = cmd(sys.executable, self.script, '--ca', self.ca, 'rotate', 'missing', 'unsafe-new', check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse((self.ca/'clients/unsafe-new').exists())

    def test_04_revoked_identity_cannot_be_rotated(self):
        r = cmd(sys.executable, self.script, '--ca', self.ca, 'rotate', 'old-unit', 'should-not-exist', check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse((self.ca/'clients/should-not-exist').exists())

    def test_05_bad_crl_validity_fails_before_mkfs(self):
        # Patch only the subprocess *inside the image builder* to simulate an
        # expired, otherwise correctly signed CRL. No real private keys copied.
        original = disk.subprocess.run
        def fake(args, **kwargs):
            if list(args)[:3] == ['openssl','crl','-in'] and '-lastupdate' in args:
                return subprocess.CompletedProcess(args, 0,
                    'lastUpdate=Jan  1 00:00:00 2020 GMT\nnextUpdate=Jan  2 00:00:00 2020 GMT\n', '')
            return original(args, **kwargs)
        out = Path(self.tmp.name)/'no-stale-image.ext4'
        with patch.object(disk.shutil, 'which', return_value='/usr/sbin/mkfs.ext4'):
            with patch.object(disk.subprocess, 'run', side_effect=fake):
                with self.assertRaisesRegex(ValueError, 'CRL expired'):
                    disk.create(self.ca, out)
        self.assertFalse(out.exists())

    def test_06_fresh_crl_dates_accepted(self):
        result=cmd('openssl','crl','-in',self.ca/'client-revocations.pem','-noout','-lastupdate','-nextupdate')
        self.assertIn('lastUpdate=', result.stdout)
        self.assertIn('nextUpdate=', result.stdout)

if __name__ == '__main__':
    unittest.main(verbosity=2)
