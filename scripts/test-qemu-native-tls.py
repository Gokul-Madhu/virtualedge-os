#!/usr/bin/env python3
"""QEMU native mTLS acceptance: ephemeral guest rootfs; real handshake and API.

Run only after enabling native TLS, staging disposable credentials and rebuilding.
Unlike the ordinary serial test, this verifies the ARM64 HTTPS service end-to-end.
"""
import argparse
import os
from pathlib import Path
import shutil
import signal
import socket
import ssl
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
IMAGES = ROOT / 'out/buildroot/images'
QEMU_HOST = ROOT / 'out/buildroot/host/bin/qemu-system-aarch64'


def tls_request(port, ca, cert=None, key=None, timeout=2.0):
    """Return HTTP bytes after a fully verified TLS handshake, or raise an error."""
    ctx = ssl.create_default_context(cafile=str(ca))
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    if cert is not None:
        ctx.load_cert_chain(str(cert), str(key))
    with socket.create_connection(('127.0.0.1', port), timeout=timeout) as conn:
        with ctx.wrap_socket(conn, server_hostname='localhost') as tls:
            tls.settimeout(timeout)
            tls.sendall(b'GET /ready HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n')
            response = bytearray()
            while len(response) < 65536:
                data = tls.recv(4096)
                if not data:
                    break
                response.extend(data)
            if len(response) >= 65536:
                raise RuntimeError('Unusually large HTTPS readiness response')
            return bytes(response)


def is_ready(response):
    status = response.split(b'\r\n', 1)[0]
    return status == b'HTTP/1.1 200 OK' and b'"status":"ready"' in response


def run(credentials, timeout=180, port=18444, tls_image=None, authorized_clients=None, revoked_clients=None):
    credentials = Path(credentials)
    for name in ('ca.pem', 'client.pem', 'client.key'):
        if not (credentials / name).is_file():
            raise RuntimeError(f'Missing development client credential {credentials / name}')
    kernel, rootfs = IMAGES / 'Image', IMAGES / 'rootfs.ext4'
    secrets = Path(tls_image) if tls_image is not None else ROOT / 'out/persistent/virtualedge-tls-dev.ext4'
    if not secrets.is_file():
        raise RuntimeError('Missing separate TLS disk: generate it with tools/virtualedge_tls_image.py')
    if secrets.is_symlink():
        raise RuntimeError('Refusing symlinked TLS disk')
    if not kernel.is_file() or not rootfs.is_file():
        raise RuntimeError('Missing kernel/rootfs: build the ARM64 image first')
    qemu = QEMU_HOST if QEMU_HOST.exists() else shutil.which('qemu-system-aarch64')
    if not qemu:
        raise RuntimeError('qemu-system-aarch64 is not installed')
    authorized_clients = list(authorized_clients or [(credentials/'client.pem', credentials/'client.key')])
    revoked_clients = list(revoked_clients or [])
    if not authorized_clients:
        raise RuntimeError('At least one approved client is required for a meaningful TLS acceptance check')
    for cert, key in authorized_clients + revoked_clients:
        if not Path(cert).is_file() or not Path(key).is_file():
            raise RuntimeError(f'Client certificate or key missing: {cert}, {key}')
    with socket.socket() as checker:
        try:
            checker.bind(('127.0.0.1', port))
        except OSError as exc:
            raise RuntimeError(f'Host HTTPS port {port} already in use: {exc}') from exc
    with tempfile.TemporaryDirectory(prefix='virtualedge-tls-qemu-') as directory:
        disk = Path(directory) / 'test-rootfs.ext4'
        shutil.copyfile(rootfs, disk)
        data_disk = Path(directory) / 'blank-data.ext4'
        with data_disk.open('wb') as f:
            f.truncate(16 * 1024 * 1024)
        mkfs = shutil.which('mkfs.ext4')
        if not mkfs:
            raise RuntimeError('mkfs.ext4 required for disposable QEMU data disk')
        subprocess.run([mkfs, '-q', '-F', str(data_disk)], check=True, stdout=subprocess.DEVNULL)
        cmd = [str(qemu), '-M', 'virt', '-cpu', 'cortex-a53', '-smp', '1',
               '-m', '256', '-nographic', '-monitor', 'none', '-serial', 'null',
               '-kernel', str(kernel), '-append', 'rootwait root=/dev/vda console=ttyAMA0 ve_tls_dev=1',
               '-netdev', f'user,id=eth0,hostfwd=tcp:127.0.0.1:{port}-:8443',
               '-device', 'virtio-net-device,netdev=eth0',
               '-drive', f'file={secrets},if=none,format=raw,readonly=on,id=hd2',
               '-device', 'virtio-blk-device,drive=hd2',
               '-drive', f'file={data_disk},if=none,format=raw,id=hd1',
               '-device', 'virtio-blk-device,drive=hd1',
               '-drive', f'file={disk},if=none,format=raw,id=hd0',
               '-device', 'virtio-blk-device,drive=hd0']
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                                start_new_session=True)
        try:
            deadline = time.monotonic() + timeout
            last_error = ''
            while time.monotonic() < deadline:
                if proc.poll() is not None:
                    log = proc.stderr.read().decode(errors='replace')[-2000:]
                    raise RuntimeError(f'QEMU exited before TLS was ready: {log}')
                try:
                    response = tls_request(port, credentials/'ca.pem', *authorized_clients[0])
                    if not is_ready(response):
                        raise RuntimeError(f'Guest HTTPS readiness rejected: {response[:1000]!r}')
                    # Gate the run on the guest becoming ready; once ready, any
                    # failure is an acceptance failure, not a boot retry.
                    for cert, key in authorized_clients[1:]:
                        if not is_ready(tls_request(port, credentials/'ca.pem', cert, key)):
                            raise RuntimeError(f'SECURITY FAILURE: authorized client refused: {cert}')
                    for cert, key in revoked_clients:
                        try:
                            denied = tls_request(port, credentials/'ca.pem', cert, key)
                        except (ssl.SSLError, ConnectionResetError, BrokenPipeError, OSError):
                            denied = b''
                        if is_ready(denied):
                            raise RuntimeError(f'SECURITY FAILURE: revoked client accepted: {cert}')
                    # A client without a certificate must not be able to receive HTTP 200.
                    try:
                        anonymous = tls_request(port, credentials/'ca.pem')
                    except (ssl.SSLError, ConnectionResetError, BrokenPipeError, OSError):
                        anonymous = b''
                    if is_ready(anonymous):
                        raise RuntimeError('SECURITY FAILURE: client without certificate was accepted')
                    print('PASS: Native QEMU ARM64 mTLS readiness and anonymous rejection')
                    print(f'PASS: {len(authorized_clients)} approved clients; {len(revoked_clients)} revoked clients rejected')
                    print(f'PASS: Disposable QEMU rootfs verified over localhost:{port}')
                    return
                except (OSError, ssl.SSLError, TimeoutError) as exc:
                    last_error = str(exc)
                    time.sleep(0.5)
            raise TimeoutError(f'ARM64 native TLS acceptance timed out after {timeout}s: {last_error}')
        finally:
            if proc.poll() is None:
                os.killpg(proc.pid, signal.SIGTERM)
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait()
            if proc.stderr:
                proc.stderr.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--credentials', default=str(Path.home()/'.virtualedge/tls-native-dev'))
    parser.add_argument('--timeout', type=int, default=180)
    parser.add_argument('--port', type=int, default=18444)
    parser.add_argument('--tls-image', type=Path, help='Specific development TLS disk to mount read-only')
    parser.add_argument('--approved', nargs=2, action='append', metavar=('CERT','KEY'), help='Approved client certificate/key pair; repeatable')
    parser.add_argument('--revoked', nargs=2, action='append', metavar=('CERT','KEY'), help='Revoked client certificate/key pair; repeatable')
    args = parser.parse_args()
    try:
        if not 1024 <= args.port <= 65535 or not 10 <= args.timeout <= 1800:
            parser.error('port must be 1024–65535 and timeout 10–1800 seconds')
        run(args.credentials, args.timeout, args.port, args.tls_image, args.approved, args.revoked)
    except (OSError, ValueError, RuntimeError, TimeoutError) as exc:
        print(f'FAIL: {exc}', file=sys.stderr)
        sys.exit(1)
