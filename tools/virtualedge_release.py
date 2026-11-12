#!/usr/bin/env python3
"""VirtualEdge offline signed release bundles (NOT an OTA installer).

Bundle format: tar archive containing manifest.json, manifest.sig and image.bin.
Ed25519 signature covers the exact manifest bytes; manifest binds SHA256 image,
board, and monotonic release version. Never package the private key.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import tempfile

BOARD = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
VERSION = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
MEMBERS = ("manifest.json", "manifest.sig", "image.bin")
MAX_MANIFEST = 4096
MAX_SIGNATURE = 128


def fail(msg):
    raise ValueError(msg)


def semver(value):
    m = VERSION.fullmatch(value)
    if not m:
        fail("version must be numeric MAJOR.MINOR.PATCH")
    return tuple(map(int, m.groups()))


def command(argv):
    p = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if p.returncode:
        raise ValueError("OpenSSL signing/verification failed: " + p.stderr.decode(errors="replace")[:250])
    return p.stdout


def digest(path):
    h = hashlib.sha256()
    size = 0
    with open(path, "rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            size += len(block)
            h.update(block)
    return h.hexdigest(), size


def keys(args):
    private = Path(args.private_key)
    public = Path(args.public_key)
    if private.exists() or public.exists():
        fail("key file exists; refusing to overwrite")
    private.parent.mkdir(parents=True, exist_ok=True)
    public.parent.mkdir(parents=True, exist_ok=True)
    # Use restrictive permissions. Keys are created by OpenSSL, not copied into a bundle.
    prior = os.umask(0o077)
    try:
        command(["openssl", "genpkey", "-algorithm", "ED25519", "-out", str(private)])
        command(["openssl", "pkey", "-in", str(private), "-pubout", "-out", str(public)])
    finally:
        os.umask(prior)
    print("Created release signing keypair; protect private key outside project/repository")


def pack(args):
    if not BOARD.fullmatch(args.board):
        fail("invalid board identifier")
    semver(args.version)
    image = Path(args.image)
    if not image.is_file() or image.stat().st_size == 0:
        fail("image missing or empty")
    sha, size = digest(image)
    manifest = {
        "board": args.board,
        "format": "virtualedge-image-v1",
        "image": "image.bin",
        "sha256": sha,
        "size": size,
        "version": args.version,
    }
    manifest_bytes = (json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n").encode()
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        (base / "manifest.json").write_bytes(manifest_bytes)
        command(["openssl", "pkeyutl", "-sign", "-rawin", "-inkey", str(args.private_key),
                 "-in", str(base / "manifest.json"), "-out", str(base / "manifest.sig")])
        out = Path(args.output)
        if out.exists():
            fail("output exists; refusing to overwrite")
        out.parent.mkdir(parents=True, exist_ok=True)
        with tarfile.open(out, "w", dereference=True) as tar:
            for name, path in (("manifest.json", base / "manifest.json"),
                               ("manifest.sig", base / "manifest.sig"),
                               ("image.bin", image)):
                tar.add(path, arcname=name, recursive=False)
    print(f"Created signed release {out} ({args.board} {args.version}, {size} bytes)")


def verify(args):
    semver(args.min_version)
    if not BOARD.fullmatch(args.board):
        fail("invalid board identifier")
    archive = Path(args.bundle)
    if not archive.is_file():
        fail("release archive not found")
    # Bounded archive inspection, reject duplicate/unknown entries, links, and traversal.
    with tarfile.open(archive, "r") as tar:
        entries = tar.getmembers()
        if len(entries) != 3 or set(e.name for e in entries) != set(MEMBERS):
            fail("bundle must contain exactly three unique files")
        if any(not e.isfile() or e.name.startswith("/") or ".." in e.name for e in entries):
            fail("unsafe bundle entries")
        m = tar.getmember("manifest.json")
        s = tar.getmember("manifest.sig")
        image = tar.getmember("image.bin")
        if not 1 <= m.size <= MAX_MANIFEST or not 1 <= s.size <= MAX_SIGNATURE:
            fail("invalid manifest/signature size")
        if image.size <= 0 or image.size > args.max_image_bytes:
            fail("image exceeds permitted size or is empty")
        manifest_bytes = tar.extractfile(m).read()
        signature = tar.extractfile(s).read()
        try:
            manifest = json.loads(manifest_bytes)
        except (UnicodeDecodeError, json.JSONDecodeError):
            fail("malformed manifest")
        if set(manifest) != {"board", "format", "image", "sha256", "size", "version"}:
            fail("unrecognized manifest fields")
        if manifest["format"] != "virtualedge-image-v1" or manifest["image"] != "image.bin":
            fail("unsupported release format")
        if manifest["board"] != args.board:
            fail("board identity mismatch")
        if not isinstance(manifest["version"], str) or semver(manifest["version"]) < semver(args.min_version):
            fail("rollback/version mismatch")
        if type(manifest["size"]) is not int or manifest["size"] != image.size:
            fail("image size mismatch")
        if not isinstance(manifest["sha256"], str) or not re.fullmatch("[0-9a-f]{64}", manifest["sha256"]):
            fail("invalid digest format")
        canonical = (json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n").encode()
        if manifest_bytes != canonical:
            fail("noncanonical manifest")
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "manifest.json").write_bytes(manifest_bytes)
            (base / "manifest.sig").write_bytes(signature)
            command(["openssl", "pkeyutl", "-verify", "-rawin", "-pubin", "-inkey", str(args.public_key),
                     "-in", str(base / "manifest.json"), "-sigfile", str(base / "manifest.sig")])
        h = hashlib.sha256()
        count = 0
        file = tar.extractfile(image)
        for block in iter(lambda: file.read(1024 * 1024), b""):
            count += len(block)
            h.update(block)
        if count != image.size or h.hexdigest() != manifest["sha256"]:
            fail("image SHA-256 mismatch")
    print(f"PASS: Signed release verified: {manifest['board']} {manifest['version']} (SHA256, Ed25519)")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    key = sub.add_parser("keygen", help="create offline Ed25519 release keypair")
    key.add_argument("--private-key", required=True)
    key.add_argument("--public-key", required=True)
    key.set_defaults(func=keys)
    create = sub.add_parser("pack", help="sign an image with board/version metadata")
    for option in ("image", "private-key", "board", "version", "output"):
        create.add_argument("--" + option, required=True)
    create.set_defaults(func=pack)
    check = sub.add_parser("verify", help="verify signed bundle before any installation")
    for option in ("bundle", "public-key", "board"):
        check.add_argument("--" + option, required=True)
    check.add_argument("--min-version", default="0.0.0")
    check.add_argument("--max-image-bytes", type=int, default=1024*1024*1024)
    check.set_defaults(func=verify)
    args = parser.parse_args()
    try:
        args.func(args)
    except (OSError, ValueError, tarfile.TarError) as error:
        print("ERROR:", error, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
