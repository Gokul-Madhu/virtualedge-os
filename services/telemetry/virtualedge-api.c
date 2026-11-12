#define _POSIX_C_SOURCE 200809L
#include <arpa/inet.h>
#include <errno.h>
#include <limits.h>
#include <netinet/in.h>
#include <poll.h>
#include <signal.h>
#include <sys/stat.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <stddef.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <time.h>
#include <unistd.h>
#include "diagnostics.h"
#include "fault_injection.h"

#ifndef VE_CONFIG_FILE
#define VE_CONFIG_FILE "/etc/virtualedge/diagnostics.conf"
#endif
#ifndef VE_EVENT_FILE
#define VE_EVENT_FILE "/var/log/virtualedge/events.log"
#endif
#ifndef VE_PORT
#define VE_PORT 8080
#endif
#ifndef VE_DASHBOARD_FILE
#define VE_DASHBOARD_FILE "/usr/share/virtualedge/dashboard.html"
#endif
#ifndef VE_LOG_MAX_BYTES
#define VE_LOG_MAX_BYTES 65536
#endif
/* Optional board-specific Linux thermal sysfs input in millidegrees Celsius.
 * Empty means simulation. Failure produces INVALID_SENSOR, never silent fallback. */
#ifndef VE_TEMPERATURE_SYSFS
#define VE_TEMPERATURE_SYSFS ""
#endif
#define EVENT_CAP 32
#define BODY_CAP 4096
#define VE_API_VERSION "0.13.0-dev"

static volatile sig_atomic_t running = 1;
static volatile sig_atomic_t config_reload_requested = 0;
static unsigned config_revision = 0;
static int config_valid = 1;
static ve_thresholds limits = {35.0, 0.30, 3.00};
static ve_sensor_data current_sensor;
static unsigned current_faults;
static long current_uptime;
static char history[EVENT_CAP][200];
static unsigned event_total;
static unsigned have_sample;
static const char *temperature_origin = "simulation";

static double read_temperature(void)
{
    if (!VE_TEMPERATURE_SYSFS[0]) {
        temperature_origin = "simulation";
        return 25.0 + (current_uptime % 90) * 0.10;
    }
    temperature_origin = "linux_thermal_sysfs";
    FILE *f = fopen(VE_TEMPERATURE_SYSFS, "r");
    if (!f) return NAN;
    long milli;
    char extra;
    int parsed = fscanf(f, " %ld %c", &milli, &extra);
    fclose(f);
    /* Kernel thermal inputs are commonly millidegrees C. Reject out-of-range
       and malformed values; do not pretend they are physical sensor readings. */
    if (parsed != 1 || milli < -50000 || milli > 150000) return NAN;
    return (double)milli / 1000.0;
}

static void on_signal(int sig)
{
    if (sig == SIGHUP) config_reload_requested = 1;
    else running = 0;
}

static double proc_number(const char *path)
{
    double v = 0;
    FILE *f = fopen(path, "r");
    if (f) { if (fscanf(f, "%lf", &v) != 1) v = 0; fclose(f); }
    return v;
}

static long memory_kb(const char *key)
{
    char name[64], unit[16];
    long value;
    FILE *f = fopen("/proc/meminfo", "r");
    if (!f) return -1;
    while (fscanf(f, "%63s %ld %15s", name, &value, unit) == 3) {
        if (strcmp(key, name) == 0) { fclose(f); return value; }
    }
    fclose(f);
    return -1;
}

static void load_config(void)
{
    FILE *f = fopen(VE_CONFIG_FILE, "r");
    if (!f) {
        /* A missing file is an explicit factory-default configuration. */
        config_valid = errno == ENOENT;
        return;
    }
    char line[160], key[80], extra;
    double value;
    ve_thresholds next = limits;
    int seen = 0, invalid = 0;
    while (fgets(line, sizeof(line), f)) {
        if (line[0] == '#' || line[0] == '\n' || line[0] == '\r') continue;
        if (sscanf(line, " %79[^=]=%lf %c", key, &value, &extra) != 2 || !isfinite(value)) {
            invalid = 1; break;
        }
        if (strcmp(key, "max_temperature_c") == 0 && value >= -50 && value <= 150) {
            next.max_temperature_c = value; seen |= 1;
        } else if (strcmp(key, "max_vibration_g") == 0 && value >= 0 && value <= 20) {
            next.max_vibration_g = value; seen |= 2;
        } else if (strcmp(key, "min_voltage_v") == 0 && value >= 0 && value <= 24) {
            next.min_voltage_v = value; seen |= 4;
        } else { invalid = 1; break; }
    }
    fclose(f);
    if (!invalid && seen == 7) {
        limits = next;
        config_valid = 1;
        config_revision++;
    } else {
        config_valid = 0;
        fprintf(stderr, "VirtualEdge: invalid configuration; preserving previous thresholds\n");
    }
}

static void record_event(unsigned from, unsigned to)
{
    char *dst = history[event_total % EVENT_CAP];
    time_t now = time(NULL);
    snprintf(dst, sizeof(history[0]),
        "{\"timestamp\":%lld,\"uptime_seconds\":%ld,\"previous_mask\":%u,\"fault_mask\":%u}",
        (long long)now, current_uptime, from, to);
    ++event_total;
    /* Keep at most one previous 64 KiB event segment. */
    struct stat st;
    if (stat(VE_EVENT_FILE, &st) == 0 && st.st_size >= VE_LOG_MAX_BYTES) {
        char backup[sizeof(VE_EVENT_FILE) + 8];
        snprintf(backup, sizeof(backup), "%s.1", VE_EVENT_FILE);
        if (rename(VE_EVENT_FILE, backup) != 0)
            fprintf(stderr, "VirtualEdge: event log rotation failed: %s\n", strerror(errno));
    }
    FILE *f = fopen(VE_EVENT_FILE, "a");
    if (f) { fprintf(f, "%s\n", dst); fclose(f); }
    else fprintf(stderr, "VirtualEdge: event log write failed: %s\n", strerror(errno));
}

static void sample(void)
{
    current_uptime = (long)proc_number("/proc/uptime");
    current_sensor = (ve_sensor_data){
        read_temperature(),
        0.05 + (current_uptime % 20) * 0.005,
        3.30 - (current_uptime % 10) * 0.005
    };
    /* A missing/bad physical source remains invalid even in simulation test
       mode: do not allow an injected fault to conceal failed acquisition. */
    int acquisition_invalid = !isfinite(current_sensor.temperature_c);
    if (!acquisition_invalid) ve_apply_fault_injection(&current_sensor);
    unsigned new_faults = ve_evaluate(current_sensor, limits);
    if (have_sample && new_faults != current_faults) record_event(current_faults, new_faults);
    current_faults = new_faults;
    have_sample = 1;
}

static void build_telemetry(char *body, size_t cap)
{
    char temp_json[40];
    if (!isfinite(current_sensor.temperature_c)) {
        strcpy(temp_json, "null");
    } else {
        snprintf(temp_json, sizeof(temp_json), "%.2f", current_sensor.temperature_c);
    }
    snprintf(body, cap,
        "{\"system\":\"VirtualEdge OS\",\"version\":\"0.12.0-dev\","
        "\"architecture\":\"aarch64\",\"uptime_seconds\":%ld,"
        "\"memory_total_kb\":%ld,\"memory_available_kb\":%ld,"
        "\"load_average_1m\":%.2f,\"sensors\":{\"source\":\"%s\","
        "\"temperature_c\":%s,\"temperature_source\":\"%s\","
        "\"vibration_g\":%.3f,\"voltage_v\":%.3f},"
        "\"health\":\"%s\"}",
        current_uptime, memory_kb("MemTotal:"), memory_kb("MemAvailable:"),
        proc_number("/proc/loadavg"),
        VE_TEMPERATURE_SYSFS[0] ? "mixed" : "simulation", temp_json, temperature_origin,
        current_sensor.vibration_g, current_sensor.voltage_v,
        current_faults ? "warning" : "ok");
}

static void build_diagnostics(char *body, size_t cap)
{
    snprintf(body, cap,
        "{\"source\":\"%s\",\"health\":\"%s\",\"fault_mask\":%u,"
        "\"faults\":{\"overtemperature\":%s,\"excessive_vibration\":%s,"
        "\"undervoltage\":%s,\"invalid_sensor\":%s},"
        "\"thresholds\":{\"max_temperature_c\":%.2f,"
        "\"max_vibration_g\":%.3f,\"min_voltage_v\":%.2f}}",
        VE_TEMPERATURE_SYSFS[0] ? "mixed" : "simulation",
        current_faults ? "warning" : "ok", current_faults,
        current_faults & VE_FAULT_OVERTEMP ? "true" : "false",
        current_faults & VE_FAULT_VIBRATION ? "true" : "false",
        current_faults & VE_FAULT_UNDERVOLTAGE ? "true" : "false",
        current_faults & VE_FAULT_INVALID_SENSOR ? "true" : "false",
        limits.max_temperature_c, limits.max_vibration_g, limits.min_voltage_v);
}

static void build_config(char *body, size_t cap)
{
    snprintf(body, cap,
        "{\"read_only\":true,\"config_valid\":%s,\"config_revision\":%u,"
        "\"thresholds\":{\"max_temperature_c\":%.2f,"
        "\"max_vibration_g\":%.3f,\"min_voltage_v\":%.2f}}",
        config_valid ? "true" : "false", config_revision,
        limits.max_temperature_c, limits.max_vibration_g, limits.min_voltage_v);
}

static void build_device(char *body, size_t cap)
{
    char hostname[65] = "virtualedge";
    if (gethostname(hostname, sizeof(hostname) - 1) != 0)
        strcpy(hostname, "virtualedge");
    hostname[sizeof(hostname) - 1] = '\0';
    /* Limit hostname to JSON-safe DNS-label characters. */
    for (size_t i = 0; hostname[i]; ++i) {
        unsigned char c = (unsigned char)hostname[i];
        if (!((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
              (c >= '0' && c <= '9') || c == '-' || c == '.'))
            hostname[i] = '_';
    }
    snprintf(body, cap,
        "{\"name\":\"VirtualEdge OS\",\"hostname\":\"%s\","
        "\"architecture\":\"aarch64\",\"api_version\":\"0.12.0-dev\","
        "\"sensor_mode\":\"%s\",\"control_api_enabled\":false}",
        hostname, VE_TEMPERATURE_SYSFS[0] ? "mixed" : "simulation");
}

/* Liveness is process availability; readiness also requires valid local
 * configuration and successful sensor acquisition. Simulated threshold alarms
 * are diagnostics, not an automatic reason to mark the service unready. */
static int service_ready(void)
{
    return config_valid && have_sample &&
           !(current_faults & VE_FAULT_INVALID_SENSOR);
}

static void build_readiness(char *body, size_t cap)
{
    snprintf(body, cap,
        "{\"status\":\"%s\",\"config_valid\":%s,"
        "\"sensor_acquisition_valid\":%s,\"fault_mask\":%u}",
        service_ready() ? "ready" : "not_ready",
        config_valid ? "true" : "false",
        (have_sample && !(current_faults & VE_FAULT_INVALID_SENSOR)) ? "true" : "false",
        current_faults);
}

/* Small fixed-size operational metrics, without sensitive identifiers. */
static void build_metrics(char *body, size_t cap)
{
    snprintf(body, cap,
        "{\"uptime_seconds\":%ld,\"memory_available_kb\":%ld,"
        "\"load_average_1m\":%.2f,\"fault_mask\":%u,"
        "\"config_valid\":%s,\"ready\":%s,"
        "\"event_transitions_total\":%u}",
        current_uptime, memory_kb("MemAvailable:"), proc_number("/proc/loadavg"),
        current_faults, config_valid ? "true" : "false",
        service_ready() ? "true" : "false", event_total);
}

static void build_events(char *body, size_t cap)
{
    /* Return the newest complete events that fit. Never truncate a JSON object.
       With 32 events, the response may exceed BODY_CAP on small devices. */
    const char *prefix = "{\"source\":\"simulation\",\"count\":";
    const char *middle = ",\"events\":[";
    unsigned count = event_total < EVENT_CAP ? event_total : EVENT_CAP;
    size_t used = strlen(prefix) + 20 + strlen(middle) + 3;
    unsigned included = 0;
    unsigned start = event_total - count;
    /* Walk backwards so the newest events take priority. */
    for (unsigned i = 0; i < count; ++i) {
        unsigned index = (event_total - 1 - i) % EVENT_CAP;
        size_t length = strlen(history[index]);
        if (used + length + 1 > cap) break;
        used += length + 1;
        included++;
    }
    int n = snprintf(body, cap, "%s%u%s", prefix, included, middle);
    if (n < 0 || (size_t)n >= cap) { if (cap) body[0] = 0; return; }
    used = (size_t)n;
    start = event_total - included;
    for (unsigned i = 0; i < included; ++i) {
        unsigned index = (start + i) % EVENT_CAP;
        n = snprintf(body + used, cap - used, "%s%s", i ? "," : "", history[index]);
        if (n < 0 || (size_t)n >= cap - used) break;
        used += (size_t)n;
    }
    (void)snprintf(body + used, cap - used, "]}");
}

static int send_all(int fd, const char *s, size_t len)
{
    while (len) {
        ssize_t n = send(fd, s, len, 0);
        if (n <= 0) return -1;
        s += n; len -= (size_t)n;
    }
    return 0;
}

static void respond(int fd, int code, const char *body)
{
    const char *reason = code == 200 ? "OK" : code == 404 ? "Not Found" :
                         code == 405 ? "Method Not Allowed" :
                         code == 503 ? "Service Unavailable" : "Bad Request";
    char header[768];
    int n = snprintf(header, sizeof(header),
        "HTTP/1.1 %d %s\r\nContent-Type: application/json\r\n"
        "Content-Length: %zu\r\nCache-Control: no-store\r\nConnection: close\r\n\r\n",
        code, reason, strlen(body));
    if (n > 0 && (size_t)n < sizeof(header) && send_all(fd, header, (size_t)n) == 0)
        (void)send_all(fd, body, strlen(body));
}

static void serve_dashboard(int fd)
{
    FILE *f = fopen(VE_DASHBOARD_FILE, "rb");
    if (!f) { respond(fd, 404, "{\"error\":\"dashboard_not_found\"}"); return; }
    if (fseek(f, 0, SEEK_END) != 0) { fclose(f); return; }
    long length = ftell(f);
    if (length < 0 || length > 131072 || fseek(f, 0, SEEK_SET) != 0) { fclose(f); return; }
    char header[768];
    int n = snprintf(header, sizeof(header),
        "HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\n"
        "X-Content-Type-Options: nosniff\r\n"
        "Content-Security-Policy: default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; form-action 'none'\r\n"
        "Cache-Control: no-store\r\nContent-Length: %ld\r\nConnection: close\r\n\r\n", length);
    if (n <= 0 || (size_t)n >= sizeof(header) || send_all(fd, header, (size_t)n) != 0) { fclose(f); return; }
    char buf[4096];
    size_t count;
    while ((count = fread(buf, 1, sizeof(buf), f)) > 0)
        if (send_all(fd, buf, count) != 0) break;
    fclose(f);
}

/* Opt-in HTTP Basic credential. This protects a local control surface against
 * accidental browsing, but Basic is NOT confidential without a TLS tunnel.
 * File contains only the Base64 encoding of 'username:secret', mode 0600.
 */
#define VE_BASIC_CAP 512
static char expected_basic[VE_BASIC_CAP];
static int auth_enabled;

static int secure_equal(const char *a, const char *b)
{
    size_t alen = strlen(a), blen = strlen(b);
    size_t mismatch = alen ^ blen;
    for (size_t i = 0; i < alen; ++i) {
        unsigned char bv = i < blen ? (unsigned char)b[i] : 0;
        mismatch |= (unsigned char)a[i] ^ bv;
    }
    return mismatch == 0;
}

static int load_auth(void)
{
    const char *path = getenv("VE_AUTH_FILE");
    if (!path || !*path) return 0;
    struct stat st;
    if (stat(path, &st) != 0 || !S_ISREG(st.st_mode) ||
        (st.st_mode & 077) || st.st_size < 24 || st.st_size >= VE_BASIC_CAP)
        return -1;
    FILE *f = fopen(path, "r");
    if (!f) return -1;
    char buf[VE_BASIC_CAP] = {0};
    if (!fgets(buf, sizeof(buf), f)) { fclose(f); return -1; }
    int next = fgetc(f);
    fclose(f);
    if (next != EOF) return -1;
    buf[strcspn(buf, "\r\n")] = '\0';
    size_t len = strlen(buf);
    if (len < 24 || len > 340 || len % 4 != 0) return -1;
    for (size_t i = 0; i < len; ++i) {
        char c = buf[i];
        if (!(c >= 'A' && c <= 'Z') && !(c >= 'a' && c <= 'z') &&
            !(c >= '0' && c <= '9') && c != '+' && c != '/' && c != '=')
            return -1;
        if (c == '=' && i < len - 2) return -1;
    }
    memcpy(expected_basic, buf, len + 1);
    auth_enabled = 1;
    return 0;
}

static void auth_denied(int fd)
{
    const char *body = "{\"error\":\"unauthorized\"}";
    char header[512];
    int n = snprintf(header, sizeof(header),
        "HTTP/1.1 401 Unauthorized\r\n"
        "WWW-Authenticate: Basic realm=\"VirtualEdge OS\", charset=\"UTF-8\"\r\n"
        "Content-Type: application/json\r\n"
        "Cache-Control: no-store\r\n"
        "Content-Length: %zu\r\nConnection: close\r\n\r\n", strlen(body));
    if (n > 0 && (size_t)n < sizeof(header) && send_all(fd, header, (size_t)n) == 0)
        (void)send_all(fd, body, strlen(body));
}

static int request_authorized(const char *headers)
{
    if (!auth_enabled) return 1;
    int count = 0, correct = 0;
    const char *line = headers;
    while (*line) {
        const char *end = strstr(line, "\r\n");
        if (!end || end == line) break;
        const char *prefix = "Authorization:";
        size_t prefixlen = strlen(prefix);
        if ((size_t)(end - line) >= prefixlen &&
            strncasecmp(line, prefix, prefixlen) == 0) {
            ++count;
            const char *value = line + prefixlen;
            while (value < end && (*value == ' ' || *value == '\t')) ++value;
            const char *basic = "Basic ";
            if (end - value > (ptrdiff_t)strlen(basic) &&
                strncmp(value, basic, strlen(basic)) == 0) {
                value += strlen(basic);
                size_t got = (size_t)(end - value);
                if (got < VE_BASIC_CAP) {
                    char candidate[VE_BASIC_CAP];
                    memcpy(candidate, value, got);
                    candidate[got] = '\0';
                    correct = secure_equal(candidate, expected_basic);
                }
            }
        }
        line = end + 2;
    }
    return count == 1 && correct;
}

static void handle_client(int fd)
{
    char request[16384] = {0};
    char body[BODY_CAP];
    struct timeval timeout = {2, 0};
    (void)setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout));
    (void)setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &timeout, sizeof(timeout));
    /* Read complete HTTP headers, capped at 16 KiB; sockets have a 2s timeout.
       Browsers may split a request across multiple TCP reads. */
    size_t used = 0;
    while (used < sizeof(request) - 1 && !strstr(request, "\r\n\r\n")) {
        ssize_t n = recv(fd, request + used, sizeof(request) - 1 - used, 0);
        if (n <= 0) break;
        used += (size_t)n;
        request[used] = '\0';
        /* Bare LF in the request line is malformed; reject immediately,
           rather than waiting for a client that will send no more bytes. */
        char *first_lf = strchr(request, '\n');
        if (first_lf && (first_lf == request || first_lf[-1] != '\r')) break;
    }
    if (!strstr(request, "\r\n\r\n")) {
        respond(fd, 400, "{\"error\":\"bad_request\"}"); return;
    }
    /* Reject malformed request lines and non-origin-form paths. */
    char *line_end = strstr(request, "\r\n");
    if (!line_end || line_end - request > 255) {
        respond(fd, 400, "{\"error\":\"bad_request\"}"); return;
    }
    *line_end = '\0';
    char method[16], path[128], version[16], extra;
    if (sscanf(request, "%15s %127s %15s %c", method, path, version, &extra) != 3 ||
        (strcmp(version, "HTTP/1.1") != 0 && strcmp(version, "HTTP/1.0") != 0) ||
        path[0] != '/' || strchr(path, '?') || strchr(path, '#')) {
        respond(fd, 400, "{\"error\":\"bad_request\"}"); return;
    }
    if (strcmp(method, "GET") != 0) {
        respond(fd, 405, "{\"error\":\"method_not_allowed\"}"); return;
    }
    if (!request_authorized(line_end + 2)) {
        auth_denied(fd); return;
    }
    if (strcmp(path, "/") == 0 || strcmp(path, "/dashboard") == 0) {
        serve_dashboard(fd);
    } else if (strcmp(path, "/health") == 0) {
        respond(fd, 200, "{\"status\":\"ok\",\"service\":\"virtualedge-api\"}");
    } else if (strcmp(path, "/ready") == 0) {
        build_readiness(body, sizeof(body));
        respond(fd, service_ready() ? 200 : 503, body);
    } else if (strcmp(path, "/api/v1/metrics") == 0) {
        build_metrics(body, sizeof(body)); respond(fd, 200, body);
    } else if (strcmp(path, "/api/v1/telemetry") == 0) {
        build_telemetry(body, sizeof(body)); respond(fd, 200, body);
    } else if (strcmp(path, "/api/v1/diagnostics") == 0) {
        build_diagnostics(body, sizeof(body)); respond(fd, 200, body);
    } else if (strcmp(path, "/api/v1/config") == 0) {
        build_config(body, sizeof(body)); respond(fd, 200, body);
    } else if (strcmp(path, "/api/v1/device") == 0) {
        build_device(body, sizeof(body)); respond(fd, 200, body);
    } else if (strcmp(path, "/api/v1/events") == 0) {
        build_events(body, sizeof(body)); respond(fd, 200, body);
    } else {
        respond(fd, 404, "{\"error\":\"not_found\"}");
    }
}

int main(void)
{
    struct sigaction action = {0};
    action.sa_handler = on_signal;
    sigemptyset(&action.sa_mask);
    (void)sigaction(SIGTERM, &action, NULL);
    (void)sigaction(SIGINT, &action, NULL);
    (void)sigaction(SIGHUP, &action, NULL);
    signal(SIGPIPE, SIG_IGN);
    if (load_auth() != 0) {
        fprintf(stderr, "VirtualEdge: invalid or insecure authentication file; refusing to start\n");
        return 1;
    }
    load_config();
    sample();

    int server = socket(AF_INET, SOCK_STREAM, 0);
    if (server < 0) { perror("socket"); return 1; }
    int yes = 1;
    (void)setsockopt(server, SOL_SOCKET, SO_REUSEADDR, &yes, sizeof(yes));
    struct sockaddr_in addr = {0};
    addr.sin_family = AF_INET;
    addr.sin_port = htons(VE_PORT);
    /* Explicit opt-in for QEMU user-mode port forwarding; default stays loopback. */
    const char *allow_external = getenv("VE_LISTEN_ANY");
    addr.sin_addr.s_addr = htonl(allow_external && strcmp(allow_external, "1") == 0 ? INADDR_ANY : INADDR_LOOPBACK);
    if (bind(server, (struct sockaddr *)&addr, sizeof(addr)) < 0 || listen(server, 8) < 0) {
        perror("bind/listen"); close(server); return 1;
    }
    printf("VirtualEdge API listening on 127.0.0.1:%d\n", VE_PORT);
    fflush(stdout);
    time_t last_sample = time(NULL);
    while (running) {
        struct pollfd pfd = {server, POLLIN, 0};
        int ready = poll(&pfd, 1, 250);
        if (ready > 0 && (pfd.revents & POLLIN)) {
            int client = accept(server, NULL, NULL);
            if (client >= 0) { handle_client(client); close(client); }
        } else if (ready < 0 && errno != EINTR) {
            perror("poll"); break;
        }
        if (config_reload_requested) {
            config_reload_requested = 0;
            load_config();
            sample();
        }
        time_t now = time(NULL);
        if (now != last_sample) { sample(); last_sample = now; }
    }
    close(server);
    return 0;
}
