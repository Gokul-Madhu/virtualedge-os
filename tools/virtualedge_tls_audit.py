#!/usr/bin/env python3
"""Fail-closed preflight of VirtualEdge *development* TLS credentials.

This is a preflight diagnostic, not a proof of secure provisioning or trusted time.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import sys


def openssl(*args):
    p = subprocess.run(['openssl', *map(str, args)], capture_output=True, text=True, timeout=12)
    if p.returncode:
        raise ValueError('OpenSSL check failed: ' + (p.stderr.strip() or 'unknown error'))
    return p.stdout


def private(path):
    if path.is_symlink() or not path.is_file():
        raise ValueError(f'private key missing, symbolic link, or not regular: {path.name}')
    if path.stat().st_mode & 0o077:
        raise ValueError(f'private key accessible to group/others: {path.name}')


def certificate(path):
    if path.is_symlink() or not path.is_file():
        raise ValueError(f'certificate missing, symbolic link, or not regular: {path.name}')
    detail = openssl('x509', '-in', path, '-noout', '-text', '-dates')
    match = re.search(r'notAfter=(.+)', detail)
    if not match:
        raise ValueError(f'certificate expiry missing: {path.name}')
    expires = datetime.strptime(match.group(1).strip(), '%b %d %H:%M:%S %Y %Z').replace(tzinfo=timezone.utc)
    match = re.search(r'notBefore=(.+)', detail)
    starts = datetime.strptime(match.group(1).strip(), '%b %d %H:%M:%S %Y %Z').replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    if starts > now or expires <= now:
        raise ValueError(f'certificate outside validity period: {path.name}')
    return detail, expires


def public_from_cert(cert):
    return openssl('x509', '-in', cert, '-pubkey', '-noout').strip()


def public_from_key(key):
    return openssl('pkey', '-in', key, '-pubout').strip()


def audit(directory, warn_days=14):
    raw = Path(directory).expanduser()
    if raw.is_symlink():
        raise ValueError('credential directory is a symbolic link')
    root = raw.resolve()
    if not root.is_dir() or root.stat().st_mode & 0o077:
        raise ValueError('credential directory missing or group/world accessible')
    for name in ('ca.key', 'client.key', 'server.key'):
        private(root / name)
    ca, ca_exp = certificate(root/'ca.pem')
    server, server_exp = certificate(root/'server.pem')
    client, client_exp = certificate(root/'client.pem')
    if 'CA:TRUE' not in ca or 'Certificate Sign' not in ca:
        raise ValueError('CA certificate lacks CA signing constraints')
    if 'TLS Web Server Authentication' not in server or 'CA:FALSE' not in server:
        raise ValueError('server certificate lacks serverAuth or CA:FALSE')
    if 'TLS Web Client Authentication' not in client or 'CA:FALSE' not in client:
        raise ValueError('client certificate lacks clientAuth or CA:FALSE')
    if not re.search(r'DNS:localhost(?:\s|,|$)', server) or 'IP Address:127.0.0.1' not in server:
        raise ValueError('server certificate lacks localhost/127.0.0.1 SAN')
    for kind in ('ca', 'server', 'client'):
        if public_from_cert(root/f'{kind}.pem') != public_from_key(root/f'{kind}.key'):
            raise ValueError(f'{kind} private key does not match certificate')
    for kind in ('server','client'):
        openssl('verify', '-CAfile', root/'ca.pem', root/f'{kind}.pem')
    remaining = {kind: int((date - datetime.now(timezone.utc)).total_seconds()//86400)
                 for kind, date in (('ca',ca_exp),('server',server_exp),('client',client_exp))}
    warnings = [f'{kind} certificate expires in {days} days' for kind,days in remaining.items() if days < warn_days]
    return {'status':'valid', 'scope':'development', 'days_remaining':remaining, 'warnings':warnings,
            'production_approved':False}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--credentials', required=True)
    p.add_argument('--warn-days', type=int, default=14)
    p.add_argument('--json', action='store_true')
    args = p.parse_args()
    if not 0 <= args.warn_days <= 365:
        p.error('--warn-days must be 0..365')
    try:
        result = audit(args.credentials, args.warn_days)
    except (ValueError, OSError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({'status':'invalid','error':str(exc)}) if args.json else f'FAIL: {exc}', file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, sort_keys=True))
    else:
        print('PASS: development TLS certificates valid, trusted and private-key matched')
        for warning in result['warnings']:
            print('WARNING: ' + warning)
        print('NOT production-approved: CA and device keys are development credentials')
    return 0

if __name__ == '__main__':
    sys.exit(main())
