#!/usr/bin/env python3
"""Functional TLS gateway checks using a simulated localhost-only guest API."""
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
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]

def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]

class Stub(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = (b'<html>virtualedge</html>' if self.path == '/dashboard'
                else b'{"status":"ok"}')
        self.send_response(200)
        self.send_header('Content-Type', 'text/html' if self.path == '/dashboard' else 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        pass

with tempfile.TemporaryDirectory(prefix='virtualedge-tls-test-') as tmp:
    creds = Path(tmp) / 'tls'
    subprocess.run([sys.executable, str(ROOT / 'tools/virtualedge_tls_provision.py'), '--output', str(creds)], check=True, capture_output=True, text=True, timeout=40)
    assert all((creds / n).exists() for n in ('ca.pem', 'server.pem', 'server.key', 'client.pem', 'client.key'))
    assert not ((creds / 'client.key').stat().st_mode & 0o077)
    repeat = subprocess.run([sys.executable, str(ROOT / 'tools/virtualedge_tls_provision.py'), '--output', str(creds)], capture_output=True, timeout=10)
    assert repeat.returncode != 0, 'Provisioner must not overwrite existing signing keys'
    print('PASS: private CA, server/client certificates, overwrite protection', flush=True)

    upstream = http.server.ThreadingHTTPServer(('127.0.0.1', free_port()), Stub)
    thread = threading.Thread(target=upstream.serve_forever, daemon=True)
    thread.start()
    port = free_port()
    args = [sys.executable, str(ROOT / 'tools/virtualedge_tls_gateway.py'), '--credentials', str(creds), '--port', str(port), '--upstream-port', str(upstream.server_port)]
    gateway = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        for _ in range(100):
            if gateway.poll() is not None:
                raise AssertionError(f'Gateway exited early: {gateway.stderr.read().decode()}')
            try:
                with socket.create_connection(('127.0.0.1', port), timeout=.1):
                    break
            except OSError:
                time.sleep(.05)
        else:
            raise AssertionError('Gateway did not start')

        ctx = ssl.create_default_context(cafile=str(creds / 'ca.pem'))
        ctx.load_cert_chain(certfile=str(creds / 'client.pem'), keyfile=str(creds / 'client.key'))
        url = f'https://localhost:{port}'
        with urllib.request.urlopen(url + '/dashboard', context=ctx, timeout=5) as resp:
            assert resp.status == 200 and b'virtualedge' in resp.read()
        with urllib.request.urlopen(url + '/ready', context=ctx, timeout=5) as resp:
            assert resp.status == 200 and b'ok' in resp.read()
        print('PASS: HTTPS client-authenticated dashboard and readiness endpoints', flush=True)

        bad_ctx = ssl.create_default_context(cafile=str(creds / 'ca.pem'))
        try:
            urllib.request.urlopen(url + '/dashboard', context=bad_ctx, timeout=5)
        except (ssl.SSLError, urllib.error.URLError, ConnectionResetError, OSError):
            pass
        else:
            raise AssertionError('Unauthenticated TLS client was accepted')
        print('PASS: TLS client certificates mandatory', flush=True)

        for path in ('/unknown', '/dashboard?secret=123', '/../../etc/passwd'):
            try:
                urllib.request.urlopen(url + path, context=ctx, timeout=5)
            except urllib.error.HTTPError as exc:
                assert exc.code == 404, (path, exc.code)
            else:
                raise AssertionError(f'Unexpected allowed route {path}')
        req = urllib.request.Request(url + '/ready', data=b'{}', method='POST')
        try:
            urllib.request.urlopen(req, context=ctx, timeout=5)
        except urllib.error.HTTPError as exc:
            assert exc.code == 405
        else:
            raise AssertionError('Mutating POST was allowed')
        print('PASS: route allowlist and read-only request handling', flush=True)

        gateway.terminate()
        gateway.wait(timeout=5)
        (creds / 'server.key').chmod(0o644)
        bad = subprocess.run(args, capture_output=True, timeout=10)
        assert bad.returncode != 0, 'Insecure private-key permissions must prevent startup'
        print('PASS: insecure server key rejected', flush=True)
    finally:
        if gateway.poll() is None:
            gateway.terminate()
            gateway.wait(timeout=5)
        upstream.shutdown()
        upstream.server_close()
print('All v0.14 development mTLS gateway checks passed.', flush=True)
