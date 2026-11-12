#!/usr/bin/env python3
"""v0.28 signed candidate -> regular-file inactive slot; no raw disks."""
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'services/telemetry'
RELEASE=ROOT/'tools/virtualedge_release.py'
class InstallTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build=tempfile.TemporaryDirectory(); base=Path(cls.build.name)
        cls.verify=base/'verify';cls.stage_tool=base/'stage';cls.install=base/'install'
        for source,out,libs in [
            ('virtualedge-update-verify.c',cls.verify,['-lcrypto']),
            ('virtualedge-update-stage.c',cls.stage_tool,[]),
            ('virtualedge-update-install-file.c',cls.install,[])]:
            subprocess.run(['gcc','-std=c11','-O2','-Wall','-Wextra','-Werror',str(SRC/source),'-o',str(out),*libs],check=True)
        cls.priv=base/'key.pem';cls.pub=base/'pub.pem'
        subprocess.run([sys.executable,str(RELEASE),'keygen','--private-key',str(cls.priv),'--public-key',str(cls.pub)],check=True,capture_output=True)
    @classmethod
    def tearDownClass(cls):cls.build.cleanup()
    def setUp(self):
        work=tempfile.TemporaryDirectory();self.addCleanup(work.cleanup)
        self.root=Path(work.name);self.stage=self.root/'stage';self.slot=self.root/'slots'
        self.stage.mkdir(mode=0o700);self.slot.mkdir(mode=0o700)
        self.image=self.root/'source.img';self.image.write_bytes(b'VirtualEdge verified image' * 256)
        bundle=self.root/'signed.tar'
        subprocess.run([sys.executable,str(RELEASE),'pack','--image',str(self.image),'--private-key',str(self.priv),'--board','qemu-aarch64','--version','0.28.0','--output',str(bundle)],check=True,capture_output=True)
        with tarfile.open(bundle) as archive:
            for name in ('manifest.json','manifest.sig','image.bin'):
                (self.root/name).write_bytes(archive.extractfile(name).read())
    def stage_it(self):
        return subprocess.run([str(self.stage_tool),str(self.stage),str(self.root/'manifest.json'),str(self.root/'manifest.sig'),str(self.root/'image.bin'),str(self.pub),'qemu-aarch64','0.27.0',str(self.verify)],capture_output=True,text=True)
    def install_it(self,**kwargs):
        opts=dict(stage=self.stage,slot=self.slot,pub=self.pub,board='qemu-aarch64',floor='0.27.0',verifier=self.verify)
        opts.update(kwargs)
        return subprocess.run([str(self.install),*[str(opts[k]) for k in ('stage','slot','pub','board','floor','verifier')]],capture_output=True,text=True)
    def assert_no_install(self):
        self.assertFalse((self.slot/'inactive-slot.img').exists())
        self.assertEqual(list(self.slot.glob('.install-*')),[])
    def test_verified_regular_file_installed(self):
        self.assertEqual(self.stage_it().returncode,0)
        result=self.install_it()
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual((self.slot/'inactive-slot.img').read_bytes(),self.image.read_bytes())
        self.assertEqual((self.slot/'inactive-slot.img').stat().st_mode & 0o077,0)
        self.assertEqual(list(self.slot.glob('.install-*')),[])
    def test_cannot_install_unstaged_image(self):
        self.assertNotEqual(self.install_it().returncode,0);self.assert_no_install()
    def test_tampered_staged_image_rejected(self):
        self.assertEqual(self.stage_it().returncode,0)
        (self.stage/'candidate'/'image.bin').write_bytes(b'tampered')
        self.assertNotEqual(self.install_it().returncode,0);self.assert_no_install()
    def test_tampered_manifest_rejected(self):
        self.assertEqual(self.stage_it().returncode,0)
        (self.stage/'candidate'/'manifest.json').write_bytes(b'{}')
        self.assertNotEqual(self.install_it().returncode,0);self.assert_no_install()
    def test_wrong_board_rejected(self):
        self.assertEqual(self.stage_it().returncode,0)
        self.assertNotEqual(self.install_it(board='other-board').returncode,0);self.assert_no_install()
    def test_rollback_floor_rejected(self):
        self.assertEqual(self.stage_it().returncode,0)
        self.assertNotEqual(self.install_it(floor='0.29.0').returncode,0);self.assert_no_install()
    def test_existing_slot_preserved(self):
        self.assertEqual(self.stage_it().returncode,0)
        (self.slot/'inactive-slot.img').write_bytes(b'original slot')
        self.assertNotEqual(self.install_it().returncode,0)
        self.assertEqual((self.slot/'inactive-slot.img').read_bytes(),b'original slot')
    def test_symlink_slot_rejected(self):
        self.assertEqual(self.stage_it().returncode,0)
        (self.slot/'inactive-slot.img').symlink_to(self.image)
        self.assertNotEqual(self.install_it().returncode,0)
        self.assertEqual(self.image.read_bytes(),b'VirtualEdge verified image'*256)
    def test_symlink_candidate_rejected(self):
        self.assertEqual(self.stage_it().returncode,0)
        (self.stage/'candidate'/'image.bin').rename(self.stage/'candidate'/'real.bin')
        (self.stage/'candidate'/'image.bin').symlink_to('real.bin')
        self.assertNotEqual(self.install_it().returncode,0);self.assert_no_install()
    def test_insecure_directory_rejected(self):
        self.assertEqual(self.stage_it().returncode,0)
        self.slot.chmod(0o755)
        self.assertNotEqual(self.install_it().returncode,0);self.assert_no_install()
    def test_cannot_install_to_device_path(self):
        self.assertEqual(self.stage_it().returncode,0)
        self.assertNotEqual(self.install_it(slot='/dev').returncode,0)
        self.assert_no_install()
if __name__=='__main__':unittest.main(verbosity=2)
