#!/usr/bin/env python3
"""Host regression tests for opt-in Linux thermal zone adapter.

Test fixtures emulate a sysfs thermal-zone file. This is not a real hardware test.
"""
import json
from pathlib import Path
import socket
import subprocess
import tempfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def wait_json(port, route, predicate, timeout=6):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{port}{route}', timeout=1) as resp:
                data = json.load(resp)
            if predicate(data):
                return data
        except (OSError, ValueError):
            pass
        time.sleep(.15)
    raise AssertionError(f'{route} did not reach expected condition')


def main():
    with tempfile.TemporaryDirectory(prefix='ve-thermal-') as folder:
        tmp = Path(folder)
        thermal = tmp / 'temp'
        cfg = tmp / 'diagnostics.conf'
        event = tmp / 'events.log'
        fault = tmp / 'fault-mode'
        exe = tmp / 'api'
        thermal.write_text('30125\n')
        cfg.write_text('max_temperature_c=35\nmax_vibration_g=0.3\nmin_voltage_v=3\n')
        port = free_port()
        cmd = ['gcc', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
               f'-DVE_PORT={port}', f'-DVE_TEMPERATURE_SYSFS="{thermal}"',
               f'-DVE_CONFIG_FILE="{cfg}"', f'-DVE_FAULT_FILE="{fault}"',
               f'-DVE_EVENT_FILE="{event}"',
               str(ROOT / 'services/telemetry/virtualedge-api.c'), '-o', str(exe)]
        subprocess.run(cmd, check=True)
        with (tmp / 'server.log').open('w') as log:
            proc = subprocess.Popen([str(exe)], stdout=log, stderr=subprocess.STDOUT)
            try:
                t = wait_json(port, '/api/v1/telemetry',
                              lambda d: d['sensors']['temperature_c'] == 30.12)
                assert t['sensors']['source'] == 'mixed', t
                assert t['sensors']['temperature_source'] == 'linux_thermal_sysfs'
                assert t['sensors']['vibration_g'] >= 0
                assert wait_json(port, '/api/v1/diagnostics', lambda d: d['fault_mask'] == 0)
                print('PASS: Millidegree sysfs adapter, per-sensor provenance')

                thermal.write_text('45100\n')
                wait_json(port, '/api/v1/diagnostics', lambda d: d['fault_mask'] == 1)
                print('PASS: Real-input pathway respects temperature threshold')

                thermal.write_text('not-a-temperature\n')
                wait_json(port, '/api/v1/diagnostics', lambda d: d['fault_mask'] == 8)
                t = wait_json(port, '/api/v1/telemetry',
                              lambda d: d['sensors']['temperature_c'] is None)
                assert t['health'] == 'warning'
                print('PASS: Malformed thermal input fails closed and produces valid JSON')

                thermal.unlink()
                wait_json(port, '/api/v1/diagnostics', lambda d: d['fault_mask'] == 8)
                print('PASS: Missing thermal input never silently falls back to simulation')

                thermal.write_text('27500\n')
                wait_json(port, '/api/v1/diagnostics', lambda d: d['fault_mask'] == 0)
                events = wait_json(port, '/api/v1/events', lambda d: d['count'] >= 3)
                assert events['events'][-1]['fault_mask'] == 0
                print('PASS: Recovery from acquisition fault is logged')
            finally:
                proc.terminate()
                try:
                    proc.wait(timeout=4)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
    print('All thermal sysfs adapter tests passed.')

if __name__ == '__main__':
    main()
