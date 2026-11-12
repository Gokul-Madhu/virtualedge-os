#!/usr/bin/env python3
"""Host verification of per-client issuance, CRL signatures and native TLS revocation."""
import http.server
import os
from pathlib import Path
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]

def run(*args, expect=0):
    r = subprocess.run(list(map(str, args)), capture_output=True, text=True, timeout=25)
    if expect is not None and r.returncode != expect:
        raise AssertionError(f'command failed: {args} ({r.returncode})\n{r.stderr}')
    return r

def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]

class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = b'{"status":"ready"}'
        self.send_response(200)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def log_message(self, *a): pass

class IdentityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='ve19-id-')
        cls.root = Path(cls.temp.name)
        cls.ca = cls.root/'ca'
        cls.binary = cls.root/'gateway'
        cls.identity = ROOT/'tools/virtualedge_identity.py'
        run('python3', ROOT/'tools/virtualedge_tls_provision.py', '--output', cls.ca)
        run('python3', cls.identity, '--ca', cls.ca, 'init')
        run('gcc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-O2', ROOT/'services/telemetry/virtualedge-tls.c', '-o', cls.binary, '-lssl', '-lcrypto')
        cls.api = http.server.ThreadingHTTPServer(('127.0.0.1', free_port()), Handler)
        cls.thread = threading.Thread(target=cls.api.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.api.shutdown()
        cls.api.server_close()
        cls.temp.cleanup()

    def client(self, name):
        return self.ca/'clients'/name

    def issue(self, name):
        return run('python3', self.identity, '--ca', self.ca, 'issue', name)

    def revoke(self, name):
        return run('python3', self.identity, '--ca', self.ca, 'revoke', name)

    def verify(self, name):
        return run('openssl', 'verify', '-CAfile', self.ca/'ca.pem', '-crl_check', '-CRLfile', self.ca/'client-revocations.pem', self.client(name)/'client.pem', expect=None)

    def probe(self, cert, key, crl=None):
        port = free_port()
        env = os.environ.copy()
        env.update(VE_TLS_PORT=str(port), VE_TLS_UPSTREAM_PORT=str(self.api.server_address[1]))
        if crl: env['VE_TLS_CRL_FILE'] = str(crl)
        with subprocess.Popen([str(self.binary), str(self.ca/'ca.pem'), str(self.ca/'server.pem'), str(self.ca/'server.key')],
                              env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE) as server:
            for _ in range(80):
                if server.poll() is not None: raise AssertionError(f'TLS exited: {server.stderr.read()}')
                try:
                    with socket.create_connection(('127.0.0.1', port), timeout=.1): break
                except OSError: time.sleep(.03)
            ctx = ssl.create_default_context(cafile=str(self.ca/'ca.pem'))
            ctx.load_cert_chain(str(cert), str(key))
            try:
                with socket.create_connection(('127.0.0.1', port), timeout=2) as s:
                    with ctx.wrap_socket(s, server_hostname='localhost') as tls:
                        tls.sendall(b'GET /ready HTTP/1.1\r\nHost: localhost\r\n\r\n')
                        return tls.recv(512)
            except (ssl.SSLError, BrokenPipeError, ConnectionResetError, OSError):
                return b''
            finally:
                server.terminate()
                server.wait(timeout=5)

    def test_01_issue_distinct_client(self):
        self.issue('unit-one')
        self.issue('unit-two')
        self.assertEqual(self.verify('unit-one').returncode, 0)
        self.assertEqual(self.verify('unit-two').returncode, 0)
        self.assertNotEqual((self.client('unit-one')/'client.pem').read_bytes(), (self.client('unit-two')/'client.pem').read_bytes())

    def test_02_no_identity_overwrite(self):
        before = (self.client('unit-one')/'client.pem').read_bytes()
        self.assertNotEqual(run('python3', self.identity, '--ca', self.ca, 'issue', 'unit-one', expect=None).returncode, 0)
        self.assertEqual(before, (self.client('unit-one')/'client.pem').read_bytes())

    def test_03_bad_identifiers_rejected(self):
        for name in ('../bad', 'bad space', 'x'*49):
            self.assertNotEqual(run('python3', self.identity, '--ca', self.ca, 'issue', name, expect=None).returncode, 0)

    def test_04_valid_identity_accepted_at_gateway(self):
        reply = self.probe(self.client('unit-one')/'client.pem', self.client('unit-one')/'client.key', self.ca/'client-revocations.pem')
        self.assertIn(b'200', reply)

    def test_05_revoked_client_rejected_at_gateway(self):
        self.revoke('unit-one')
        self.assertNotEqual(self.verify('unit-one').returncode, 0)
        reply = self.probe(self.client('unit-one')/'client.pem', self.client('unit-one')/'client.key', self.ca/'client-revocations.pem')
        self.assertNotIn(b'200', reply)
        self.assertIn(b'200', self.probe(self.client('unit-two')/'client.pem', self.client('unit-two')/'client.key', self.ca/'client-revocations.pem'))

    def test_06_missing_configured_crl_fails_closed(self):
        port = free_port()
        env = os.environ.copy()
        env.update(VE_TLS_PORT=str(port), VE_TLS_CRL_FILE=str(self.root/'missing.pem'))
        r = subprocess.run([self.binary, self.ca/'ca.pem', self.ca/'server.pem', self.ca/'server.key'], env=env, capture_output=True, timeout=5)
        self.assertNotEqual(r.returncode, 0)

    def test_07_disk_script_stages_crl(self):
        code = (ROOT/'tools/virtualedge_tls_image.py').read_text()
        self.assertIn('client-revocations.pem', code)
        self.assertIn('CRL signature verification failed', code)

if __name__ == '__main__': unittest.main(verbosity=2)
