#!/usr/bin/env python3
"""End-to-end host tests of native guest-side offline staging. No block devices."""
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

class StageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build=tempfile.TemporaryDirectory()
        base=Path(cls.build.name)
        cls.verifier=base/'virtualedge-update-verify'
        cls.stager=base/'virtualedge-update-stage'
        for name,target in [('virtualedge-update-verify.c',cls.verifier),('virtualedge-update-stage.c',cls.stager)]:
            cmd=['gcc','-std=c11','-O2','-Wall','-Wextra','-Werror',str(SRC/name),'-o',str(target)]
            if name.endswith('verify.c'):cmd.append('-lcrypto')
            subprocess.run(cmd,check=True)
        cls.private=base/'private.pem';cls.pub=base/'public.pem'
        subprocess.run([sys.executable,str(RELEASE),'keygen','--private-key',str(cls.private),'--public-key',str(cls.pub)],check=True,capture_output=True)

    @classmethod
    def tearDownClass(cls):cls.build.cleanup()

    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base=Path(tmp.name)
        self.stage=self.base/'storage';self.stage.mkdir(mode=0o700)
        self.image=self.base/'rootfs.ext4';self.image.write_bytes(b'VirtualEdge sample rootfs' * 128)
        bundle=self.base/'bundle.tar'
        subprocess.run([sys.executable,str(RELEASE),'pack','--image',str(self.image),
            '--private-key',str(self.private),'--board','qemu-aarch64','--version','0.27.0','--output',str(bundle)],check=True,capture_output=True)
        for name in ('manifest.json','manifest.sig','image.bin'):
            with tarfile.open(bundle) as tar:
                (self.base/name).write_bytes(tar.extractfile(name).read())

    def stage_image(self, **changes):
        params={'root':self.stage,'manifest':self.base/'manifest.json','sig':self.base/'manifest.sig',
                'image':self.base/'image.bin','pub':self.pub,'board':'qemu-aarch64','floor':'0.26.0','verifier':self.verifier}
        params.update(changes)
        return subprocess.run([str(self.stager),str(params['root']),str(params['manifest']),str(params['sig']),
                               str(params['image']),str(params['pub']),str(params['board']),str(params['floor']),
                               str(params['verifier'])],capture_output=True,text=True)

    def assert_clean(self):
        self.assertFalse((self.stage/'candidate').exists())
        self.assertEqual(list(self.stage.glob('.stage-*')),[])

    def test_valid_signed_image_published_atomically(self):
        ret=self.stage_image()
        self.assertEqual(ret.returncode,0,ret.stderr)
        self.assertEqual((self.stage/'candidate'/'image.bin').read_bytes(),(self.base/'image.bin').read_bytes())
        self.assertEqual({x.name for x in (self.stage/'candidate').iterdir()}, {'manifest.json','manifest.sig','image.bin'})
        self.assertFalse((self.stage/'candidate'/'image.bin').stat().st_mode & 0o077)

    def test_corrupted_image_never_published(self):
        (self.base/'image.bin').write_bytes(b'bad image')
        self.assertNotEqual(self.stage_image().returncode,0)
        self.assert_clean()

    def test_corrupted_signature_never_published(self):
        (self.base/'manifest.sig').write_bytes(b'wrong')
        self.assertNotEqual(self.stage_image().returncode,0)
        self.assert_clean()

    def test_board_mismatch_never_published(self):
        self.assertNotEqual(self.stage_image(board='another-board').returncode,0)
        self.assert_clean()

    def test_version_floor_never_published(self):
        self.assertNotEqual(self.stage_image(floor='0.28.0').returncode,0)
        self.assert_clean()

    def test_existing_candidate_preserved(self):
        (self.stage/'candidate').mkdir()
        (self.stage/'candidate'/'keep').write_text('do not overwrite')
        self.assertNotEqual(self.stage_image().returncode,0)
        self.assertEqual((self.stage/'candidate'/'keep').read_text(),'do not overwrite')

    def test_insecure_staging_directory_rejected(self):
        self.stage.chmod(0o755)
        self.assertNotEqual(self.stage_image().returncode,0)
        self.assert_clean()

    def test_symlink_image_rejected(self):
        image=self.base/'image.bin';image.rename(self.base/'real.img')
        image.symlink_to(self.base/'real.img')
        self.assertNotEqual(self.stage_image().returncode,0)
        self.assert_clean()

    def test_nonregular_input_rejected(self):
        self.assertNotEqual(self.stage_image(image=self.base).returncode,0)
        self.assert_clean()

    def test_failed_verifier_never_publishes(self):
        self.assertNotEqual(self.stage_image(verifier='/does/not/exist').returncode,0)
        self.assert_clean()

if __name__=='__main__':unittest.main(verbosity=2)
