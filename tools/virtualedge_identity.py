#!/usr/bin/env python3
"""Development-only per-client X.509 issuance and CRL management.

CA private key is only used on provisioning host and must never be put on QEMU.
Requires existing CA credentials created by virtualedge_tls_provision.py.
"""
import argparse
import os
from pathlib import Path
import re
import subprocess
import sys

ID = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9_-]{0,47}$')

def run(*args):
    p = subprocess.run(['openssl', *map(str, args)], capture_output=True, text=True, timeout=20)
    if p.returncode:
        raise ValueError('OpenSSL operation failed: ' + (p.stderr.strip()[-500:] or str(p.returncode)))
    return p.stdout

def private(path):
    if path.is_symlink() or not path.is_file() or (path.stat().st_mode & 0o077):
        raise ValueError(f'Missing, symlinked, or insecure private key: {path}')

def check_ca(ca):
    if ca.is_symlink() or not ca.is_dir() or ca.stat().st_mode & 0o077:
        raise ValueError('CA directory must exist with mode 0700')
    private(ca / 'ca.key')
    if not (ca / 'ca.pem').is_file() or (ca / 'ca.pem').is_symlink():
        raise ValueError('CA certificate missing or symlinked')

def cfg(ca):
    # Never resolve a client-provided path into an OpenSSL command line template.
    # The path to the CA is controlled by the local user running this tool.
    from pathlib import Path
    path = ca / 'identity-openssl.cnf'
    if not path.exists():
        raise ValueError('Run init first')
    return path

def init(ca):
    check_ca(ca)
    config = ca / 'identity-openssl.cnf'
    if config.exists() or config.is_symlink() or (ca / 'index.txt').exists():
        raise ValueError('Identity CA database already initialized; refusing to reset')
    if re.search(r'[^a-zA-Z0-9_./-]', str(ca)):
        raise ValueError('CA path can only contain letters, numbers, /, ., _, -')
    (ca / 'newcerts').mkdir(mode=0o700)
    (ca / 'index.txt').write_text('')
    (ca / 'serial').write_text('1000\n')
    (ca / 'crlnumber').write_text('1000\n')
    # OpenSSL config uses only validated local CA path characters.
    config.write_text(f'''[ ca ]
default_ca = ca_default
[ ca_default ]
dir = {ca}
database = $dir/index.txt
new_certs_dir = $dir/newcerts
certificate = $dir/ca.pem
private_key = $dir/ca.key
serial = $dir/serial
crlnumber = $dir/crlnumber
default_md = sha256
default_days = 30
default_crl_days = 7
policy = policy_any
x509_extensions = client_ext
unique_subject = no
[ policy_any ]
commonName = supplied
[ client_ext ]
basicConstraints = critical,CA:FALSE
keyUsage = critical,digitalSignature
extendedKeyUsage = clientAuth
''')
    for name in ('index.txt', 'serial', 'crlnumber', config.name):
        (ca / name).chmod(0o600)
    generate_crl(ca)
    print('Initialized development certificate registry and CRL')

def generate_crl(ca):
    result = ca / 'client-revocations.pem'
    if result.is_symlink():
        raise ValueError('CRL output cannot be a symlink')
    run('ca', '-batch', '-config', cfg(ca), '-gencrl', '-out', result)
    result.chmod(0o644)
    return result

def issue(ca, identity):
    if not ID.fullmatch(identity):
        raise ValueError('Identity must be 1-48 alphanumeric, underscore or hyphen characters')
    config = cfg(ca)
    out = ca / 'clients' / identity
    if out.exists() or out.is_symlink():
        raise ValueError('Identity exists; refusing to overwrite')
    out.parent.mkdir(mode=0o700, exist_ok=True)
    out.mkdir(mode=0o700)
    try:
        key = out / 'client.key'
        cert = out / 'client.pem'
        csr = out / 'client.csr'
        run('genpkey', '-algorithm', 'EC', '-pkeyopt', 'ec_paramgen_curve:P-256', '-out', key)
        key.chmod(0o600)
        run('req', '-new', '-key', key, '-subj', f'/CN=VE-{identity}', '-out', csr)
        run('ca', '-batch', '-config', config, '-in', csr, '-out', cert, '-notext')
        if 'TLS Web Client Authentication' not in run('x509', '-in', cert, '-noout', '-text'):
            raise ValueError('Issued certificate lacks clientAuth')
        print(f'Issued unique development client identity {identity}: {cert}')
    except Exception:
        # Keep failed output for inspection; never attempt to reissue an issued identity.
        raise

def revoke(ca, identity):
    if not ID.fullmatch(identity):
        raise ValueError('Invalid client identity')
    cert = ca / 'clients' / identity / 'client.pem'
    if cert.is_symlink() or not cert.is_file():
        raise ValueError('Certificate not found')
    run('ca', '-batch', '-config', cfg(ca), '-revoke', cert)
    generate_crl(ca)
    print(f'Revoked {identity}; rebuild credential disk and restart TLS gateway to enforce')

def rotate(ca, old_identity, new_identity):
    """Issue and verify a new identity before revoking the old certificate.

    This deliberately never overwrites a client's key. The caller distributes
    the new credential bundle separately and must refresh the deployed CRL.
    """
    if not ID.fullmatch(old_identity) or not ID.fullmatch(new_identity):
        raise ValueError('Invalid client identity')
    if old_identity == new_identity:
        raise ValueError('Replacement identity must have a different name')
    old_cert = ca / 'clients' / old_identity / 'client.pem'
    if old_cert.is_symlink() or not old_cert.is_file():
        raise ValueError('Old identity certificate missing or unsafe')
    # Ensure the old certificate belongs to this CA and is not already revoked.
    run('verify', '-CAfile', ca / 'ca.pem', '-crl_check',
        '-CRLfile', ca / 'client-revocations.pem', old_cert)
    issue(ca, new_identity)
    new_cert = ca / 'clients' / new_identity / 'client.pem'
    try:
        run('verify', '-CAfile', ca / 'ca.pem', '-crl_check',
            '-CRLfile', ca / 'client-revocations.pem', new_cert)
        private(ca / 'clients' / new_identity / 'client.key')
    except Exception as exc:
        raise ValueError(f'Replacement verification failed; old identity retained: {exc}') from exc
    revoke(ca, old_identity)
    print(f'Rotated {old_identity} -> {new_identity}. Deliver new credentials securely; '
          'rebuild the development credential disk and restart QEMU to enforce revocation.')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--ca', required=True, type=Path)
    sub = p.add_subparsers(dest='command', required=True)
    sub.add_parser('init')
    i = sub.add_parser('issue'); i.add_argument('identity')
    r = sub.add_parser('revoke'); r.add_argument('identity')
    rot = sub.add_parser('rotate'); rot.add_argument('old_identity'); rot.add_argument('new_identity')
    sub.add_parser('crl')
    a = p.parse_args()
    os.umask(0o077)
    ca = a.ca.expanduser().resolve()
    try:
        check_ca(ca)
        if a.command == 'init': init(ca)
        elif a.command == 'issue': issue(ca, a.identity)
        elif a.command == 'revoke': revoke(ca, a.identity)
        elif a.command == 'rotate': rotate(ca, a.old_identity, a.new_identity)
        else: print('Created CRL:', generate_crl(ca))
    except (ValueError, OSError, subprocess.TimeoutExpired) as e:
        p.exit(1, f'ERROR: {e}\n')

if __name__ == '__main__': main()
