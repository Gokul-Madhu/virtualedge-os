#!/usr/bin/env python3
"""Test restart-on-exit and clean child stop for the supervisor."""
from pathlib import Path
import os
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
SUP = ROOT/'board/virtualedge/rootfs-overlay/usr/bin/virtualedge-supervisor'

with tempfile.TemporaryDirectory() as td:
    tmp=Path(td)
    counter=tmp/'starts'
    child=tmp/'child.sh'
    child.write_text(f'''#!/bin/sh
printf x >> "{counter}"
if [ "$(wc -c < "{counter}")" -lt 2 ]; then
    exit 3
fi
exec sleep 40
''')
    child.chmod(0o755)
    env={**os.environ,'VE_DAEMON':str(child)}
    with (tmp/'supervisor.log').open('w') as logs:
        process=subprocess.Popen(['sh',str(SUP)],env=env,stdout=logs,stderr=subprocess.STDOUT)
        try:
            until=time.monotonic()+8
            while (not counter.exists() or counter.stat().st_size<2) and time.monotonic()<until:
                time.sleep(.1)
            assert counter.exists() and counter.stat().st_size>=2, 'supervisor failed to restart child'
            print('PASS: Supervisor automatically restarts exited daemon')
        finally:
            process.terminate()
            process.wait(timeout=5)
        assert process.returncode == 0, process.returncode
        print('PASS: Supervisor terminates cleanly on SIGTERM')
