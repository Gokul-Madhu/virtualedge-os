#!/usr/bin/env python3
"""QEMU-only A/B rootfs manager. Not a production device bootloader or OTA client.

State changes are atomic and synchronized. Never run two instances concurrently.
On each `boot`, a pending candidate consumes one attempt; after exhaustion the
next boot falls back to the confirmed slot. `confirm` is an EXPLICIT host action.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile

SLOTS = ("A", "B")
VERS = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
BOARD = "qemu-aarch64"
MAX_IMAGE_BYTES = 1024 * 1024 * 1024
MAX_BUNDLE_BYTES = MAX_IMAGE_BYTES + 8 * 1024 * 1024
SHA256 = re.compile(r"^[0-9a-f]{64}$")


def version(s):
    m = VERS.fullmatch(s)
    if not m:
        raise ValueError("version must be numeric MAJOR.MINOR.PATCH")
    return tuple(int(x) for x in m.groups())


def regular_file(p):
    return p.is_file() and not p.is_symlink()


def safe_directory(p):
    if p.is_symlink():
        raise ValueError(f"refusing symlink directory: {p}")
    p.mkdir(parents=True, exist_ok=True)
    if not p.is_dir():
        raise ValueError("invalid state directory")


def atomic_json(p, value):
    fd, tmp = tempfile.mkstemp(prefix=".ve-state-", dir=p.parent)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(value, f, sort_keys=True, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, p)
        fsync_dir(p.parent)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def fsync_dir(d):
    fd = os.open(d, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def validate(s):
    base = {"format", "confirmed", "pending", "attempts_left", "versions"}
    if not isinstance(s, dict) or s.get("format") not in (1, 2):
        raise ValueError("invalid state format")
    expected = base | ({"hashes"} if s["format"] == 2 else set())
    if set(s) != expected:
        raise ValueError("invalid state format fields")
    if s["confirmed"] not in SLOTS:
        raise ValueError("invalid confirmed slot")
    if s["pending"] is not None and (s["pending"] not in SLOTS or s["pending"] == s["confirmed"]):
        raise ValueError("invalid pending slot")
    if type(s["attempts_left"]) is not int or not 0 <= s["attempts_left"] <= 3:
        raise ValueError("invalid attempt counter")
    if not isinstance(s["versions"], dict) or set(s["versions"]) != set(SLOTS):
        raise ValueError("invalid slot versions")
    for v in s["versions"].values():
        if v is not None:
            version(v)
    if s["versions"][s["confirmed"]] is None:
        raise ValueError("confirmed slot missing version")
    if s["pending"] is None and s["attempts_left"] != 0:
        raise ValueError("attempt counter without pending slot")
    if s["pending"] is not None and s["versions"][s["pending"]] is None:
        raise ValueError("pending slot missing version")
    if s["format"] == 2:
        if not isinstance(s["hashes"], dict) or set(s["hashes"]) != set(SLOTS):
            raise ValueError("invalid slot hashes")
        for slot in SLOTS:
            digest = s["hashes"][slot]
            if digest is not None and (not isinstance(digest, str) or not SHA256.fullmatch(digest)):
                raise ValueError("invalid slot digest")
            if s["versions"][slot] is not None and digest is None:
                raise ValueError("versioned slot has no digest")
            if s["versions"][slot] is None and digest is not None:
                raise ValueError("empty slot has digest")
    return s


def disk_sha256(directory, slot):
    p = image_path(directory, slot)
    if not regular_file(p) or not 0 < p.stat().st_size <= MAX_IMAGE_BYTES:
        raise ValueError(f"slot {slot} image missing, symlinked, empty or oversized")
    h = hashlib.sha256()
    with p.open("rb") as stream:
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def check_slot(directory, s, slot):
    # v1 was shipped without hashes. Never silently turn a hashless state into
    # a trusted integrity record; see explicit 'enroll' migration command.
    if s["format"] == 1:
        if not regular_file(image_path(directory, slot)):
            raise ValueError(f"slot {slot} image missing")
        return
    actual = disk_sha256(directory, slot)
    if actual != s["hashes"][slot]:
        raise ValueError(f"slot {slot} SHA-256 mismatch; refusing unsafe boot/confirmation")


def enroll(args, directory):
    s = load(directory)
    if s["format"] != 1:
        raise ValueError("state already has recorded image hashes")
    # Do not trust the current files automatically; the operator explicitly
    # accepts these bytes as the integrity baseline for this QEMU-only demo.
    s["hashes"] = {slot: disk_sha256(directory, slot) if s["versions"][slot] is not None else None
                   for slot in SLOTS}
    s["format"] = 2
    atomic_json(directory / "state.json", validate(s))
    print("Enrolled existing QEMU slot image hashes; host metadata is not a cryptographic trust anchor")


def audit(args, directory):
    s = load(directory)
    if s["format"] == 1:
        raise ValueError("legacy v1 state lacks hashes; review images, then run enroll")
    for slot in SLOTS:
        if s["versions"][slot] is not None:
            check_slot(directory, s, slot)
            print(f"PASS: slot {slot} image matches recorded SHA-256")
    print("PASS: all recorded QEMU images match their host-side digests")


def state_file(directory):
    p = directory / "state.json"
    if not regular_file(p):
        raise ValueError("state file missing or unsafe; run init first")
    return p


def load(directory):
    p = state_file(directory)
    if p.stat().st_size > 4096:
        raise ValueError("state too large")
    return validate(json.loads(p.read_text()))


def image_path(directory, slot):
    if slot not in SLOTS:
        raise ValueError("unknown slot")
    return directory / f"rootfs-{slot}.ext4"


def image_copy(source, target, max_bytes=MAX_IMAGE_BYTES):
    if not regular_file(source) or not 0 < source.stat().st_size <= max_bytes:
        raise ValueError("source image missing/unsafe or too large")
    if target.is_symlink():
        raise ValueError("refusing symlink target")
    fd, tmp = tempfile.mkstemp(prefix=".ve-image-", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as dest, source.open("rb") as src:
            shutil.copyfileobj(src, dest, 1024 * 1024)
            dest.flush()
            os.fsync(dest.fileno())
        os.replace(tmp, target)
        fsync_dir(target.parent)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def init(args, directory):
    state_path = directory / "state.json"
    if state_path.exists() or state_path.is_symlink() or any(image_path(directory, s).exists() for s in SLOTS):
        raise ValueError("existing slot/state files; refusing initialization")
    version(args.version)
    image_copy(Path(args.image), image_path(directory, "A"))
    atomic_json(state_path, {"format": 2, "confirmed": "A", "pending": None,
                             "attempts_left": 0, "versions": {"A": args.version, "B": None},
                             "hashes": {"A": disk_sha256(directory, "A"), "B": None}})
    print("Initialized confirmed slot A; slot B is empty")


def test_crash_point(name):
    """Opt-in destructive crash injection for disposable TEST state only.

    Requires two independent environment opt-ins, and no production capability.
    _exit intentionally skips Python cleanup to simulate abrupt power loss.
    """
    if (os.environ.get("VE_TEST_FAULTS") == "I_UNDERSTAND_THIS_KILLS_THE_PROCESS"
            and os.environ.get("VE_TEST_CRASH_POINT") == name):
        os._exit(77)


def recover(args, directory):
    """Audit bootable state and discard orphan temporary files after a crash.

    Never changes slot metadata, images, or promotes a candidate. The manager's
    exclusive lock in main() makes this safe relative to other manager commands.
    """
    s = load(directory)
    check_slot(directory, s, s["confirmed"])
    if s["pending"] is not None:
        check_slot(directory, s, s["pending"])
    stale_prefixes = (".ve-bundle-", ".ve-stage-", ".ve-image-", ".ve-state-")
    removed = 0
    for entry in directory.iterdir():
        if any(entry.name.startswith(prefix) for prefix in stale_prefixes):
            if entry.is_symlink() or not entry.is_file():
                raise ValueError(f"unsafe temporary entry; manual review required: {entry}")
            entry.unlink()
            removed += 1
    if removed:
        fsync_dir(directory)
    print(f"PASS: confirmed slot {s['confirmed']} verified; "
          f"{('candidate '+s['pending']+' verified; ') if s['pending'] else ''}"
          f"{removed} orphan temporary files removed; metadata unchanged")


def stage(args, directory):
    s = load(directory)
    if s["pending"] is not None:
        raise ValueError("pending update exists; confirm or abort before staging another")
    check_slot(directory, s, s["confirmed"])
    source = Path(args.bundle)
    if not regular_file(source) or not 0 < source.stat().st_size <= MAX_BUNDLE_BYTES:
        raise ValueError("signed bundle missing, unsafe or oversized")

    # Verify and consume the exact same immutable-by-path private snapshot.
    # Previously 'verify' read the original path and the installer reopened it,
    # creating a TOCTOU window where an unsigned replacement could be staged.
    # The snapshot is restricted to the manager's state directory (mode 0600).
    fd, snapshot_name = tempfile.mkstemp(prefix=".ve-bundle-", dir=directory)
    snapshot = Path(snapshot_name)
    try:
        with os.fdopen(fd, "wb") as out, source.open("rb") as src:
            length = 0
            while True:
                block = src.read(1024 * 1024)
                if not block:
                    break
                length += len(block)
                if length > MAX_BUNDLE_BYTES:
                    raise ValueError("signed bundle changed size or exceeds limit")
                out.write(block)
            out.flush()
            os.fsync(out.fileno())
        test_crash_point("snapshot_fsynced")

        verify = Path(__file__).with_name("virtualedge_release.py")
        cmd = [sys.executable, str(verify), "verify", "--bundle", str(snapshot),
               "--public-key", args.public_key, "--board", BOARD,
               "--min-version", s["versions"][s["confirmed"]],
               "--max-image-bytes", str(MAX_IMAGE_BYTES)]
        subprocess.run(cmd, check=True)

        with tarfile.open(snapshot, "r") as bundle:
            m = json.loads(bundle.extractfile("manifest.json").read())
            if version(m["version"]) <= version(s["versions"][s["confirmed"]]):
                raise ValueError("update must be strictly newer than confirmed release")
            pending = "B" if s["confirmed"] == "A" else "A"
            dest = image_path(directory, pending)
            if dest.is_symlink():
                raise ValueError("refusing symlink target")
            fd, tmp = tempfile.mkstemp(prefix=".ve-stage-", dir=directory)
            try:
                h = hashlib.sha256()
                length = 0
                with os.fdopen(fd, "wb") as out, bundle.extractfile("image.bin") as src:
                    while True:
                        data = src.read(1024 * 1024)
                        if not data:
                            break
                        length += len(data)
                        if length > MAX_IMAGE_BYTES:
                            raise ValueError("image too large")
                        h.update(data)
                        out.write(data)
                    out.flush()
                    os.fsync(out.fileno())
                test_crash_point("slot_temp_fsynced")
                if length != m["size"] or h.hexdigest() != m["sha256"]:
                    raise ValueError("image changed during staging")
                os.replace(tmp, dest)
                fsync_dir(directory)
                test_crash_point("slot_replaced")
            finally:
                if os.path.exists(tmp):
                    os.unlink(tmp)
        s["pending"] = pending
        s["attempts_left"] = 2
        s["versions"][pending] = m["version"]
        if s["format"] == 2:
            s["hashes"][pending] = m["sha256"]
        atomic_json(directory / "state.json", s)
        test_crash_point("metadata_committed")
        print(f"Staged verified {m['version']} into inactive slot {pending}; two boot attempts")
    finally:
        snapshot.unlink(missing_ok=True)

def boot(args, directory):
    s = load(directory)
    # Always check the confirmed recovery slot before selecting anything.
    # Avoid consuming a candidate attempt when the recovery image is corrupt.
    check_slot(directory, s, s["confirmed"])
    if s["pending"] is not None and s["attempts_left"] == 0:
        print(f"Candidate slot {s['pending']} unconfirmed; returning to {s['confirmed']}", file=sys.stderr)
        s["pending"] = None
        atomic_json(directory / "state.json", s)
    elif s["pending"] is not None:
        candidate = s["pending"]
        try:
            check_slot(directory, s, candidate)
        except ValueError as exc:
            print(f"Rejected corrupt candidate {candidate}: {exc}; using confirmed slot", file=sys.stderr)
            s["pending"] = None
            s["attempts_left"] = 0
            atomic_json(directory / "state.json", s)
        else:
            s["attempts_left"] -= 1
            atomic_json(directory / "state.json", s)
            print(f"{candidate} {s['versions'][candidate]} {image_path(directory, candidate)}")
            return
    slot = s["confirmed"]
    print(f"{slot} {s['versions'][slot]} {image_path(directory, slot)}")


def confirm(args, directory):
    s = load(directory)
    if s["pending"] is None or s["pending"] != args.slot:
        raise ValueError("slot is not pending; cannot confirm")
    if not args.guest_selftest_passed:
        raise ValueError("explicit --guest-selftest-passed flag required")
    check_slot(directory, s, s["confirmed"])
    check_slot(directory, s, s["pending"])
    s["confirmed"] = s["pending"]
    s["pending"] = None
    s["attempts_left"] = 0
    atomic_json(directory / "state.json", s)
    print(f"Confirmed slot {s['confirmed']} after externally verified guest self-test")


def abort(args, directory):
    s = load(directory)
    if s["pending"] is None:
        raise ValueError("no pending update")
    s["pending"] = None
    s["attempts_left"] = 0
    atomic_json(directory / "state.json", s)
    print("Aborted pending candidate; confirmed slot unchanged")


def status(args, directory):
    print(json.dumps(load(directory), sort_keys=True, indent=2))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--state-dir", required=True, type=Path)
    sub = p.add_subparsers(dest="command", required=True)
    first = sub.add_parser("init")
    first.add_argument("--image", required=True)
    first.add_argument("--version", required=True)
    pending = sub.add_parser("stage")
    pending.add_argument("--bundle", required=True)
    pending.add_argument("--public-key", required=True)
    sub.add_parser("boot")
    done = sub.add_parser("confirm")
    done.add_argument("--slot", choices=SLOTS, required=True)
    done.add_argument("--guest-selftest-passed", action="store_true")
    sub.add_parser("abort")
    sub.add_parser("status")
    sub.add_parser("audit")
    sub.add_parser("enroll")
    sub.add_parser("recover")
    args = p.parse_args()
    try:
        safe_directory(args.state_dir)
        lock = args.state_dir / ".lock"
        if lock.is_symlink():
            raise ValueError("symlink lock refused")
        with lock.open("a+") as fd:
            fcntl.flock(fd.fileno(), fcntl.LOCK_EX)
            globals()[args.command](args, args.state_dir)
        return 0
    except (ValueError, OSError, subprocess.CalledProcessError, tarfile.TarError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
