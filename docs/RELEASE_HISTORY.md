# VirtualEdge OS v0.36 — Baseline-first real QEMU OTA acceptance

The OTA acceptance launcher now performs a **real ARM64 smoke boot of the confirmed baseline** before staging the candidate, then tests confirmation and fallback. The gate refuses symlinked confirmed images and pending A/B state. Host tests cover fail-closed operation; actual five-boot acceptance still requires the user’s WSL QEMU environment. See [`docs/QEMU_BASELINE_SMOKE_036.md`](QEMU_BASELINE_SMOKE_036.md). This remains a development platform, not certified production OTA.

---

# VirtualEdge OS v0.35 — QEMU A/B Acceptance Hardening

Based on the v0.34 development source. This update detects fatal ARM64 boot
failures immediately and validates candidate/retry/fallback slot and version
sequences in QEMU acceptance reports. It does not implement physical OTA,
secure boot, or hardware power-loss recovery.

See `docs/QEMU_AB_ACCEPTANCE_035.md` for the WSL acceptance procedure.

# VirtualEdge OS v0.34 — QEMU OTA acceptance gate and hardware roadmap

This release builds on v0.33. The new `scripts/accept-qemu-ota.py` runs the
existing **non-mutating signed-update preflight** before any guest boot, refuses
to operate while another QEMU process is running, executes the disposable
confirmation/fallback QEMU test, and validates the returned JSON report for
**real ARM64 guest evidence** (not a host-test stub). Existing A/B state, images
and persistent data are not modified by the acceptance tests.

Host checks: `python3 tests/test-ota-accept-entry.py` and
`python3 tests/test-ota-preflight.py`.

WSL acceptance (after Buildroot and A/B initialization):

```bash
mkdir -p "$HOME/virtualedge-test-reports"
python3 scripts/accept-qemu-ota.py \
  --state-dir out/ab \
  --data-image out/persistent/virtualedge-data.ext4 \
  --bundle out/ota-demo/virtualedge-test-0.33.0.tar \
  --public-key "$HOME/virtualedge-private-keys/dev-ed25519.pub.pem" \
  --scenario both --timeout 240 \
  --report "$HOME/virtualedge-test-reports/ota-accept-01.json"
```

Instructions: [docs/QEMU_OTA_ACCEPTANCE_034.md](QEMU_OTA_ACCEPTANCE_034.md).
Hardware, bootloader, secure boot and power-interruption requirements:
[docs/HARDWARE_SECUREBOOT_POWERLOSS_PLAN_034.md](HARDWARE_SECUREBOOT_POWERLOSS_PLAN_034.md).

**No real ARM64/QEMU OTA success claim is made by this source release.** It must
be run against a built guest in the user's WSL installation. Physical OTA,
bootloader integration, secure boot, and actual electrical power-loss testing
remain unimplemented and unqualified.

---

# VirtualEdge OS v0.33 — QEMU OTA preflight and integration hardening

Adds **non-mutating preflight** before the full ARM64 acceptance test. It verifies the independently signed bundle, A/B slot integrity, ext filesystem image format, pending-update state, and available space. It clearly warns when the candidate is byte-identical to the confirmed image (an update-mechanism test, **not** an application upgrade). Includes negative tests for altered images, bad filesystem magic and unsafe symlink inputs. Original v0.32 monitoring, TLS, persistent storage, A/B tooling and automatic dashboard launcher are retained.

Host test: `python3 tests/test-ota-preflight.py`.

Example in Ubuntu WSL, with QEMU stopped and a previously initialized `out/ab` state:

```bash
python3 scripts/preflight-qemu-ota.py \
  --state-dir out/ab \
  --data-image out/persistent/virtualedge-data.ext4 \
  --bundle out/ota-demo/virtualedge-test-0.33.0.tar \
  --public-key "$HOME/virtualedge-private-keys/dev-ed25519.pub.pem"
```

After **PASS**, run the existing `scripts/test-qemu-ota.py` with matching arguments and `--scenario both --report <new-output-file>`. The preflight does not invoke QEMU or prove a candidate can boot. It does not create, change or reinitialize A/B state. Full ARM64 confirmation/fallback has **not** been executed in this environment. Hardware boot security, on-device partition installation and physical power-loss behavior remain outside this release.

---

# VirtualEdge OS v0.32 — Auditable QEMU OTA trace

Adds per-boot A/B evidence to the OTA JSON report, explicit promotion/fallback outcomes, runner provenance, and report-path isolation. Original input SHA-256 checks remain in place. Host-only trace tests passed; real QEMU boot acceptance remains pending on the WSL machine. See [docs/QEMU_OTA_TRACE_032.md](QEMU_OTA_TRACE_032.md).

---

# VirtualEdge OS v0.31 — QEMU OTA acceptance evidence

Adds SHA-256 fingerprints of original A/B metadata, populated rootfs slot
files and persistent data disks, with before/after non-mutation checks even
on acceptance failure. The QEMU acceptance runner can now write a **new**, mode
0600 JSON report using `--report PATH` and refuses to overwrite old reports.
Dedicated host evidence tests: `python3 tests/test-ota-evidence.py`.
See [docs/QEMU_OTA_EVIDENCE_031.md](QEMU_OTA_EVIDENCE_031.md).
Real QEMU ARM64 acceptance is still pending in the user's WSL installation.
No physical OTA, secure boot, tamper-proof attestation or power-loss guarantee.

---

# VirtualEdge OS v0.30 — Disposable QEMU OTA acceptance

New `scripts/test-qemu-ota.py` ties signed update staging to isolated QEMU candidate boots, guest health checks, explicit confirmation and two-attempt fallback. Both scenarios use temporary copies, so original A/B metadata and persistent data disk remain untouched. Host orchestration tests use a guest stub; real ARM64 tests require WSL/QEMU. See [docs/QEMU_OTA_ACCEPTANCE_030.md](QEMU_OTA_ACCEPTANCE_030.md). This is **not** guest-side OTA, verified boot, or power-loss-tested installation.

---

# VirtualEdge OS v0.29 — Verified guest image → QEMU A/B handoff

**New:** `tools/virtualedge_ab_import.py` securely transfers an **offline-exported**
v0.28 `inactive-slot.img` into the existing QEMU A/B manager, but only when it
matches a signed candidate manifest and passes independent Ed25519, SHA-256,
board and version verification. The confirmed QEMU slot is preserved; an
unconfirmed candidate retains the existing two-attempt fallback behavior.

Host tests: `python3 tests/test-ab-guest-handoff.py` (6 checks passed). Details
and commands: [`docs/GUEST_AB_HANDOFF_029.md`](GUEST_AB_HANDOFF_029.md).
**No raw-disk writes, production OTA, or actual QEMU guest boot is included.**

---

# VirtualEdge OS v0.20 — Development identity rotation and CRL validity

This release adds a validated `rotate <old_identity> <new_identity>` workflow and rejects expired/not-yet-valid CRLs while building the separate development TLS disk. The old identity is revoked after verifying the replacement, and the operator must distribute new client credentials and deploy the fresh CRL manually. **Not automatic renewal, remote enrollment, or production key protection.**

See [`docs/IDENTITY_ROTATION_020.md`](IDENTITY_ROTATION_020.md). New tests: `python3 tests/test-identity-rotation.py`. ARM64 cross-build, QEMU reboot/disk swap and real-board deployment have not been verified in this environment.

---

# VirtualEdge OS v0.18 — Isolated TLS Development Credentials

**New milestone:** Credential-staging into the firmware root filesystem is disabled. Native guest mTLS can load test credentials from a **separate read-only QEMU disk**. This is unencrypted development storage, not production key protection.

- Release instructions and migration: [`docs/TLS_DISK_018.md`](TLS_DISK_018.md).
- Host tests: `python3 tests/test-tls-disk.py` and `python3 tests/test-native-tls.py`.
- Create test disk: `python3 tools/virtualedge_tls_image.py --credentials "$HOME/.virtualedge/tls-v018-dev" --output out/persistent/virtualedge-tls-dev.ext4`.
- The QEMU launcher `./scripts/run-qemu-native-tls.sh` explicitly enables TLS with `ve_tls_dev=1`; it does **not** forward plaintext HTTP.
- Build security checks reject old TLS credential directories in the overlay and Buildroot target. **Remove historical credentials before rebuilding; do not share previously generated firmware images.**
- ARM64 build, full regression and QEMU native mTLS acceptance must still run in the user's WSL installation.

---

# VirtualEdge OS — Embedded Linux Edge Monitoring Prototype — v0.11 QEMU acceptance prototype

A custom Buildroot ARM64/Linux distribution targeting QEMU `virt` with native C-based telemetry, simulated sensor diagnostics, a lightweight browser dashboard, and a small process supervisor.

## Functional capabilities

- Hostname and system-monitoring boot scripts using a root filesystem overlay.
- Read-only dashboard (`GET /dashboard`) served directly by the C API.
- Local HTTP endpoints: `/health`, `/api/v1/telemetry`, `/api/v1/diagnostics`, `/api/v1/events`.
- Linux uptime, memory and load measurements, **separate from simulated** voltage/vibration/temperature.
- Threshold configuration at `/etc/virtualedge/diagnostics.conf`, read at daemon startup.
- Development-only fault injection through `/run/virtualedge/fault-mode` (`none`, `overtemp`, `vibration`, `undervoltage`, `multiple`).
- Automatic sampling every second, event transitions, 32-event in-memory history, file logging with one 64 KiB rotated previous segment.
- Boot service starts a tiny restart-on-crash supervisor.
- Simple bounded HTTP request-line parsing and default loopback-only listener. Not an Internet-facing server.

## Build on your existing Ubuntu WSL installation

After backing up the source, extract the archive **into** `~/dev/virtualedge-os`, preserving your existing `out/buildroot` and `~/tools/buildroot-2026.08.1`.

```bash
cd ~/dev/virtualedge-os
./scripts/test-host.sh       # Tests on WSL; runs without Buildroot
./scripts/preview-dashboard.sh # Browser preview: http://localhost:18081/dashboard
./scripts/build-and-test.sh  # Rebuild ARM64 image using existing Buildroot
```

Power off QEMU before running the image rebuild. Start it with `cd out/buildroot/images && ./start-qemu.sh`. Inside QEMU, login root and run `virtualedge-selftest`. See `docs/QEMU_ACCEPTANCE.md`.

## Important limitations

This release is an embedded Linux **prototype**, not a finished industrial OS. Physical sensor interfaces, secure remote access, signed OTA, complete configuration and production-level networking remain outside its current functionality. Only prior versions were boot-verified in the user's QEMU environment; this new revision has been host-tested but not QEMU-tested here. See `docs/RELEASE_STATUS.md` and `docs/DASHBOARD.md`.

## Version 0.5: automated acceptance and bounded API history

- The event API serializes only **complete, newest events that fit** the bounded JSON reply. Its `count` describes included events, not all historical transitions. `tests/test-events-capacity.c` tests ring wrap and capacity.
- `scripts/test-qemu.py` boots a **disposable copy** of the ext4 guest image, logs in on the serial console, executes `virtualedge-selftest`, and exits nonzero on failure or timeout. No additional Python packages required.
- After setting up Buildroot, `./scripts/build-and-test.sh --qemu` runs host tests, cross-compiles, rebuilds the rootfs, and performs a guest smoke test. `python3 scripts/test-qemu.py` can run separately against an existing image.
- The QEMU acceptance harness is **not yet executed in this environment**; its first real run must be performed in Ubuntu WSL and its result retained. The API is still unauthenticated and loopback-only by default.

**Deployment warning:** This is not a certified or production-ready industrial OS. No hardware driver/board integration, secure OTA, hardware safety case, or full endurance qualification is provided.

## Version 0.6: optional Linux thermal-zone acquisition

- Default image still simulates all sensors, preserving your current QEMU test workflow.
- For boards with Linux thermal-zone drivers, opt into a temperature sysfs node
  during the ARM64 build using `VE_TEMPERATURE_SYSFS_PATH` (see
  `docs/THERMAL_SYSFS.md`).
- Temperature data identifies its origin; invalid/unavailable physical inputs yield
  `null` in JSON, bit 8 in diagnostics, and automatic recovery events.
- Tests: `./scripts/test-host.sh` runs the new thermal sysfs fixture suite
  alongside previous tests.
- This is **not a generic I2C/SPI sensor driver**, and it is not verified on a
  physical board. Simulation continues for vibration and voltage. The existing
  unauthenticated API must remain loopback-only except in controlled QEMU tests.

## Version 0.7: validated local device management

- Added ARM64 `virtualedge-config` utility for privileged local threshold edits, with strict validation and atomic update.
- Added runtime threshold reload using `killall -HUP virtualedge-api`, retaining last known-good thresholds on malformed config.
- Added read-only `/api/v1/device` and `/api/v1/config` endpoints. Dashboard displays device hostname and configuration status.
- Host integration tests passed; updated guest build and physical hardware execution not yet verified.
- See `docs/DEVICE_MANAGEMENT.md` and `docs/RELEASE_07.md`.

## Version 0.8: offline signed update trust chain

- `tools/virtualedge_release.py` signs exact image bytes with an offline Ed25519 key via OpenSSL 3, using a canonical manifest binding SHA-256, board identifier, and numeric version.
- Verification rejects changed images, altered manifests, wrong boards, rollback versions, malformed bundles, and oversize images.
- **This is release preparation and pre-installation verification, not OTA.** It does not partition a device, write a bootloader, flash a filesystem, update itself in-guest, or implement A/B rollback. See `docs/SIGNED_RELEASES.md`.
- Buildroot/QEMU boot validation and real board tests still require your WSL/hardware environment.

## Version 0.9: optional persistent data volume

- Added a **second QEMU ext4 disk** (`out/persistent/virtualedge-data.ext4`) with a reuse-safe launcher and early boot mounting.
- Configuration and event logs can be stored independently of the root filesystem image. This is **not** A/B OTA or power-failure qualified.
- Host tests cover launcher creation/reuse and source invariants; actual QEMU bind-mount and reboot persistence still need WSL acceptance.
- See `docs/PERSISTENT_DATA.md` for commands and cautions.

## v0.10 QEMU A/B root filesystem evaluation

The optional QEMU-only slot manager can stage an offline **signed** rootfs
image into the inactive slot, select it for two trial boots and fall back to
the confirmed slot if no operator confirms success. It retains v0.9's
separate data volume. See [`docs/AB_QEMU.md`](AB_QEMU.md) for a safe
host-side walkthrough and release limitations. This feature is **not**
production OTA, verified boot, or hardware-certified rollback.

## Version 0.11: automated QEMU candidate acceptance

The A/B host manager can now run the **selected pending rootfs** through the serial QEMU acceptance harness and verify its guest-reported slot/version and `virtualedge-selftest` result. `scripts/check-ab-candidate.py` leaves the candidate pending unless explicitly invoked with `--confirm-on-pass`. Failed tests preserve the old confirmed slot. Test disks are disposable copies. See `docs/AB_GUEST_ACCEPTANCE_011.md`. This is **not** real device OTA, verified boot, or production rollback.

## v0.12 — Health-gated guest acceptance

The guest now distinguishes liveness (`GET /health`) from readiness (`GET /ready`): a misconfigured device or failed thermal acquisition gets `503` readiness while the API can remain alive. `GET /api/v1/metrics` provides bounded operational measurements. `virtualedge-selftest` checks readiness, so the host A/B candidate acceptance workflow cannot mark a guest as passing if these checked conditions fail. See [`docs/RELEASE_012.md`](RELEASE_012.md) for constraints and verification.

## v0.13 — opt-in local dashboard/API authentication

The C HTTP server optionally requires a Basic-auth credential for every route,
including the dashboard. Credentials are provisioned **on the guest** using
`virtualedge-auth-setup`, never embedded in this source archive. Unauthorized
requests return 401 and invalid/missing credentials fail closed when explicitly
enabled. Full host regression and dedicated split-TCP/authentication tests are
provided in `tests/test-auth.py`.

**This is not secure remote management:** Basic auth over HTTP exposes credentials
to anyone able to observe traffic. Keep access local to QEMU/loopback or use an
external authenticated TLS tunnel; see `docs/LOCAL_AUTH_013.md`. No HTTPS server,
secure boot, on-device OTA, physical sensor certification or industrial
qualification is claimed. v0.13 ARM64/QEMU validation remains pending.

## v0.14 — Host-side mutually authenticated TLS gateway (development only)

A separate **WSL host-side** HTTPS gateway protects browser/API requests using
mutual TLS (mTLS), certificates generated locally and an explicit read-only
route allowlist. It forwards traffic solely to the local QEMU port at
`127.0.0.1:18080`. TLS 1.2+ and client certificates are mandatory. Guest Basic
auth can be forwarded with `--forward-basic` when deliberately provisioned.
See `docs/TLS_GATEWAY_014.md` for setup and remaining security constraints.

This does **not** add TLS to the ARM64 guest, secure remote fleet management,
hardware-rooted identities, credential rotation, or production authorization.
The old plaintext QEMU port remains reachable on the Windows/WSL loopback
interface, so TLS cannot be used as a defense against untrusted programs on
the same host. Do not expose the development gateway to the Internet.

## v0.15 — native guest mutual TLS (opt-in)

The ARM64 guest now has a native C/OpenSSL mTLS server (`virtualedge-tls`)
for read-only monitoring, exposed on guest TCP port 8443 when enabled. It
requires a client certificate and rejects unsupported routes and methods.
`./scripts/enable-native-tls.sh` enables Buildroot OpenSSL packages; the
build script cross-compiles the service and repackages the rootfs. Host-side
integration tests validate TLS behavior. The new service is **disabled by
default** and does not ship with keys. See `docs/NATIVE_TLS_015.md` for explicit
development provisioning, port forwarding, security limitations, and WSL QEMU
acceptance steps. Real device-side certificate lifecycle and release security
remain unfinished.

## Version 0.17: TLS credential audit before staging

Development-only mTLS credential preflight validates CA trust, server/client
certificate purpose, localhost SAN, validity dates, private-key match and
file permissions. `scripts/stage-native-tls-dev-certs.sh` now calls the audit
before embedding a server key into a development firmware image. This does
**not** implement hardware-backed keys, certificate renewal, or production
provisioning. See `docs/TLS_CREDENTIAL_AUDIT_017.md`.

## v0.21 — Mandatory revocation policy (development profile)

The native ARM64 mTLS guest now **fails closed** if its separate credential disk lacks the configured signed client CRL. A host-side certificate disk built from an initialized identity CA also refuses a missing CRL. A new integration test runs the native OpenSSL gateway through client enrollment, rotation, rejection of the revoked client and acceptance of the replacement.

Run `python3 tests/test-crl-enforcement.py`. See `docs/CRL_ENFORCEMENT_021.md` for migration steps. Native QEMU acceptance, power-loss behavior, real hardware deployment, trusted boot and production certificate lifecycle remain unverified.


## v0.22 — QEMU certificate revocation acceptance

The new `scripts/test-qemu-crl-lifecycle.py` runs two independent ARM64 QEMU
boots using **disposable** development credential disks: two approved clients
before rotation, then an approved replacement and a rejected revoked client
after the CRL change. It does not alter your persistent device data disk or
existing TLS credentials. Run `python3 tests/test-qemu-crl-lifecycle.py` for
host orchestration checks and, after building the ARM64 image,
`python3 scripts/test-qemu-crl-lifecycle.py --timeout 180` for a real guest
acceptance test. See `docs/QEMU_CRL_LIFECYCLE_022.md`. The actual QEMU
two-boot lifecycle has not been verified in the release development environment.

## v0.23 — QEMU A/B image integrity before boot and confirmation

A/B state format 2 records SHA-256 of each populated rootfs slot. Stage, boot,
confirmation and `audit` verify image bytes against the recorded digest; a
corrupt trial candidate falls back to the confirmed image, while a corrupt
confirmed image stops boot selection. Existing v1 A/B state requires explicit
`enroll` to establish its initial host-side digest baseline. Run
`python3 tests/test-ab-integrity.py` and read
[`docs/AB_INTEGRITY_023.md`](AB_INTEGRITY_023.md). This is corruption
detection on the QEMU host, **not secure boot or on-device OTA**.

## v0.24 — Verified immutable snapshot for A/B staging

Fixes a time-of-check/time-of-use race in the QEMU host-side signed update
stager: both Ed25519/SHA-256 verification and inactive-slot installation now
consume a single private, bounded snapshot of the release bundle, rather than
reopening an attacker-replaceable source pathname. Adds regression tests for
post-verification bundle swaps, malformed/symlinked bundles, and interrupted
metadata writes. `python3 tests/test-ab-snapshot.py` and
[`docs/AB_ATOMIC_STAGING_024.md`](AB_ATOMIC_STAGING_024.md).

**This is NOT secure boot, on-device OTA installation or power-failure
qualification.** Actual ARM64 QEMU validation remains necessary.

## v0.25 — Controlled A/B crash recovery (QEMU-host only)

Adds `virtualedge_ab.py --state-dir out/ab recover`, which validates recorded
slot hashes and removes safe orphan temporary files without altering slot
metadata or promoting untested candidates. Includes four independent
process-crash checkpoints covering snapshot, inactive image, rename, and
metadata-commit boundaries, with signed-image retry checks. Run
`python3 tests/test-ab-crash-recovery.py` or see
`docs/AB_CRASH_RECOVERY_025.md` for limitations and installation guidance.
This is **not** guest-side OTA or physical power-loss qualification.

## v0.26 — Native signed-image verification (non-installing)

The OpenSSL-enabled ARM64 build now includes `virtualedge-update-verify`, a small
C utility which independently checks the Ed25519 manifest signature, image
SHA-256, board identifier, version floor, and file bounds. It **never writes
to any disk**, and it is not yet an OTA agent. Nine dedicated host tests
exercise valid/invalid signatures, file integrity, board/version mismatch and
unsafe inputs. Run `python3 tests/test-guest-update-verify.py` or see
`docs/GUEST_UPDATE_PREFLIGHT_026.md` for guest usage and trust limitations.

## v0.27 — Verified guest-side file staging (not disk installation)

The OpenSSL-enabled ARM64 image now contains `virtualedge-update-stage`.
It privately snapshots three release files, verifies that exact snapshot using
`virtualedge-update-verify`, and publishes the candidate directory atomically.
It does **not** write raw flash, switch A/B slots, or trigger reboot.
See `docs/GUEST_FILE_STAGING_027.md` and run
`python3 tests/test-guest-update-stage.py` for host acceptance.

## v0.28 — Native verified installation into an inactive regular-file image

`virtualedge-update-install-file` prepares a disposable inactive-slot **regular
file** from a freshly verified private snapshot of the guest-staged candidate.
It fails closed on invalid signatures, tampering, rollback and pre-existing
outputs. It does not write block devices or change the boot slot. Host tests:
`python3 tests/test-guest-update-install-file.py`. See
[`docs/GUEST_INSTALL_FILE_028.md`](GUEST_INSTALL_FILE_028.md).
ARM64/QEMU verification and power-loss acceptance remain outstanding.


## Consolidated v0.32 integration fixes

See `docs/FINAL_INTEGRATION_v032.md` for the disk-order, signing, dashboard and OTA acceptance fixes.
