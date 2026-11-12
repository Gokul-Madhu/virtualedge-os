# v0.11 — QEMU candidate boot acceptance

## Included
- Expanded `scripts/test-qemu.py` to use a selected rootfs and optional persistent data volume, both copied to temporary disk files.
- Host checks that the guest's `/proc/cmdline` contains exactly the expected slot and version.
- New `scripts/check-ab-candidate.py` invokes the existing A/B state machine, boots the selected pending rootfs, validates `virtualedge-selftest`, and only invokes host confirmation with `--confirm-on-pass`.
- `tests/test-ab-acceptance.py` adds negative tests for absent/mismatched/ambiguous slot evidence, failed guest tests, and confirmation gating.

## Verification in the authoring environment
- Existing C, API, signature, supervisor, persistence tests passed up to the A/B slot stage in the combined runner.
- `tests/test-ab-slots.py`: passed separately.
- `tests/test-ab-acceptance.py`: passed separately, including failure and recovery paths.
- `python3 -m py_compile` and `bash -n` passed.
- One combined host-test invocation exceeded the container time limit, so a single uninterrupted full-suite pass is not claimed.
- QEMU v0.11 candidate image boot, actual persistent image mounting, on-device OTA, power-loss safety and hardware acceptance are **not** verified.

## Important limitations
The host supplies kernel boot arguments and still retains a separate, unsigned Buildroot kernel. QEMU acceptance is only a functional smoke test. Candidate promotion is a host-side decision; `--confirm-on-pass` is optional and should only be used with a test image intended for deployment. This is not a secure, production-ready update mechanism.
