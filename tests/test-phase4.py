#!/usr/bin/env python3
"""Host integration: isolated TCP port, config, injection, events, recovery."""
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def fetch(port, path):
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=3) as resp:
        assert resp.status == 200
        return json.load(resp)


def wait_for(condition, limit=8):
    until = time.monotonic() + limit
    while time.monotonic() < until:
        try:
            answer = condition()
            if answer is not None:
                return answer
        except (OSError, ValueError, AssertionError):
            pass
        time.sleep(0.2)
    raise AssertionError("Timed out waiting for expected state")


def main():
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        cfg = tmp / "diagnostics.conf"
        fault = tmp / "fault-mode"
        logfile = tmp / "events.log"
        exe = tmp / "virtualedge-api"
        cfg.write_text("max_temperature_c=39\nmax_vibration_g=0.3\nmin_voltage_v=3.0\n")
        subprocess.run([
            "gcc", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
            f'-DVE_CONFIG_FILE="{cfg}"',
            f'-DVE_EVENT_FILE="{logfile}"',
            f'-DVE_FAULT_FILE="{fault}"',
            f"-DVE_PORT={port}",
            f'-DVE_DASHBOARD_FILE="{ROOT / "board/virtualedge/rootfs-overlay/usr/share/virtualedge/dashboard.html"}"',
            str(ROOT / "services/telemetry/virtualedge-api.c"),
            "-o", str(exe),
        ], check=True)
        with open(tmp / "server.log", "w") as out:
            proc = subprocess.Popen([str(exe)], stdout=out, stderr=subprocess.STDOUT)
            try:
                wait_for(lambda: fetch(port, "/health"))
                telemetry = fetch(port, "/api/v1/telemetry")
                assert telemetry["sensors"]["source"] == "simulation"
                assert fetch(port, "/api/v1/diagnostics")["fault_mask"] == 0
                assert fetch(port, "/api/v1/events")["count"] == 0
                print("PASS: Health, telemetry, baseline diagnostics")

                with urllib.request.urlopen(f"http://127.0.0.1:{port}/dashboard", timeout=3) as page:
                    assert page.status == 200
                    assert page.headers.get_content_type() == "text/html"
                    dashboard = page.read().decode("utf-8")
                assert "VirtualEdge OS" in dashboard
                assert "Live sensor telemetry" in dashboard
                assert "/api/v1/diagnostics" in dashboard
                assert "fault-mask" in dashboard
                assert "<script>" in dashboard
                print("PASS: Dashboard HTML served with live API bindings")

                fault.write_text("overtemp\n")
                wait_for(lambda: fetch(port, "/api/v1/diagnostics") if fetch(port, "/api/v1/diagnostics")["fault_mask"] == 1 else None)
                events = fetch(port, "/api/v1/events")
                assert events["count"] == 1 and events["events"][0]["fault_mask"] == 1
                assert fetch(port, "/api/v1/telemetry")["health"] == "warning"
                time.sleep(1.3)
                assert fetch(port, "/api/v1/events")["count"] == 1
                print("PASS: Overtemperature event, no duplicate events")

                fault.write_text("multiple\n")
                wait_for(lambda: fetch(port, "/api/v1/diagnostics") if fetch(port, "/api/v1/diagnostics")["fault_mask"] == 7 else None)
                assert fetch(port, "/api/v1/events")["count"] == 2
                print("PASS: Multiple simultaneous faults")

                fault.write_text("none\n")
                wait_for(lambda: fetch(port, "/api/v1/diagnostics") if fetch(port, "/api/v1/diagnostics")["fault_mask"] == 0 else None)
                events = fetch(port, "/api/v1/events")
                assert events["count"] == 3
                assert events["events"][-1]["previous_mask"] == 7
                assert events["events"][-1]["fault_mask"] == 0
                assert len(logfile.read_text().splitlines()) == 3
                print("PASS: Recovery and persistent transition log")

                try:
                    urllib.request.urlopen(f"http://127.0.0.1:{port}/not-found", timeout=3)
                    raise AssertionError("404 was not returned")
                except urllib.error.HTTPError as ex:
                    assert ex.code == 404
                print("PASS: Unknown routes return 404")
            finally:
                proc.terminate()
                try:
                    proc.wait(timeout=4)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
        print("All Phase 4 host integration tests passed.")


if __name__ == "__main__":
    main()
