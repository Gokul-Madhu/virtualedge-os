#!/usr/bin/env bash
set -euo pipefail
PROJECT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT"
gcc -std=c11 -O2 -Wall -Wextra -Werror tests/test-diagnostics.c -o /tmp/virtualedge-diagnostics-test
/tmp/virtualedge-diagnostics-test
./tests/test-telemetry.sh
python3 ./tests/test-phase4.py

python3 ./tests/test-hardening.py
python3 ./tests/test-supervisor.py
gcc -std=c11 -O2 -Wall -Wextra -Werror tests/test-events-capacity.c -o /tmp/ve-events-capacity-test
/tmp/ve-events-capacity-test
python3 ./tests/test-thermal-sysfs.py

python3 ./tests/test-device-config.py

echo "=== Signed offline release checks ==="
python3 ./tests/test-signed-release.py

echo "=== QEMU persistence source/launcher checks ==="
python3 ./tests/test-persistence.py

echo "=== QEMU A/B boot-slot state tests ==="
python3 ./tests/test-ab-slots.py

echo "=== A/B guest-evidence and acceptance checks ==="
python3 ./tests/test-ab-acceptance.py

echo '=== v0.12 readiness, metrics and recovery checks ==='
python3 ./tests/test-readiness.py

echo "=== v0.13 optional HTTP authentication checks ==="
python3 ./tests/test-auth.py

echo '=== v0.14 development mTLS gateway checks ==='
python3 ./tests/test-tls-gateway.py

echo '=== v0.15 native guest OpenSSL mTLS checks ==='
python3 ./tests/test-native-tls.py

echo '=== v0.17 TLS development certificate audit ==='
python3 ./tests/test-tls-audit.py

echo '=== v0.18 firmware credential isolation and TLS disk checks ==='
python3 ./tests/test-tls-disk.py

echo '=== v0.19 per-device identity and CRL enforcement ==='
python3 ./tests/test-device-identity.py

echo '=== v0.20 credential rotation and CRL freshness ==='
python3 ./tests/test-identity-rotation.py

echo '=== v0.21 mandatory guest CRL and full client rotation enforcement ==='
python3 ./tests/test-crl-enforcement.py

echo '=== v0.22 QEMU CRL lifecycle orchestration tests ==='
python3 ./tests/test-qemu-crl-lifecycle.py

echo '=== v0.23 A/B image integrity and corruption fallback ==='
python3 ./tests/test-ab-integrity.py

echo '=== v0.24 snapshotted signed bundle staging and interruption tests ==='
python3 ./tests/test-ab-snapshot.py

echo '=== v0.25 A/B process-crash and orphan recovery ==='
python3 ./tests/test-ab-crash-recovery.py

echo "=== v0.26 Native signed-image verification ==="
python3 ./tests/test-guest-update-verify.py
echo '=== v0.27 Native verified file staging (never writes block devices) ==='
python3 ./tests/test-guest-update-stage.py

echo '=== v0.28 Guest-side signed candidate installation to REGULAR FILE ONLY ==='
python3 ./tests/test-guest-update-install-file.py

echo "=== v0.29 Exported guest candidate to QEMU A/B handoff ==="
python3 ./tests/test-ab-guest-handoff.py

echo '=== v0.30 Disposable QEMU OTA acceptance orchestration (host stubs) ==='
python3 ./tests/test-qemu-ota.py

echo "=== v0.31 OTA non-mutation SHA-256 and report evidence ==="
python3 ./tests/test-ota-evidence.py

echo "=== v0.32 OTA acceptance boot trace and report isolation ==="
python3 ./tests/test-ota-trace.py


echo "=== v0.33 QEMU OTA preflight (offline and non-mutating) ==="
python3 ./tests/test-ota-preflight.py

echo "=== v0.34 preflight-gated real QEMU acceptance entry-point safety ==="
python3 ./tests/test-ota-accept-entry.py

echo "=== v0.36 real confirmed-baseline smoke gate (host contract tests) ==="
python3 ./tests/test-ota-baseline-smoke.py
