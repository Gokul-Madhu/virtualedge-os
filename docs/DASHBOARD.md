# VirtualEdge OS Control Center (Phase 4D)

A responsive, dependency-free browser dashboard ships **inside the Buildroot root filesystem** at `/usr/share/virtualedge/dashboard.html`. The native C service serves it at `/` and `/dashboard` and fetches telemetry/diagnostics/events from the existing local JSON API every two seconds. Features: system health, three sensor readings, short in-browser trend charts, memory and uptime, fault flags, recent transitions and offline feedback. **Read-only**; cannot trigger faults or change configuration.

## Immediate Windows preview (no QEMU rebuild required)

Within WSL VirtualEdge-Ubuntu:

```bash
cd ~/dev/virtualedge-os
./scripts/preview-dashboard.sh
```

From Windows on the same computer, browse to `http://localhost:18081/dashboard`. WSL localhost forwarding normally makes this accessible. Keep the WSL terminal open, press Ctrl+C to stop. This preview reports **WSL host memory/uptime**, not the ARM guest, while the sensor readings remain simulated.

## Run on the actual QEMU guest

`./scripts/build-and-test.sh` installs the dashboard file and cross-compiled service into the ARM64 image. Run QEMU normally and test within the guest:

```bash
wget -O /tmp/dashboard.html http://127.0.0.1:8080/dashboard
head -c 80 /tmp/dashboard.html
```

To view *guest* measurements from the Windows browser, a controlled QEMU loopback port forward is required; the default guest API binds to `127.0.0.1` and is not remotely reachable.

1. With QEMU stopped, inside WSL edit the generated launcher `out/buildroot/images/start-qemu.sh` (after making a backup) and change **only** `-netdev user,id=eth0` to `-netdev user,id=eth0,hostfwd=tcp:127.0.0.1:18080-:8080` (do not duplicate the `-netdev` argument).
2. To permit QEMU's forwarded connection to reach the guest service, in the **WSL source overlay** create `board/virtualedge/rootfs-overlay/etc/default/virtualedge-api` with the line `VE_LISTEN_ANY=1`. This enables binding to all *guest* interfaces, **without authentication**; use only with QEMU user-mode NAT and the host-loopback port forward. Do not use for production or bridge the guest to untrusted networks.
3. Rebuild with `./scripts/build-and-test.sh`, then boot `./start-qemu.sh` from the images directory.
4. Browse from the WSL/Windows host to `http://localhost:18080/dashboard` (on Windows, WSL localhost forwarding must be functioning).

Rebuilding Buildroot may regenerate `start-qemu.sh`; confirm the hostfwd argument after a rebuild. Do not expose port 18080 on non-loopback interfaces or public networks. Neither TLS nor authentication exists in the current prototype. A true embedded graphical desktop would require additional display drivers, GPU/framebuffer, input support, much more RAM and a different target image; the browser UI avoids those costs.
