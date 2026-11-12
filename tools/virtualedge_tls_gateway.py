#!/usr/bin/env python3
"""Loopback-only mutual-TLS gateway for the QEMU VirtualEdge development API.

This is a host-side development gateway, NOT an in-guest TLS stack or production proxy.
"""
import argparse
import http.client
import http.server
import os
from pathlib import Path
import ssl
import sys

ROUTES = frozenset(("/", "/dashboard", "/health", "/ready", "/api/v1/telemetry",
                    "/api/v1/diagnostics", "/api/v1/device", "/api/v1/config",
                    "/api/v1/events", "/api/v1/metrics"))
MAX_RESPONSE = 1024 * 1024

class Handler(http.server.BaseHTTPRequestHandler):
    server_version = "VirtualEdgeTLS/0.14"
    protocol_version = "HTTP/1.1"

    def do_GET(self):
        if self.path not in ROUTES:
            return self.fail(404, b'{"error":"not_found"}')
        if len(str(self.headers)) > 8192:
            return self.fail(431, b'{"error":"headers_too_large"}')
        upstream = http.client.HTTPConnection('127.0.0.1', self.server.upstream_port, timeout=4)
        try:
            # Deliberately allowlist request headers. Browser/client auth is enforced by mTLS.
            headers = {}
            if self.server.forward_basic:
                authorization = self.headers.get('Authorization')
                if authorization and authorization.startswith('Basic ') and len(authorization) <= 2048:
                    headers['Authorization'] = authorization
            upstream.request('GET', self.path, headers=headers)
            response = upstream.getresponse()
            if response.status not in (200, 400, 401, 403, 404, 405, 503):
                return self.fail(502, b'{"error":"unexpected_upstream_response"}')
            length = response.getheader('Content-Length')
            if length is not None and (not length.isdigit() or int(length) > MAX_RESPONSE):
                return self.fail(502, b'{"error":"upstream_response_too_large"}')
            body = response.read(MAX_RESPONSE + 1)
            if len(body) > MAX_RESPONSE:
                return self.fail(502, b'{"error":"upstream_response_too_large"}')
            self.send_response(response.status)
            content_type = response.getheader('Content-Type', 'application/json')
            if not (content_type.startswith('application/json') or content_type.startswith('text/html')):
                content_type = 'application/octet-stream'
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; form-action 'none'")
            if response.status == 401:
                self.send_header('WWW-Authenticate', 'Basic realm="VirtualEdge"')
            self.end_headers()
            self.wfile.write(body)
        except (OSError, http.client.HTTPException, TimeoutError) as exc:
            self.log_error('upstream error: %s', exc)
            try:
                self.fail(502, b'{"error":"upstream_unavailable"}')
            except (BrokenPipeError, ConnectionResetError):
                pass
        finally:
            upstream.close()

    def do_HEAD(self):
        self.fail(405, b'{"error":"method_not_allowed"}')

    def do_POST(self):
        self.fail(405, b'{"error":"method_not_allowed"}')

    def fail(self, status, body):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        sys.stderr.write('VirtualEdge TLS: ' + fmt % args + '\n')

class Server(http.server.ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--credentials', required=True, help='directory containing ca.pem, server.pem and server.key')
    p.add_argument('--port', type=int, default=18443)
    p.add_argument('--upstream-port', type=int, default=18080)
    p.add_argument('--forward-basic', action='store_true', help='forward guest HTTP Basic header through mTLS')
    args = p.parse_args()
    if not (1024 <= args.port <= 65535 and 1 <= args.upstream_port <= 65535):
        p.error('invalid port')
    directory = Path(args.credentials)
    for filename in ('ca.pem', 'server.pem', 'server.key'):
        f = directory / filename
        if not f.is_file() or f.is_symlink():
            p.error(f'invalid or missing credential: {f}')
    if (directory / 'server.key').stat().st_mode & 0o077:
        p.error('server.key must not be group/world accessible (chmod 600)')
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.verify_mode = ssl.CERT_REQUIRED
    context.load_verify_locations(cafile=str(directory / 'ca.pem'))
    context.load_cert_chain(certfile=str(directory / 'server.pem'), keyfile=str(directory / 'server.key'))
    with Server(('127.0.0.1', args.port), Handler) as server:
        server.socket = context.wrap_socket(server.socket, server_side=True)
        server.upstream_port = args.upstream_port
        server.forward_basic = args.forward_basic
        print(f'VirtualEdge mTLS gateway: https://localhost:{args.port}/dashboard', flush=True)
        print('Client certificates are REQUIRED; upstream stays on 127.0.0.1.', flush=True)
        server.serve_forever(poll_interval=0.2)

if __name__ == '__main__':
    main()
