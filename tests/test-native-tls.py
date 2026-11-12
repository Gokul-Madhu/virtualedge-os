#!/usr/bin/env python3
"""Native OpenSSL guest gateway tests, executed on Linux host with temporary credentials."""
import http.server
import os
from pathlib import Path
import socket
import ssl
import subprocess
import tempfile
import threading
import time
import unittest

ROOT = Path(__file__).resolve().parent.parent

def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1',0))
        return s.getsockname()[1]

class API(http.server.BaseHTTPRequestHandler):
    requests=[]
    def do_GET(self):
        self.__class__.requests.append((self.path,dict(self.headers)))
        body=b'{"status":"ready"}'
        self.send_response(200)
        self.send_header('Content-Type','application/json')
        self.send_header('Content-Length',str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def log_message(self,*args):pass

class NativeTLSTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory()
        cls.root=Path(cls.tmp.name)
        cls.binary=cls.root/'virtualedge-tls'
        subprocess.run(['gcc','-std=c11','-O2','-Wall','-Wextra','-Werror',str(ROOT/'services/telemetry/virtualedge-tls.c'),'-o',str(cls.binary),'-lssl','-lcrypto'],check=True)
        cls.creds=cls.root/'credentials'
        subprocess.run(['python3',str(ROOT/'tools/virtualedge_tls_provision.py'),'--output',str(cls.creds)],check=True)
        cls.api_port=free_port()
        cls.api=http.server.ThreadingHTTPServer(('127.0.0.1',cls.api_port),API)
        cls.thread=threading.Thread(target=cls.api.serve_forever,daemon=True)
        cls.thread.start()
        cls.tls_port=free_port()
        env=os.environ.copy()
        env['VE_TLS_PORT']=str(cls.tls_port)
        env['VE_TLS_UPSTREAM_PORT']=str(cls.api_port)
        cls.proxy=subprocess.Popen([str(cls.binary),str(cls.creds/'ca.pem'),str(cls.creds/'server.pem'),str(cls.creds/'server.key')],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        for _ in range(100):
            if cls.proxy.poll() is not None:raise AssertionError('TLS server quit')
            try:
                with socket.create_connection(('127.0.0.1',cls.tls_port),timeout=.1):break
            except OSError:time.sleep(.03)
        else:raise AssertionError('TLS server never started')

    @classmethod
    def tearDownClass(cls):
        cls.proxy.terminate()
        cls.proxy.wait(timeout=5)
        cls.api.shutdown()
        cls.api.server_close()
        cls.tmp.cleanup()

    def request(self,raw,cert=True):
        ctx=ssl.create_default_context(cafile=str(self.creds/'ca.pem'))
        if cert:ctx.load_cert_chain(str(self.creds/'client.pem'),str(self.creds/'client.key'))
        with socket.create_connection(('127.0.0.1',self.tls_port),timeout=3) as sock:
            with ctx.wrap_socket(sock,server_hostname='localhost') as tls:
                tls.settimeout(3)
                for chunk in raw:
                    tls.sendall(chunk)
                    time.sleep(.02)
                data=b''
                try:
                    while True:
                        chunk=tls.recv(4096)
                        if not chunk:break
                        data+=chunk
                except (ssl.SSLError,ConnectionResetError):pass
                return data

    def test_ready_over_mtls(self):
        data=self.request([b'GET /ready HTTP/1.1\r\nHost: localhost\r\n\r\n'])
        self.assertIn(b'200 OK',data)
        self.assertIn(b'"status":"ready"',data)

    def test_no_certificate_rejected(self):
        try:
            data=self.request([b'GET /ready HTTP/1.1\r\nHost: localhost\r\n\r\n'],cert=False)
        except (ssl.SSLError,ConnectionResetError,BrokenPipeError):return
        self.assertNotIn(b'200 OK',data)

    def test_split_request(self):
        data=self.request([b'GET /ready HTTP/1.1\r\nHost:',b' localhost\r\n\r\n'])
        self.assertIn(b'200 OK',data)

    def test_route_and_method_restrictions(self):
        self.assertIn(b'404 Not Found',self.request([b'GET /admin HTTP/1.1\r\nHost: localhost\r\n\r\n']))
        self.assertIn(b'405 Method Not Allowed',self.request([b'POST /ready HTTP/1.1\r\nHost: localhost\r\n\r\n']))

    def test_request_headers_not_forwarded(self):
        API.requests.clear()
        data=self.request([b'GET /ready HTTP/1.1\r\nHost: localhost\r\nAuthorization: Basic attacker\r\nX-Admin: true\r\n\r\n'])
        self.assertIn(b'200 OK',data)
        self.assertTrue(API.requests)
        self.assertNotIn('Authorization',API.requests[-1][1])
        self.assertNotIn('X-Admin',API.requests[-1][1])

    def test_guest_acceptance_client_probe(self):
        """Exercise the same Python certificate and readiness probe as live QEMU."""
        import importlib.util
        script = ROOT/'scripts/test-qemu-native-tls.py'
        spec = importlib.util.spec_from_file_location('guest_tls_acceptance', script)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        ok = module.tls_request(self.tls_port, self.creds/'ca.pem',
                                self.creds/'client.pem', self.creds/'client.key')
        self.assertIn(b'200 OK', ok)
        with self.assertRaises((ssl.SSLError, ConnectionResetError, BrokenPipeError, OSError)):
            module.tls_request(self.tls_port, self.creds/'ca.pem')

    def test_guest_acceptance_missing_credentials_fails(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location('guest_tls_acceptance', ROOT/'scripts/test-qemu-native-tls.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with self.assertRaisesRegex(RuntimeError, 'Missing development client credential'):
            module.run(self.root/'missing-credentials', timeout=10)

    def test_insecure_server_key_rejected(self):
        key=self.creds/'server.key'
        key.chmod(0o644)
        try:
            result=subprocess.run([str(self.binary),str(self.creds/'ca.pem'),str(self.creds/'server.pem'),str(key)],capture_output=True,timeout=3)
            self.assertNotEqual(result.returncode,0)
            self.assertIn(b'insecure',result.stderr)
        finally:key.chmod(0o600)

if __name__ == '__main__':
    unittest.main(verbosity=2)
