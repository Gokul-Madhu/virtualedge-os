#!/usr/bin/env python3
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / 'tools/virtualedge_tls_audit.py'
PROVISION = ROOT / 'tools/virtualedge_tls_provision.py'


class CredentialAuditTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='ve-tls-audit-')
        cls.root = Path(cls.tmp.name)
        cls.valid = cls.root/'original'
        subprocess.run([sys.executable, str(PROVISION), '--output', str(cls.valid)], check=True, capture_output=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def copy(self):
        path = self.root / self.id().split('.')[-1]
        shutil.copytree(self.valid, path)
        return path

    def run_audit(self, path):
        return subprocess.run([sys.executable, str(TOOL), '--credentials', str(path), '--json'], capture_output=True, text=True)

    def test_valid(self):
        result = self.run_audit(self.valid)
        self.assertEqual(result.returncode, 0, result.stderr)
        obj = json.loads(result.stdout)
        self.assertEqual(obj['status'],'valid')
        self.assertFalse(obj['production_approved'])

    def test_world_readable_private_key(self):
        path = self.copy()
        (path/'server.key').chmod(0o644)
        self.assertNotEqual(self.run_audit(path).returncode, 0)

    def test_mismatched_server_key(self):
        path = self.copy()
        shutil.copyfile(path/'client.key', path/'server.key')
        self.assertIn('does not match', self.run_audit(path).stderr)

    def test_mismatched_trust_anchor(self):
        path = self.copy()
        other = self.root/'different-ca'
        subprocess.run([sys.executable,str(PROVISION),'--output',str(other)],check=True,capture_output=True)
        shutil.copyfile(other/'ca.pem',path/'ca.pem')
        self.assertNotEqual(self.run_audit(path).returncode,0)

    def test_server_certificate_must_have_server_purpose(self):
        path=self.copy()
        shutil.copyfile(path/'client.pem',path/'server.pem')
        self.assertNotEqual(self.run_audit(path).returncode,0)

    def test_symlinked_private_key_rejected(self):
        path=self.copy()
        (path/'server.key').unlink()
        (path/'server.key').symlink_to(self.valid/'server.key')
        self.assertNotEqual(self.run_audit(path).returncode,0)

    def test_insecure_credential_directory(self):
        path=self.copy()
        path.chmod(0o755)
        self.assertNotEqual(self.run_audit(path).returncode,0)

    def test_expiry_warning(self):
        result=subprocess.run([sys.executable,str(TOOL),'--credentials',str(self.valid),'--warn-days','365','--json'],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertTrue(json.loads(result.stdout)['warnings'])

if __name__ == '__main__':
    unittest.main(verbosity=2)
