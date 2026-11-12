# VirtualEdge OS hardware, boot trust and power-loss roadmap

**Status: target-specific engineering plan. None of these physical tests have
been executed or certified by the v0.34 software release.**

## 1. Choose a physical board before writing disk-update code

A concrete candidate is Raspberry Pi 4 (64-bit Linux) with a known SD/eMMC
controller. Raspberry Pi Zero 2 W is another port target, but requires its own
image and performance validation. **Do not use the QEMU `virt` kernel or QEMU
rootfs as a flashable Pi image.** Buildroot needs a Pi-specific kernel, device
tree, firmware/boot files, kernel command line, serial console, peripherals and
boot-image assembly. Validate the exact board revision and boot firmware.

A minimal gated bring-up sequence:

1. Boot a board-specific Buildroot image over serial; capture console logs.
2. Confirm stable boot, memory, network, watchdog and thermal interfaces.
3. Read known I²C/SPI sensor IDs and acquire actual readings with timestamps,
   limits and explicit error states. Simulated sensor signals must remain labeled.
4. Document the physical storage layout, partition IDs, offsets, device nodes,
   mount rules and power-off behavior on the chosen board.
5. Test data partition persistence across 100 controlled reboots before OTA.

## 2. A/B storage contract and bootloader

Target layout (illustrative only, NOT an executable flash map):

- `boot/recovery`: bootloader and an independently verified recovery mechanism.
- `rootfs_A` and `rootfs_B`: immutable/selectable system partitions.
- `data`: configuration, logs, device-specific identity, never overwritten by OTA.
- `boot_state`: redundant, checksummed/atomic state with slot, retries,
  confirmed generation and a rollback floor.

The update agent must verify the **exact same bytes** that it writes, refuse the
active mounted partition, flush and reread inactive partition, and only then
atomically request a trial boot. The bootloader must decrement retries and
fallback if a candidate doesn't confirm after full service readiness checks.
Protect rollback counters and verification keys against an attacker who can
modify the root filesystem; otherwise this isn't a trusted OTA chain.

Hardware-specific bootloader selection must be proven first. Raspberry Pi
firmware, U-Boot, UEFI and industrial SoC boot ROMs have different trust roots;
there is no one generic secure-boot implementation. Before claiming secure
boot, verify signed first-stage firmware, bootloader, kernel/DTB, rootfs
integrity (e.g., authenticated dm-verity where appropriate), key enrollment,
key revocation and recovery from a corrupt active image.

## 3. Power-loss test matrix (requires physical target and power controller)

Use an instrumented programmable power switch, serial logger and a disposable
board/media. Never perform destructive tests on a user's only device or data.
For **every** stage, abruptly remove power and restore it; repeat across media,
voltage/temperature ranges and timings:

| Cut point | Expected property |
|---|---|
| Idle, no update | Previously confirmed OS boots; data preserved |
| While downloading | Incomplete download discarded; confirmed OS boots |
| While validating signature/hash | Invalid or partial candidate rejected |
| While writing inactive root | Confirmed OS boots; incomplete slot never selected |
| After write before sync | Incomplete slot rejected after restart |
| After sync before metadata commit | Previous confirmed OS boots |
| After trial boot selection | Retries bounded; fallback eventually possible |
| During first trial boot | Retry consumed; confirmed slot still available |
| During confirmation commit | Either old confirmed or fully new confirmed state; never ambiguous |
| During rollback | Recovery slot boots; persistent config unaffected |

For each run collect: serial console, bootloader state, kernel command line,
readiness/self-test, active slot, both image digests, config and log checks,
power interruption timestamp, reset reason and outcome. Define quantitative
acceptance targets and run hundreds of iterations after basic correctness is
established. Test under realistic brownout and storage wear; an emulated QEMU
process kill is **not** equivalent to true power-loss testing.

## 4. Production security gates

- Per-device identities and keys provisioned to a hardware trust anchor when
  the chosen board supports one; no pre-shared private keys inside public images.
- Mutual TLS with correct server identity, certificate and CRL updates,
  expiration handling and secure real-time clock/time synchronization.
- Update signing key rotation, revocation and offline recovery process.
- Least privilege, read-only roots, secure file permissions, audit trail,
  reproducible release manifests, SBOM and vulnerability scan.
- Independent review and documented release criteria. No industrial security,
  safety or electromagnetic compliance certification is implied here.
