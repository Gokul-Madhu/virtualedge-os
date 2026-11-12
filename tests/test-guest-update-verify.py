#!/usr/bin/env python3
"""Host-native regression for the ARM64 guest offline signed-image preflight."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / 'tools' / 'virtualedge_release.py'
SRC = ROOT / 'services' / 'telemetry' / 'virtualedge-update-verify.c'

class VerifyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build = tempfile.TemporaryDirectory()
        cls.bin = Path(cls.build.name) / 'verify'
        subprocess.run(['gcc', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', str(SRC), '-lcrypto', '-o', str(cls.bin)], check=True)

    @classmethod
    def tearDownClass(cls): cls.build.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.p = Path(self.temp.name)
        self.key = self.p / 'key.pem'; self.pub = self.p / 'pub.pem'
        self.img = self.p / 'rootfs.ext4'
        self.img.write_bytes(b'VirtualEdge disposable image test \x00' * 71)
        self.bundle = self.p / 'release.tar'
        self.call_release('keygen', '--private-key', str(self.key), '--public-key', str(self.pub))
        self.call_release('pack', '--image', str(self.img), '--private-key', str(self.key),
                          '--board', 'qemu-aarch64', '--version', '0.26.0', '--output', str(self.bundle))
        with tarfile.open(self.bundle) as t:
            for name in ('manifest.json', 'manifest.sig', 'image.bin'):
                (self.p / name).write_bytes(t.extractfile(name).read())

    def call_release(self, *args):
        subprocess.run([sys.executable, str(RELEASE), *args], check=True, capture_output=True)

    def verify(self, board='qemu-aarch64', minimum='0.25.0'):
        return subprocess.run([str(self.bin), str(self.p / 'manifest.json'),
                               str(self.p / 'manifest.sig'), str(self.p / 'image.bin'),
                               str(self.pub), board, minimum], capture_output=True, text=True)

    def test_approved_signed_image(self):
        result = self.verify()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('NO installation performed', result.stdout)

    def test_modified_image_rejected(self):
        with (self.p / 'image.bin').open('ab') as f: f.write(b'tampered')
        self.assertNotEqual(self.verify().returncode, 0)

    def test_modified_manifest_rejected(self):
        f = self.p / 'manifest.json'
        f.write_bytes(f.read_bytes().replace(b'0.26.0', b'0.27.0'))
        self.assertNotEqual(self.verify().returncode, 0)

    def test_modified_signature_rejected(self):
        f = self.p / 'manifest.sig'; data = bytearray(f.read_bytes()); data[0] ^= 0xff; f.write_bytes(data)
        self.assertNotEqual(self.verify().returncode, 0)

    def test_board_mismatch_rejected(self): self.assertNotEqual(self.verify(board='other-board').returncode, 0)
    def test_rollback_floor_rejected(self): self.assertNotEqual(self.verify(minimum='0.27.0').returncode, 0)
    def test_symlink_image_rejected(self):
        f = self.p / 'image.bin'; moved = self.p / 'other.img'; f.rename(moved); f.symlink_to(moved)
        self.assertNotEqual(self.verify().returncode, 0)
    def test_noncanonical_manifest_rejected(self):
        f = self.p / 'manifest.json'; f.write_bytes(f.read_bytes().replace(b'"size":', b'"size":0'))
        self.assertNotEqual(self.verify().returncode, 0)
    def test_bad_minimum_version_rejected(self): self.assertNotEqual(self.verify(minimum='0.025.0').returncode, 0)

if __name__ == '__main__': unittest.main(verbosity=2)
