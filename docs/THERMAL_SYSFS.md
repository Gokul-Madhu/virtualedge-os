# Linux thermal-zone adapter (v0.6 experimental hardware integration)

VirtualEdge OS is a Buildroot-based Linux prototype. Its default QEMU target uses
**simulated temperature, vibration and voltage**. Version 0.6 adds a strictly
opt-in Linux thermal-zone temperature reader for a future real board.

## Build and deployment

On an actual target with a readable kernel thermal-zone sysfs node:

```bash
ls -l /sys/class/thermal/thermal_zone*/temp
cat /sys/class/thermal/thermal_zone0/type
cat /sys/class/thermal/thermal_zone0/temp
```

Check which thermal zone represents the measurement of interest: often a CPU/SoC
thermal zone, **not** ambient temperature. The kernel driver must expose the zone;
this release does not install or implement physical sensor drivers.

From WSL build the system using an explicit absolute Linux thermal-zone path:

```bash
cd ~/dev/virtualedge-os
VE_TEMPERATURE_SYSFS_PATH=/sys/class/thermal/thermal_zone0/temp \
  ./scripts/build-and-test.sh --qemu
```

**Caution:** The path belongs to the **guest/target**, not WSL. If you build a
QEMU image with this option, QEMU must expose a compatible thermal zone or the
API will report `invalid_sensor` and null temperature, as designed.
For normal QEMU acceptance tests, omit the variable to retain simulation mode.

## Telemetry provenance and fail-closed behavior

- Default build: `sensors.source=simulation`, `temperature_source=simulation`.
- Thermal-enabled build: `sensors.source=mixed`,
  `temperature_source=linux_thermal_sysfs`. Voltage and vibration remain
  simulated; do not interpret them as physical measurements.
- The input uses Linux's millidegree-Celsius text convention. Invalid, missing,
  unreadable, out-of-range values produce JSON `temperature_c:null`, health
  `warning`, and diagnostic `invalid_sensor` (mask bit 8). No silent fallback.
- Fault-mode injection stays for development only; the API listens on loopback
  by default. Remove test fault injection from production designs.
- Changes to the thermal file are sampled approximately once per second; health
  transitions enter event history.

## Testing

`python3 tests/test-thermal-sysfs.py` compiles the native C app and emulates a
thermal sysfs node through a fixture. It tests valid milli-Celsius readings,
thresholds, malformed/missing inputs and recovery. These tests do **not** validate
hardware I2C/SPI drivers, board BSPs, kernel thermal driver integration, or
physical measurement accuracy.
