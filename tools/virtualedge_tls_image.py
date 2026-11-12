#!/usr/bin/env python3
"""Create a disposable ext4 QEMU TLS credential disk (never a firmware rootfs).

Requires e2fsprogs mkfs.ext4 and a validated development credential directory.
This is NOT encrypted key storage and must never be used with production secrets.
"""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
FILES = ('ca.pem', 'server.pem', 'server.key')
OPTIONAL_CRL = 'client-revocations.pem'


def create(credentials: Path, output: Path):
    credentials = credentials.expanduser().resolve(strict=True)
    output = output.expanduser().absolute()
    if output.is_symlink() or output.exists():
        raise ValueError(f'Refusing to overwrite an existing credential disk: {output}')
    if not output.parent.is_dir() or output.parent.is_symlink():
        raise ValueError('Output parent must be an existing directory (not a symlink)')
    for name in FILES:
        p = credentials / name
        if not p.is_file() or p.is_symlink():
            raise ValueError(f'Missing or symlinked credential: {name}')
    audited = subprocess.run([sys.executable, str(ROOT/'tools/virtualedge_tls_audit.py'),
                             '--credentials', str(credentials)], capture_output=True, text=True)
    if audited.returncode:
        raise ValueError('TLS certificate audit failed: ' + audited.stderr.strip())
    mkfs = shutil.which('mkfs.ext4')
    if not mkfs:
        raise RuntimeError('mkfs.ext4 missing: install e2fsprogs in Ubuntu WSL')
    with tempfile.TemporaryDirectory(prefix='ve-tls-build-') as tmp:
        workspace = Path(tmp)
        staged = workspace/'contents'
        staged.mkdir(mode=0o700)
        for name in FILES:
            dest = staged/name
            shutil.copyfile(credentials/name, dest, follow_symlinks=False)
            dest.chmod(0o600 if name.endswith('.key') else 0o644)
        crl = credentials / OPTIONAL_CRL
        if crl.is_symlink():
            raise ValueError('CRL cannot be a symlink')
        # An identity-aware development CA must carry a CRL. Refuse to
        # package credentials that would disable revocation in the guest.
        if (credentials / 'identity-openssl.cnf').exists() and not crl.exists():
            raise ValueError('Identity CA requires a signed CRL for credential disk')
        if crl.exists():
            if not crl.is_file():
                raise ValueError('CRL is not a file')
            # Verify CRL is signed by the same trusted CA.
            verify = subprocess.run(['openssl', 'crl', '-in', str(crl), '-noout',
                                     '-verify', '-CAfile', str(credentials/'ca.pem')],
                                    capture_output=True, text=True)
            if verify.returncode:
                raise ValueError('CRL signature verification failed')
            # A valid signature alone does not guarantee that the CRL is current.
            # Fail closed for an expired or not-yet-valid CRL before packaging it.
            validity = subprocess.run(['openssl', 'crl', '-in', str(crl), '-noout',
                                       '-lastupdate', '-nextupdate'],
                                      capture_output=True, text=True)
            if validity.returncode:
                raise ValueError('CRL validity dates cannot be read')
            from datetime import datetime, timezone
            from email.utils import parsedate_to_datetime
            values = dict(line.split('=', 1) for line in validity.stdout.splitlines() if '=' in line)
            try:
                last = parsedate_to_datetime(values['lastUpdate']).astimezone(timezone.utc)
                future = parsedate_to_datetime(values['nextUpdate']).astimezone(timezone.utc)
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError('CRL validity dates are missing or malformed') from exc
            now = datetime.now(timezone.utc)
            if not (last <= now < future):
                raise ValueError('CRL expired or not yet valid; regenerate on the trusted host')
            shutil.copyfile(crl, staged/OPTIONAL_CRL)
            (staged/OPTIONAL_CRL).chmod(0o644)
        image = workspace/'credentials.ext4'
        with image.open('wb') as f:
            f.truncate(16*1024*1024)
        subprocess.run([mkfs, '-F', '-q', '-L', 'VETLSDEV', '-d', str(staged), str(image)],
                       check=True, stdout=subprocess.DEVNULL)
        os.chmod(image, 0o600)
        # Exclusive create after all checks; this will not overwrite an existing disk.
        with output.open('xb') as destination, image.open('rb') as source:
            os.fchmod(destination.fileno(), 0o600)
            shutil.copyfileobj(source, destination)
    print(f'Created disposable TLS credential disk: {output}')
    print('WARNING: This ext4 disk contains an UNENCRYPTED development private key.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--credentials', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    try:
        create(args.credentials, args.output)
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f'ERROR: {exc}\n')
