#!/usr/bin/env python3
"""v0.21: fail-closed revocation policy and full client-rotation TLS acceptance."""
import http.server
import os
from pathlib import Path
from unittest.mock import patch
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]

def command(*args, check=True):
    return subprocess.run([str(x) for x in args], check=check, capture_output=True, text=True, timeout=35)

def port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]

class Upstream(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        data=b'{"status":"ready"}'
        self.send_response(200)
        self.send_header('Content-Length',str(len(data)))
        self.end_headers()
        self.wfile.write(data)
    def log_message(self, *_): pass

class CRLPolicy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='ve21-crl-')
        cls.root=Path(cls.tmp.name)
        cls.ca=cls.root/'ca'
        cls.tool=ROOT/'tools/virtualedge_identity.py'
        cls.bin=cls.root/'virtualedge-tls'
        command(sys.executable,ROOT/'tools/virtualedge_tls_provision.py','--output',cls.ca)
        command(sys.executable,cls.tool,'--ca',cls.ca,'init')
        command(sys.executable,cls.tool,'--ca',cls.ca,'issue','original')
        command('gcc','-std=c11','-O2','-Wall','-Wextra','-Werror',ROOT/'services/telemetry/virtualedge-tls.c','-o',cls.bin,'-lssl','-lcrypto')
        cls.api=http.server.ThreadingHTTPServer(('127.0.0.1',port()),Upstream)
        cls.thread=threading.Thread(target=cls.api.serve_forever,daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.api.shutdown();cls.api.server_close();cls.tmp.cleanup()

    def server(self, crl=None, required=True):
        tlsport=port()
        env=os.environ.copy()
        env['VE_TLS_PORT']=str(tlsport)
        env['VE_TLS_UPSTREAM_PORT']=str(self.api.server_address[1])
        env.pop('VE_TLS_CRL_FILE',None)
        env['VE_TLS_REQUIRE_CRL']='1' if required else '0'
        if crl is not None: env['VE_TLS_CRL_FILE']=str(crl)
        proc=subprocess.Popen([str(self.bin),str(self.ca/'ca.pem'),str(self.ca/'server.pem'),str(self.ca/'server.key')],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        for _ in range(100):
            if proc.poll() is not None: return proc,tlsport
            try:
                with socket.create_connection(('127.0.0.1',tlsport),timeout=.1):return proc,tlsport
            except OSError:time.sleep(.02)
        proc.terminate();proc.wait(timeout=3)
        self.fail('TLS gateway did not start')

    def probe(self, tlsport, name):
        ctx=ssl.create_default_context(cafile=str(self.ca/'ca.pem'))
        loc=self.ca/'clients'/name
        ctx.load_cert_chain(str(loc/'client.pem'),str(loc/'client.key'))
        try:
            with socket.create_connection(('127.0.0.1',tlsport),timeout=3) as sock:
                with ctx.wrap_socket(sock,server_hostname='localhost') as tls:
                    tls.settimeout(3)
                    tls.sendall(b'GET /ready HTTP/1.1\r\nHost: localhost\r\n\r\n')
                    return tls.recv(512)
        except (ssl.SSLError,ConnectionResetError,BrokenPipeError,OSError):return b''

    def test_01_guest_startup_requires_crl(self):
        service=(ROOT/'board/virtualedge/rootfs-overlay/etc/init.d/S97virtualedge-tls').read_text()
        self.assertIn('VE_TLS_REQUIRE_CRL=1',service)
        self.assertIn('Required TLS CRL missing',service)
        proc,_=self.server(crl=None)
        self.assertNotEqual(proc.wait(timeout=3),0)
        self.assertIn(b'revocation list required',proc.stderr.read());proc.stderr.close()

    def test_02_missing_crl_path_fails(self):
        proc,_=self.server(self.root/'absent.pem')
        self.assertNotEqual(proc.wait(timeout=3),0)
        self.assertIn(b'CRL missing or unsafe',proc.stderr.read());proc.stderr.close()

    def test_03_active_rotation_and_revocation_enforced(self):
        crl=self.ca/'client-revocations.pem'
        proc,p=self.server(crl)
        try:self.assertIn(b'200 OK',self.probe(p,'original'))
        finally:proc.terminate();proc.wait(timeout=3);proc.stderr.close()
        command(sys.executable,self.tool,'--ca',self.ca,'rotate','original','replacement')
        proc,p=self.server(crl)
        try:
            self.assertNotIn(b'200 OK',self.probe(p,'original'))
            self.assertIn(b'200 OK',self.probe(p,'replacement'))
        finally:proc.terminate();proc.wait(timeout=3);proc.stderr.close()

    def test_04_stale_missing_crl_disk_is_rejected(self):
        import importlib.util
        spec=importlib.util.spec_from_file_location('tlsdisk',ROOT/'tools/virtualedge_tls_image.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        crl=self.ca/'client-revocations.pem'
        temp=self.ca/'client-revocations.pem.saved'
        crl.rename(temp)
        try:
            with patch.object(module.shutil, 'which', return_value='/usr/sbin/mkfs.ext4'):
                with self.assertRaisesRegex(ValueError,'requires a signed CRL'):
                    module.create(self.ca,self.root/'not-created.ext4')
        finally:temp.rename(crl)
        self.assertFalse((self.root/'not-created.ext4').exists())

if __name__=='__main__':unittest.main(verbosity=2)
