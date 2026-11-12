#define _POSIX_C_SOURCE 200809L
#include <arpa/inet.h>
#include <errno.h>
#include <netinet/in.h>
#include <openssl/err.h>
#include <openssl/ssl.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/time.h>
#include <unistd.h>

/* Development-grade embedded mTLS reverse proxy. No write endpoints. */
#define REQ_MAX 8192
#define REPLY_MAX (1024 * 1024)
#define TLS_PORT 8443
static int env_port(const char *name, int fallback) {
    const char *value=getenv(name);
    if (!value || !*value) return fallback;
    char *end=NULL; long n=strtol(value,&end,10);
    if (*end || n<1024 || n>65535) return -1;
    return (int)n;
}
static volatile sig_atomic_t running = 1;
static void stop_signal(int signal_number) { (void)signal_number; running = 0; }
static int secure_file(const char *path, int private_key) {
    struct stat s;
    if (lstat(path, &s) || !S_ISREG(s.st_mode) ||
        (private_key && (s.st_mode & 0077))) return 0;
    return 1;
}
static int allowed(const char *path) {
    static const char *const routes[] = {
        "/", "/dashboard", "/health", "/ready", "/api/v1/telemetry",
        "/api/v1/diagnostics", "/api/v1/device", "/api/v1/config",
        "/api/v1/events", "/api/v1/metrics"
    };
    for (size_t i = 0; i < sizeof(routes)/sizeof(routes[0]); ++i)
        if (!strcmp(path, routes[i])) return 1;
    return 0;
}
static void error_response(SSL *tls, int status, const char *reason) {
    char response[512];
    int n = snprintf(response, sizeof(response),
        "HTTP/1.1 %d %s\r\nContent-Type: application/json\r\n"
        "Content-Length: 2\r\nCache-Control: no-store\r\nConnection: close\r\n\r\n{}",
        status, reason);
    if (n > 0 && (size_t)n < sizeof(response)) SSL_write(tls, response, n);
}
static int forward_to_api(SSL *tls, const char *path) {
    int upstream_port=env_port("VE_TLS_UPSTREAM_PORT",8080);
    if (upstream_port<0) return -1;
    int fd = socket(AF_INET, SOCK_STREAM, 0);
    if (fd < 0) return -1;
    struct timeval timeout = { .tv_sec = 4, .tv_usec = 0 };
    setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout));
    setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &timeout, sizeof(timeout));
    struct sockaddr_in addr = { .sin_family=AF_INET, .sin_port=htons((uint16_t)upstream_port) };
    inet_pton(AF_INET, "127.0.0.1", &addr.sin_addr);
    if (connect(fd, (struct sockaddr *)&addr, sizeof(addr)) != 0) { close(fd); return -1; }
    char request[256];
    int req_len = snprintf(request, sizeof(request),
        "GET %s HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n", path);
    if (req_len <= 0 || (size_t)req_len >= sizeof(request)) {close(fd); return -1;}
    for (int offset=0; offset<req_len;) {
        ssize_t n = send(fd, request + offset, (size_t)(req_len - offset), 0);
        if (n <= 0) { close(fd); return -1; }
        offset += (int)n;
    }
    char buf[4096];
    size_t total=0;
    int result=0;
    for (;;) {
        ssize_t n=recv(fd, buf, sizeof(buf), 0);
        if (n == 0) break;
        if (n < 0 || total + (size_t)n > REPLY_MAX) {result=-1; break;}
        total += (size_t)n;
        for (ssize_t pos=0; pos<n;) {
            int written=SSL_write(tls, buf + pos, (int)(n-pos));
            if (written <= 0) {result=-1; break;}
            pos += written;
        }
        if (result) break;
    }
    close(fd);
    return result;
}
static void handle(SSL *tls) {
    char buffer[REQ_MAX + 1];
    size_t used=0;
    int complete=0;
    while (used < REQ_MAX) {
        int n=SSL_read(tls, buffer + used, (int)(REQ_MAX-used));
        if (n <= 0) return;
        used += (size_t)n;
        buffer[used]=0;
        if (strstr(buffer, "\r\n\r\n")) {complete=1;break;}
    }
    if (!complete) {error_response(tls, 431, "Request Header Fields Too Large");return;}
    char *end=strstr(buffer,"\r\n");
    if (!end || (size_t)(end-buffer)>255) {error_response(tls,400,"Bad Request");return;}
    *end=0;
    char method[16]={0}, path[128]={0}, version[16]={0}, extra;
    if (sscanf(buffer,"%15s %127s %15s %c",method,path,version,&extra)!=3 ||
        (strcmp(version,"HTTP/1.1") && strcmp(version,"HTTP/1.0")) || path[0]!='/') {
        error_response(tls,400,"Bad Request");return;
    }
    if (strcmp(method,"GET")) {error_response(tls,405,"Method Not Allowed");return;}
    if (!allowed(path)) {error_response(tls,404,"Not Found");return;}
    /* Never forward caller-provided headers (including Authorization) or bodies. */
    if (forward_to_api(tls,path)) {
        /* No response can be inserted after streaming has started. */
        fprintf(stderr,"VirtualEdge TLS upstream failed\n");
    }
}
int main(int argc,char **argv) {
    if (argc!=4) {
        fprintf(stderr,"Usage: %s <CA.pem> <server.pem> <server.key>\n",argv[0]);return 2;
    }
    if (!secure_file(argv[1],0) || !secure_file(argv[2],0) || !secure_file(argv[3],1)) {
        fprintf(stderr,"VirtualEdge TLS: missing or insecure credential files\n"); return 1;
    }
    OPENSSL_init_ssl(0,NULL);
    SSL_CTX *ctx=SSL_CTX_new(TLS_server_method());
    if (!ctx) return 1;
    SSL_CTX_set_min_proto_version(ctx,TLS1_2_VERSION);
    SSL_CTX_set_verify(ctx,SSL_VERIFY_PEER | SSL_VERIFY_FAIL_IF_NO_PEER_CERT,NULL);
    SSL_CTX_set_verify_depth(ctx,2);
    if (SSL_CTX_load_verify_locations(ctx,argv[1],NULL)!=1 ||
        SSL_CTX_use_certificate_file(ctx,argv[2],SSL_FILETYPE_PEM)!=1 ||
        SSL_CTX_use_PrivateKey_file(ctx,argv[3],SSL_FILETYPE_PEM)!=1 ||
        SSL_CTX_check_private_key(ctx)!=1) {
        ERR_print_errors_fp(stderr);SSL_CTX_free(ctx);return 1;
    }
    /* Optional signed CRL for revoking individual development client identities.
     * Fail closed if a configured CRL cannot be loaded or validated.
     * Restart the gateway after replacing the CRL (OpenSSL store is in memory). */
    const char *crl_path = getenv("VE_TLS_CRL_FILE");
    const char *require_crl = getenv("VE_TLS_REQUIRE_CRL");
    if (require_crl && !strcmp(require_crl, "1") && (!crl_path || !*crl_path)) {
        fprintf(stderr, "VirtualEdge TLS: revocation list required but not configured\n");
        SSL_CTX_free(ctx); return 1;
    }
    if (crl_path && *crl_path) {
        if (!secure_file(crl_path, 0)) {
            fprintf(stderr, "VirtualEdge TLS: configured CRL missing or unsafe\n");
            SSL_CTX_free(ctx); return 1;
        }
        X509_STORE *store = SSL_CTX_get_cert_store(ctx);
        X509_LOOKUP *lookup = X509_STORE_add_lookup(store, X509_LOOKUP_file());
        if (!lookup || X509_load_crl_file(lookup, crl_path, X509_FILETYPE_PEM) != 1 ||
            X509_STORE_set_flags(store, X509_V_FLAG_CRL_CHECK | X509_V_FLAG_CRL_CHECK_ALL) != 1) {
            fprintf(stderr, "VirtualEdge TLS: CRL load failed\n");
            SSL_CTX_free(ctx); return 1;
        }
    }
    /* Refuse startup with an expired or not-yet-valid server certificate.
     * A real device must establish trusted wall-clock time before startup. */
    X509 *server_certificate = SSL_CTX_get0_certificate(ctx);
    if (!server_certificate ||
        X509_cmp_current_time(X509_get0_notBefore(server_certificate)) > 0 ||
        X509_cmp_current_time(X509_get0_notAfter(server_certificate)) < 0) {
        fprintf(stderr,"VirtualEdge TLS: server certificate is outside validity period\n");
        SSL_CTX_free(ctx);return 1;
    }
    int tls_port=env_port("VE_TLS_PORT",TLS_PORT);
    if (tls_port<0) {SSL_CTX_free(ctx);return 2;}
    int fd=socket(AF_INET,SOCK_STREAM,0);
    if (fd<0) {SSL_CTX_free(ctx);return 1;}
    int yes=1;
    setsockopt(fd,SOL_SOCKET,SO_REUSEADDR,&yes,sizeof(yes));
    const char *listen_any=getenv("VE_TLS_LISTEN_ANY");
    struct sockaddr_in addr={.sin_family=AF_INET,.sin_port=htons((uint16_t)tls_port)};
    addr.sin_addr.s_addr=htonl(listen_any && !strcmp(listen_any,"1") ? INADDR_ANY : INADDR_LOOPBACK);
    if (bind(fd,(struct sockaddr *)&addr,sizeof(addr)) || listen(fd,8)) {
        perror("VirtualEdge TLS bind/listen");close(fd);SSL_CTX_free(ctx);return 1;
    }
    signal(SIGTERM,stop_signal); signal(SIGINT,stop_signal); signal(SIGPIPE,SIG_IGN);
    fprintf(stderr,"VirtualEdge guest mTLS listening on port %d\n",tls_port);
    while (running) {
        int client=accept(fd,NULL,NULL);
        if (client<0) {if (errno==EINTR) continue;break;}
        struct timeval t={.tv_sec=5,.tv_usec=0};
        setsockopt(client,SOL_SOCKET,SO_RCVTIMEO,&t,sizeof(t));
        setsockopt(client,SOL_SOCKET,SO_SNDTIMEO,&t,sizeof(t));
        SSL *tls=SSL_new(ctx);
        if (tls) {
            SSL_set_fd(tls,client);
            if (SSL_accept(tls)==1 && SSL_get_verify_result(tls)==X509_V_OK)
                handle(tls);
            SSL_shutdown(tls);
            SSL_free(tls);
        }
        close(client);
    }
    close(fd);SSL_CTX_free(ctx);return 0;
}
