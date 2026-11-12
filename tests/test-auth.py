#!/usr/bin/env python3
"""Opt-in HTTP Basic protection and split-request compatibility regression."""
import base64
import http.client
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]


def send(port, route, header=None, split=False):
    sock = socket.create_connection(('127.0.0.1', port), timeout=3)
    sock.settimeout(3)
    request = 'GET ' + route + ' HTTP/1.1\r\nHost: localhost\r\n'
    if header is not None:
        request += f'Authorization: Basic {header}\r\n'
    request += 'Connection: close\r\n\r\n'
    raw = request.encode('ascii')
    try:
        if split:
            sock.sendall(raw[:5]); time.sleep(.03)
            sock.sendall(raw[5:15]); time.sleep(.03)
            sock.sendall(raw[15:])
        else:
            sock.sendall(raw)
        answer = bytearray()
        while True:
            chunk = sock.recv(65536)
            if not chunk: break
            answer.extend(chunk)
    finally:
        sock.close()
    code = int(answer.split(b'\r\n', 1)[0].split()[1])
    return code, bytes(answer)


def freeport():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def run():
    with tempfile.TemporaryDirectory(prefix='ve13-auth-') as folder:
        d = Path(folder)
        port = freeport()
        exe = d / 'api'
        subprocess.run(['gcc', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
                        f'-DVE_PORT={port}', f'-DVE_DASHBOARD_FILE="{ROOT / "board/virtualedge/rootfs-overlay/usr/share/virtualedge/dashboard.html"}"', f'-DVE_EVENT_FILE="{d / "events"}"',
                        str(ROOT / 'services/telemetry/virtualedge-api.c'), '-o', str(exe)], check=True)
        key = base64.b64encode(b'virtualedge:' + os.urandom(32)).decode('ascii')
        auth = d / 'auth'
        auth.write_text(key + '\n')
        auth.chmod(0o600)
        env = {**os.environ, 'VE_AUTH_FILE': str(auth)}
        with (d / 'server.log').open('wb') as log:
            proc = subprocess.Popen([str(exe)], env=env, stdout=log, stderr=subprocess.STDOUT)
            try:
                for _ in range(80):
                    try:
                        status, _ = send(port, '/health')
                        break
                    except OSError:
                        if proc.poll() is not None:
                            raise AssertionError('authenticated API exited early')
                        time.sleep(.05)
                else: raise AssertionError('timeout')
                assert status == 401
                assert send(port, '/dashboard')[0] == 401
                assert send(port, '/api/v1/config')[0] == 401
                assert send(port, '/health', 'not-valid')[0] == 401
                print('PASS: unauthorized requests rejected across dashboard and APIs')
                assert send(port, '/health', key)[0] == 200
                code, page = send(port, '/dashboard', key, split=True)
                assert code == 200 and b'<!doctype html>' in page
                assert send(port, '/api/v1/telemetry', key)[0] == 200
                print('PASS: authorized requests and split TCP headers accepted')
            finally:
                proc.terminate()
                try: proc.wait(timeout=4)
                except subprocess.TimeoutExpired: proc.kill(); proc.wait()

        auth.chmod(0o644)
        proc = subprocess.run([str(exe)], env=env, capture_output=True, timeout=3)
        assert proc.returncode != 0 and b'authentication file' in proc.stderr
        print('PASS: insecure credential-file permissions fail closed')
        auth.unlink()
        proc = subprocess.run([str(exe)], env=env, capture_output=True, timeout=3)
        assert proc.returncode != 0
        print('PASS: missing credential file fails closed')


if __name__ == '__main__': run()
