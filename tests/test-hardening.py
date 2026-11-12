#!/usr/bin/env python3
"""Host-only security/regression checks: HTTP parsing and event log bounds."""
import json
from pathlib import Path
import socket
import subprocess
import tempfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def request(port, raw):
    with socket.create_connection(('127.0.0.1', port), timeout=2) as sock:
        sock.settimeout(2)
        sock.sendall(raw)
        chunks = []
        while True:
            data = sock.recv(8192)
            if not data:
                break
            chunks.append(data)
    return b''.join(chunks)


def get_json(port, route):
    with urllib.request.urlopen(f'http://127.0.0.1:{port}{route}', timeout=3) as resp:
        return json.load(resp)


def until(predicate, limit=5):
    end = time.monotonic() + limit
    while time.monotonic() < end:
        try:
            if predicate():
                return
        except OSError:
            pass
        time.sleep(.2)
    raise AssertionError('Timed out waiting for diagnostic transition')


def main():
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        exe = d/'api'; fault = d/'fault'; log = d/'events.log'
        subprocess.run([
            'gcc','-std=c11','-O2','-Wall','-Wextra','-Werror',
            f'-DVE_PORT={port}', '-DVE_LOG_MAX_BYTES=200',
            f'-DVE_FAULT_FILE="{fault}"', f'-DVE_EVENT_FILE="{log}"',
            str(ROOT/'services/telemetry/virtualedge-api.c'),'-o',str(exe)
        ], check=True)
        with (d/'server.log').open('w') as out:
            p = subprocess.Popen([str(exe)],stdout=out,stderr=subprocess.STDOUT)
            try:
                until(lambda: get_json(port,'/health')['status']=='ok')
                for payload, code in [
                    (b'POST /health HTTP/1.1\r\nHost: localhost\r\n\r\n', 405),
                    (b'GET /health?x=1 HTTP/1.1\r\nHost: localhost\r\n\r\n', 400),
                    (b'GET /health HTTP/9.9\r\nHost: localhost\r\n\r\n', 400),
                    (b'GET /health\n', 400),
                    (b'GET /not-there HTTP/1.1\r\nHost: localhost\r\n\r\n', 404),
                    (b'GET /health HTTP/1.1\r\nHost: localhost\r\n\r\n', 200),
                ]:
                    resp=request(port,payload)
                    assert resp.startswith(f'HTTP/1.1 {code} '.encode()),(payload,resp[:100])
                print('PASS: HTTP rejects malformed, unsupported and non-GET requests')
                for mode, expected in [('overtemp',1),('multiple',7),('none',0),('vibration',2),('none',0)]:
                    fault.write_text(mode+'\n')
                    until(lambda: get_json(port,'/api/v1/diagnostics')['fault_mask']==expected)
                assert log.exists() and (d/'events.log.1').exists(), 'rotation missing'
                assert log.stat().st_size < 400
                assert (d/'events.log.1').stat().st_size < 400
                assert get_json(port,'/api/v1/events')['count']==5
                print('PASS: Rotated bounded event log and in-memory history')
            finally:
                p.terminate()
                try:p.wait(timeout=3)
                except subprocess.TimeoutExpired:p.kill();p.wait()
    print('All hardening checks passed.')

if __name__=='__main__':main()
