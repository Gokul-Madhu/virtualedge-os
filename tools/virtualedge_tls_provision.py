#!/usr/bin/env python3
"""Create development-only, private CA/server/client TLS certificates for VirtualEdge."""
import argparse
import os
from pathlib import Path
import subprocess
import sys


def openssl(*argv):
    subprocess.run(['openssl', *map(str, argv)], check=True, stdout=subprocess.DEVNULL,
                   stderr=subprocess.PIPE, timeout=20)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', required=True)
    args = p.parse_args()
    directory = Path(args.output).expanduser().resolve()
    if directory.is_symlink():
        p.error('output directory must not be symlink')
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    if directory.stat().st_mode & 0o077:
        p.error('credential directory must be private: chmod 700')
    files = ['ca.key', 'ca.pem', 'server.key', 'server.csr', 'server.pem', 'client.key', 'client.csr', 'client.pem', 'server.ext', 'client.ext', 'ca.srl']
    if any((directory / name).exists() or (directory / name).is_symlink() for name in files):
        p.error('credentials already exist; refusing to overwrite keys')
    os.umask(0o077)
    try:
        openssl('genpkey', '-algorithm', 'EC', '-pkeyopt', 'ec_paramgen_curve:P-256', '-out', directory / 'ca.key')
        openssl('req', '-x509', '-new', '-key', directory / 'ca.key', '-sha256', '-days', '90', '-subj', '/CN=VirtualEdge Development CA', '-out', directory / 'ca.pem', '-addext', 'basicConstraints=critical,CA:TRUE', '-addext', 'keyUsage=critical,keyCertSign,cRLSign')
        openssl('genpkey', '-algorithm', 'EC', '-pkeyopt', 'ec_paramgen_curve:P-256', '-out', directory / 'server.key')
        openssl('req', '-new', '-key', directory / 'server.key', '-subj', '/CN=localhost', '-out', directory / 'server.csr')
        (directory / 'server.ext').write_text('basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature\nextendedKeyUsage=serverAuth\nsubjectAltName=DNS:localhost,IP:127.0.0.1\n')
        openssl('x509', '-req', '-in', directory / 'server.csr', '-CA', directory / 'ca.pem', '-CAkey', directory / 'ca.key', '-CAcreateserial', '-out', directory / 'server.pem', '-days', '30', '-sha256', '-extfile', directory / 'server.ext')
        openssl('genpkey', '-algorithm', 'EC', '-pkeyopt', 'ec_paramgen_curve:P-256', '-out', directory / 'client.key')
        openssl('req', '-new', '-key', directory / 'client.key', '-subj', '/CN=VirtualEdge Development Client', '-out', directory / 'client.csr')
        (directory / 'client.ext').write_text('basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature\nextendedKeyUsage=clientAuth\n')
        openssl('x509', '-req', '-in', directory / 'client.csr', '-CA', directory / 'ca.pem', '-CAkey', directory / 'ca.key', '-CAcreateserial', '-out', directory / 'client.pem', '-days', '30', '-sha256', '-extfile', directory / 'client.ext')
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        p.error(f'openssl provisioning failed: {exc}')
    for file in directory.iterdir():
        if file.suffix in ('.key', '.ext', '.csr', '.srl'):
            file.chmod(0o600)
    print(f'Created private development TLS credentials in {directory}')
    print('Keep ca.key and client.key secret; do not commit any generated keys to Git.')
    print('Certificates expire after 30 days (client and server); regenerate in a new directory.')

if __name__ == '__main__':
    main()
