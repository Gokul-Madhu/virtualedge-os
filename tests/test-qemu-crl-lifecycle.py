#!/usr/bin/env python3
"""Host tests of the QEMU revocation lifecycle orchestration and checks."""
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestQemuLifecycle(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qemu = load('ve22tlsqemu', 'scripts/test-qemu-native-tls.py')
        cls.lifecycle = load('ve22crllife', 'scripts/test-qemu-crl-lifecycle.py')

    def test_readiness_status_is_strict(self):
        self.assertTrue(self.qemu.is_ready(b'HTTP/1.1 200 OK\r\n\r\n{"status":"ready"}'))
        for response in (b'', b'HTTP/1.1 503 Service Unavailable\r\n\r\n{"status":"ready"}',
                         b'HTTP/1.1 200 OK\r\n\r\n{"status":"not_ready"}',
                         b'HTTP/1.1 200 OK\r\n\r\n{"status":"ok"}'):
            self.assertFalse(self.qemu.is_ready(response))

    def test_lifecycle_two_boots_with_expected_identities(self):
        commands = []
        def fake_exec(*cmd):
            commands.append([str(x) for x in cmd])
        with patch.object(self.lifecycle, 'execute', side_effect=fake_exec):
            self.lifecycle.lifecycle(40, 19999)
        boots = [cmd for cmd in commands if 'test-qemu-native-tls.py' in cmd[1]]
        self.assertEqual(len(boots), 2)
        self.assertIn('--approved', boots[0])
        self.assertNotIn('--revoked', boots[0])
        self.assertIn('--revoked', boots[1])
        self.assertEqual(boots[1].count('--approved'), 2)
        self.assertEqual(boots[1].count('--revoked'), 1)
        self.assertIn('alpha', ' '.join(boots[1]))
        self.assertIn('charlie', ' '.join(boots[1]))
        self.assertIn('bravo', ' '.join(boots[1]))
        self.assertTrue(any('rotate' in cmd for cmd in commands))
        self.assertEqual(sum('virtualedge_tls_image.py' in cmd[1] for cmd in commands), 2)

    def test_qemu_client_inputs_reject_missing_keys(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            (base / 'ca.pem').touch()
            (base / 'client.pem').touch()
            (base / 'client.key').touch()
            with patch.object(self.qemu, 'IMAGES', base), patch.object(self.qemu, 'ROOT', base):
                with self.assertRaisesRegex(RuntimeError, 'Missing separate TLS disk'):
                    self.qemu.run(base, tls_image=base / 'missing.ext4')

    def test_help_documents_expected_cli_options(self):
        for script, expected in (
            ('scripts/test-qemu-native-tls.py', ('--approved', '--revoked', '--tls-image')),
            ('scripts/test-qemu-crl-lifecycle.py', ('--timeout', '--port'))):
            out = subprocess.run([sys.executable, str(ROOT / script), '--help'],
                                 capture_output=True, text=True, timeout=8)
            self.assertEqual(out.returncode, 0, out.stderr)
            for option in expected:
                self.assertIn(option, out.stdout)


if __name__ == '__main__':
    unittest.main(verbosity=2)
