# VirtualEdge OS v0.25 — QEMU-host A/B crash recovery

## Scope

This release adds explicit recovery of orphaned temporary staging files and a **test-only** crash-injection harness. It does **not** install updates from inside the ARM64 guest, perform block-device OTA, establish power-loss-safe flash writes, or provide verified boot.

The existing signed update manager writes to inactive QEMU root filesystem *files* under `out/ab`. It uses `fsync` and atomic `os.replace` on the host filesystem. This is a useful simulation of update interruption, not a substitute for actual power-loss tests with physical storage.

## Added command: recover

```bash
cd ~/dev/virtualedge-os
python3 tools/virtualedge_ab.py --state-dir out/ab audit
python3 tools/virtualedge_ab.py --state-dir out/ab recover
```

`recover` requires that the confirmed image's SHA-256 matches the recorded hash. If an update is pending, it also checks the candidate hash. Only after successful validation does it delete recognized temporary files left by an interrupted operation (`.ve-bundle-*`, `.ve-stage-*`, `.ve-image-*`, `.ve-state-*`). It refuses symlinks and unexpected non-regular temporary entries. It never changes `state.json`, never modifies either slot image, and never promotes a candidate. If a slot is corrupted, it stops and asks for human intervention.

**Do not invoke recovery while another program outside this manager is directly modifying images or metadata.** The manager takes its own exclusive `.lock`, but cannot coordinate with external tools that ignore this lock.

## Crash tests

```bash
python3 tests/test-ab-crash-recovery.py
```

The host test builds tiny disposable images and an Ed25519-signed update. It launches a staging subprocess that deliberately exits at each of four durable boundaries:

1. `snapshot_fsynced` — verified-bundle snapshot written, before verification.
2. `slot_temp_fsynced` — inactive-slot temporary file synced, before the atomic rename.
3. `slot_replaced` — inactive slot image renamed, before the metadata commit.
4. `metadata_committed` — slot metadata atomically committed, before temporary-snapshot cleanup.

After each crash, a new manager process calls `recover` and `audit`, verifies the original confirmed slot still matches its digest, and either retries staging or preserves the committed candidate. Tests also check that symlinked cleanup entries and corrupted confirmed root images are rejected.

To run a single checkpoint test:

```bash
VE_ONLY_POINT=slot_replaced python3 tests/test-ab-crash-recovery.py
```

The crash injector **only** triggers with both a specific internal test acknowledgement and a named checkpoint. It is not a public device feature; never set the `VE_TEST_*` fault-injection environment variables in production.

## Recommended acceptance sequence

```bash
./scripts/test-host.sh
python3 tests/test-ab-crash-recovery.py
python3 tools/virtualedge_ab.py --state-dir out/ab audit
./scripts/build-and-test.sh --qemu
```

The host tests have passed in the release environment, but full ARM64/QEMU acceptance has not been performed here. On real hardware, update durability depends on filesystem and storage cache behavior, partition switching, kernel/bootloader integration and explicit power-loss testing.
