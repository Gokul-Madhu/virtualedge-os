#!/usr/bin/env python3
"""Signed offline release tests; no flashing or update installation."""
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "virtualedge_release.py"

def run(*args, ok=True):
    result = subprocess.run([sys.executable, str(TOOL), *map(str, args)], capture_output=True, text=True)
    if (result.returncode == 0) != ok:
        raise AssertionError(f"unexpected exit={result.returncode}: {result.stdout}\n{result.stderr}")

with tempfile.TemporaryDirectory() as temp:
    base = Path(temp)
    key, pub = base / "release.key", base / "release.pub"
    image = base / "rootfs.img"
    image.write_bytes(b"VIRTUALEDGE TEST IMAGE\x00" * 512)
    bundle = base / "release.tar"
    run("keygen", "--private-key", key, "--public-key", pub)
    assert key.stat().st_mode & 0o077 == 0, "private signing key permissions too broad"
    run("pack", "--image", image, "--private-key", key, "--board", "qemu-aarch64",
        "--version", "0.8.0", "--output", bundle)
    run("verify", "--bundle", bundle, "--public-key", pub, "--board", "qemu-aarch64",
        "--min-version", "0.7.0")
    run("verify", "--bundle", bundle, "--public-key", pub, "--board", "rpi4", ok=False)
    run("verify", "--bundle", bundle, "--public-key", pub, "--board", "qemu-aarch64",
        "--min-version", "0.9.0", ok=False)
    run("verify", "--bundle", bundle, "--public-key", pub, "--board", "qemu-aarch64",
        "--max-image-bytes", "8", ok=False)
    # A tampered image with an unchanged signed manifest must be rejected.
    modified = base / "tampered.tar"
    with tarfile.open(bundle) as source, tarfile.open(modified, "w") as target:
        for member in source:
            raw = source.extractfile(member).read()
            if member.name == "image.bin":
                raw = b"X" + raw[1:]
            from io import BytesIO
            member.size = len(raw)
            target.addfile(member, BytesIO(raw))
    run("verify", "--bundle", modified, "--public-key", pub, "--board", "qemu-aarch64", ok=False)
    # Tampered signed metadata must fail Ed25519 verification.
    changed = base / "changed.tar"
    with tarfile.open(bundle) as source, tarfile.open(changed, "w") as target:
        for member in source:
            raw = source.extractfile(member).read()
            if member.name == "manifest.json":
                raw = raw.replace(b"0.8.0", b"0.9.0")
            from io import BytesIO
            member.size = len(raw)
            target.addfile(member, BytesIO(raw))
    run("verify", "--bundle", changed, "--public-key", pub, "--board", "qemu-aarch64", ok=False)
    print("PASS: signed release verification, board lock, rollback guard and tamper rejection")
