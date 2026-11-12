#define _POSIX_C_SOURCE 200809L
/* VirtualEdge v0.26: native signed-image preflight; deliberately does NOT install.
 * Inputs are already extracted from a signed bundle by a trusted local operator.
 * The strict manifest grammar matches virtualedge_release.py pack(), and the
 * Ed25519 signature covers the exact manifest file bytes.
 */
#include <ctype.h>
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <limits.h>
#include <openssl/evp.h>
#include <openssl/pem.h>
#include <openssl/crypto.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

#define IMAGE_LIMIT (1024ULL * 1024ULL * 1024ULL)

static void fail(const char *reason) { fprintf(stderr, "FAIL: %s\n", reason); exit(1); }
static int valid_board(const char *p) {
    size_t n = strlen(p);
    if (n < 1 || n > 64 || !((p[0] >= 'a' && p[0] <= 'z') || isdigit((unsigned char)p[0]))) return 0;
    for (size_t i = 0; i < n; i++) {
        unsigned char c = (unsigned char)p[i];
        if (!((c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '.' || c == '_' || c == '-')) return 0;
    }
    return 1;
}
static int semver(const char *v, uint64_t out[3]) {
    if (!v || !*v) return 0;
    for (int k = 0; k < 3; k++) {
        if (!isdigit((unsigned char)*v)) return 0;
        if (*v == '0' && isdigit((unsigned char)v[1])) return 0;
        uint64_t number = 0;
        do {
            unsigned d = (unsigned)(*v++ - '0');
            if (number > (UINT64_MAX - d) / 10) return 0;
            number = number * 10 + d;
        } while (isdigit((unsigned char)*v));
        out[k] = number;
        if (k < 2) { if (*v++ != '.') return 0; }
    }
    return *v == 0;
}
static int version_at_least(const char *current, const char *floor) {
    uint64_t a[3], b[3];
    if (!semver(current, a) || !semver(floor, b)) return 0;
    for (int i = 0; i < 3; i++) {
        if (a[i] != b[i]) return a[i] > b[i];
    }
    return 1;
}
static int open_regular(const char *path, uint64_t maximum, size_t *size) {
    int fd = open(path, O_RDONLY | O_NOFOLLOW | O_CLOEXEC);
    if (fd < 0) fail("input missing, unreadable, or symlinked");
    struct stat st;
    if (fstat(fd, &st) || !S_ISREG(st.st_mode) || st.st_size <= 0 || (uint64_t)st.st_size > maximum) {
        close(fd); fail("input not a regular file or outside size limits");
    }
    *size = (size_t)st.st_size;
    return fd;
}
static void read_exact(int fd, unsigned char *buf, size_t count) {
    size_t pos = 0;
    while (pos < count) {
        ssize_t n = read(fd, buf + pos, count - pos);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) fail("short input read");
        pos += (size_t)n;
    }
    unsigned char extra;
    ssize_t n;
    do { n = read(fd, &extra, 1); } while (n < 0 && errno == EINTR);
    if (n != 0) fail("input changed during read");
}
static void validate_manifest(const char *m, size_t size, const char *expected_board,
                              const char *minimum_version, uint64_t *image_size,
                              char sha[65], char version[96]) {
    char board[65] = {0};
    int end = -1;
    /* Match only the canonical, lexicographically ordered JSON emitted by pack().
       No whitespace, escaping, duplicate properties, or trailing bytes accepted. */
    unsigned long long bytes = 0;
    int found = sscanf(m,
        "{\"board\":\"%64[a-z0-9._-]\",\"format\":\"virtualedge-image-v1\","
        "\"image\":\"image.bin\",\"sha256\":\"%64[0-9a-f]\",\"size\":%llu,"
        "\"version\":\"%95[0-9.]\"}%n", board, sha, &bytes, version, &end);
    if (found != 4 || end < 0 || (size_t)end + 1 != size || m[end] != '\n')
        fail("manifest is malformed or noncanonical");
    if (!valid_board(board) || strcmp(board, expected_board)) fail("board mismatch");
    if (strlen(sha) != 64) fail("invalid image digest");
    if (bytes == 0 || bytes > IMAGE_LIMIT) fail("invalid image size");
    if (!version_at_least(version, minimum_version)) fail("version below minimum or invalid");
    /* Ensure there are no leading zeroes in the image size. */
    char amount[32]; snprintf(amount, sizeof(amount), "%llu", bytes);
    char token[48]; snprintf(token, sizeof(token), "\"size\":%s,", amount);
    if (!strstr(m, token)) fail("noncanonical image size");
    *image_size = (uint64_t)bytes;
}
static void verify_signature(const unsigned char *manifest, size_t manifest_size,
                             const unsigned char *sig, size_t signature_size,
                             const char *pubfile) {
    if (signature_size != 64) fail("invalid Ed25519 signature length");
    FILE *fp = fopen(pubfile, "r");
    if (!fp) fail("trusted public key unavailable");
    EVP_PKEY *key = PEM_read_PUBKEY(fp, NULL, NULL, NULL);
    fclose(fp);
    if (!key || EVP_PKEY_base_id(key) != EVP_PKEY_ED25519) fail("expected Ed25519 public key");
    EVP_MD_CTX *ctx = EVP_MD_CTX_new();
    if (!ctx) fail("crypto allocation error");
    int ok = EVP_DigestVerifyInit(ctx, NULL, NULL, NULL, key) == 1 &&
             EVP_DigestVerify(ctx, sig, signature_size, manifest, manifest_size) == 1;
    EVP_MD_CTX_free(ctx);
    EVP_PKEY_free(key);
    if (!ok) fail("signature verification failed");
}
static void verify_image(int fd, size_t actual_size, uint64_t expected_size, const char *expected_sha) {
    if ((uint64_t)actual_size != expected_size) fail("image size mismatch");
    EVP_MD_CTX *ctx = EVP_MD_CTX_new();
    if (!ctx || EVP_DigestInit_ex(ctx, EVP_sha256(), NULL) != 1) fail("SHA-256 initialization failed");
    unsigned char buffer[65536];
    uint64_t total = 0;
    for (;;) {
        ssize_t n = read(fd, buffer, sizeof(buffer));
        if (n < 0 && errno == EINTR) continue;
        if (n < 0) fail("image read failed");
        if (n == 0) break;
        total += (uint64_t)n;
        if (total > expected_size || EVP_DigestUpdate(ctx, buffer, (size_t)n) != 1)
            fail("image exceeds manifest size or hash failure");
    }
    unsigned char digest[32]; unsigned len = 0;
    if (total != expected_size || EVP_DigestFinal_ex(ctx, digest, &len) != 1 || len != 32)
        fail("image incomplete or hash failed");
    EVP_MD_CTX_free(ctx);
    char hex[65];
    for (int i = 0; i < 32; i++) snprintf(hex + i * 2, 3, "%02x", digest[i]);
    if (CRYPTO_memcmp(hex, expected_sha, 64) != 0) fail("image SHA-256 mismatch");
}
int main(int argc, char **argv) {
    if (argc != 7) {
        fprintf(stderr, "Usage: %s MANIFEST SIG IMAGE TRUSTED_ED25519_PUB BOARD MIN_VERSION\n", argv[0]);
        return 2;
    }
    if (!valid_board(argv[5])) fail("invalid target board");
    uint64_t dummy[3];
    if (!semver(argv[6], dummy)) fail("invalid minimum version");
    size_t msize, ssize, isize;
    int mf = open_regular(argv[1], 4096, &msize);
    unsigned char manifest[4097] = {0};
    read_exact(mf, manifest, msize); close(mf);
    int sf = open_regular(argv[2], 128, &ssize);
    unsigned char sig[128];
    read_exact(sf, sig, ssize); close(sf);
    char sha[65] = {0}, release_version[96] = {0};
    uint64_t expected_size = 0;
    validate_manifest((char *)manifest, msize, argv[5], argv[6], &expected_size, sha, release_version);
    verify_signature(manifest, msize, sig, ssize, argv[4]);
    int imagefd = open_regular(argv[3], IMAGE_LIMIT, &isize);
    verify_image(imagefd, isize, expected_size, sha);
    close(imagefd);
    printf("PASS: signed image verified for %s version %s (Ed25519 + SHA-256); NO installation performed\n",
           argv[5], release_version);
    return 0;
}
