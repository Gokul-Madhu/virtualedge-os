#!/usr/bin/env python3
"""Configuration management: hostile input, atomic update, SIGHUP, read-only APIs."""
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import tempfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def api(port, route):
    with urllib.request.urlopen(f'http://127.0.0.1:{port}{route}', timeout=3) as r:
        assert r.status == 200
        return json.load(r)


def wait_until(test):
    for _ in range(40):
        try:
            if test():
                return
        except (OSError, AssertionError):
            pass
        time.sleep(.1)
    raise AssertionError('timed out')


def main():
    with tempfile.TemporaryDirectory() as folder:
        d = Path(folder)
        cfg = d / 'diagnostics.conf'
        cfg.write_text('max_temperature_c=35\nmax_vibration_g=0.3\nmin_voltage_v=3\n')
        fault = d / 'fault-mode'
        api_exe = d / 'api'
        cli_exe = d / 'config'
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        flags = ['gcc', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', f'-DVE_CONFIG_FILE="{cfg}"']
        subprocess.run(flags + [str(ROOT/'services/telemetry/virtualedge-config.c'), '-o', str(cli_exe)], check=True)
        subprocess.run(flags + [f'-DVE_PORT={port}', f'-DVE_FAULT_FILE="{fault}"',
                                f'-DVE_EVENT_FILE="{d / "events.log"}"',
                                str(ROOT/'services/telemetry/virtualedge-api.c'), '-o', str(api_exe)], check=True)
        cmd = lambda *args: subprocess.run([str(cli_exe), *args], capture_output=True, text=True)
        assert cmd('validate').returncode == 0
        assert '35' in cmd('show').stdout
        assert cmd('set', 'max_temperature_c', 'nan').returncode != 0
        assert cmd('set', 'max_temperature_c', '155').returncode != 0
        assert cmd('set', 'nonsense', '3').returncode != 0
        assert cfg.read_text().startswith('max_temperature_c=35')
        print('PASS: Validated local configuration and rejected invalid input')
        with (d / 'server.log').open('w') as log:
            p = subprocess.Popen([str(api_exe)], stdout=log, stderr=subprocess.STDOUT)
            try:
                wait_until(lambda: api(port, '/health')['status'] == 'ok')
                dev = api(port, '/api/v1/device')
                assert dev['name'] == 'VirtualEdge OS'
                assert dev['control_api_enabled'] is False
                config = api(port, '/api/v1/config')
                assert config['read_only'] is True and config['config_valid'] is True
                initial_rev = config['config_revision']
                assert cmd('set', 'max_temperature_c', '25').returncode == 0
                os.kill(p.pid, signal.SIGHUP)
                wait_until(lambda: api(port, '/api/v1/config')['thresholds']['max_temperature_c'] == 25)
                config = api(port, '/api/v1/config')
                assert config['config_revision'] > initial_rev
                assert api(port, '/api/v1/diagnostics')['thresholds']['max_temperature_c'] == 25
                print('PASS: Device info, read-only configuration API and live SIGHUP reload')
                before = cfg.read_bytes()
                assert cmd('set', 'max_vibration_g', '-2').returncode != 0
                assert cfg.read_bytes() == before
                cfg.write_text('max_temperature_c=22\nwrong_key=1\n')
                os.kill(p.pid, signal.SIGHUP)
                wait_until(lambda: api(port, '/api/v1/config')['config_valid'] is False)
                assert api(port, '/api/v1/config')['thresholds']['max_temperature_c'] == 25
                print('PASS: Invalid reload preserves previously verified thresholds')
            finally:
                p.terminate()
                try:
                    p.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    p.kill(); p.wait()
    print('All device configuration host tests passed.')

if __name__ == '__main__':
    main()
