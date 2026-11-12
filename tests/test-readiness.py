#!/usr/bin/env python3
"""Host-side v0.12 liveness, readiness, metrics and fail-closed acceptance tests."""
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import tempfile
import time
from urllib.error import HTTPError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]


def request(port, path):
    try:
        with urlopen(f'http://127.0.0.1:{port}{path}', timeout=2) as response:
            return response.status, json.load(response)
    except HTTPError as error:
        return error.code, json.loads(error.read())


def wait_until(fn, timeout=4):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if fn():
                return
        except (OSError, ValueError):
            pass
        time.sleep(.05)
    raise AssertionError('condition not reached')


def main():
    with tempfile.TemporaryDirectory(prefix='ve-ready-') as dirname:
        d = Path(dirname)
        cfg, fault, thermal = (d / name for name in ('diagnostics.conf', 'fault-mode', 'thermal'))
        cfg.write_text('max_temperature_c=35\nmax_vibration_g=0.30\nmin_voltage_v=3\n')
        thermal.write_text('25300\n')
        with socket.socket() as s:
            s.bind(('127.0.0.1', 0))
            port = s.getsockname()[1]
        binary = d / 'api'
        subprocess.run([
            'gcc', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
            f'-DVE_PORT={port}', f'-DVE_CONFIG_FILE="{cfg}"',
            f'-DVE_FAULT_FILE="{fault}"', f'-DVE_TEMPERATURE_SYSFS="{thermal}"',
            f'-DVE_EVENT_FILE="{d / "events.log"}"',
            str(ROOT / 'services/telemetry/virtualedge-api.c'), '-o', str(binary)
        ], check=True)
        with (d / 'server.log').open('w') as logfile:
            proc = subprocess.Popen([str(binary)], stdout=logfile, stderr=subprocess.STDOUT)
            try:
                wait_until(lambda: request(port, '/ready')[0] == 200)
                status, health = request(port, '/health')
                assert (status, health['status']) == (200, 'ok')
                status, ready = request(port, '/ready')
                assert (status, ready['status']) == (200, 'ready')
                status, metrics = request(port, '/api/v1/metrics')
                assert status == 200 and metrics['ready'] is True
                assert metrics['memory_available_kb'] >= 0
                print('PASS: liveness distinct from readiness; operational metrics')

                thermal.write_text('not-a-number\n')
                wait_until(lambda: request(port, '/ready')[0] == 503, timeout=4)
                status, result = request(port, '/ready')
                assert status == 503 and result['sensor_acquisition_valid'] is False
                assert request(port, '/health')[0] == 200
                print('PASS: broken physical temperature input fails readiness, not liveness')

                thermal.write_text('27500\n')
                wait_until(lambda: request(port, '/ready')[0] == 200)
                print('PASS: sensor recovery restores readiness')

                cfg.write_text('invalid-key=1\n')
                os.kill(proc.pid, signal.SIGHUP)
                wait_until(lambda: request(port, '/ready')[0] == 503)
                assert request(port, '/ready')[1]['config_valid'] is False
                assert request(port, '/health')[0] == 200
                print('PASS: rejected configuration fails readiness')

                cfg.write_text('max_temperature_c=35\nmax_vibration_g=0.30\nmin_voltage_v=3\n')
                os.kill(proc.pid, signal.SIGHUP)
                wait_until(lambda: request(port, '/ready')[0] == 200)
                print('PASS: valid configuration reload restores readiness')

                fault.write_text('overtemp\n')
                wait_until(lambda: request(port, '/api/v1/diagnostics')[1]['fault_mask'] == 1)
                assert request(port, '/ready')[0] == 200
                print('PASS: simulated threshold alert does not falsely mark API unready')
            finally:
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
    print('PASS: All v0.12 readiness and metrics host tests')


if __name__ == '__main__':
    main()
