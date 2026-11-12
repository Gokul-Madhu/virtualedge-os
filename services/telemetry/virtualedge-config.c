#define _POSIX_C_SOURCE 200809L
/* Local-only privileged configuration management. No HTTP write endpoint. */
#include <errno.h>
#include <fcntl.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

#ifndef VE_CONFIG_FILE
#define VE_CONFIG_FILE "/etc/virtualedge/diagnostics.conf"
#endif

static const char *keys[] = {
    "max_temperature_c", "max_vibration_g", "min_voltage_v"
};
static const double defaults[] = {35.0, 0.30, 3.00};
static const double minimum[] = {-50.0, 0.0, 0.0};
static const double maximum[] = {150.0, 20.0, 24.0};

static int parse_number(const char *str, int index, double *out)
{
    char *end = NULL;
    errno = 0;
    double value = strtod(str, &end);
    if (errno || end == str || *end || !isfinite(value) ||
        value < minimum[index] || value > maximum[index]) return -1;
    *out = value;
    return 0;
}

static int read_config(double v[3])
{
    for (int i = 0; i < 3; ++i) v[i] = defaults[i];
    FILE *f = fopen(VE_CONFIG_FILE, "r");
    if (!f) return errno == ENOENT ? 0 : -1;
    char line[192];
    unsigned seen = 0;
    int rc = 0;
    while (fgets(line, sizeof(line), f)) {
        if (line[0] == '#' || line[0] == '\n') continue;
        char key[80], number[80], trailing;
        if (sscanf(line, " %79[^=]=%79s %c", key, number, &trailing) != 2) { rc = -1; break; }
        int index = -1;
        for (int i = 0; i < 3; ++i) if (strcmp(key, keys[i]) == 0) index = i;
        if (index < 0 || (seen & (1u << index)) || parse_number(number, index, &v[index])) {
            rc = -1; break;
        }
        seen |= 1u << index;
    }
    if (ferror(f)) rc = -1;
    fclose(f);
    if (seen != 7 && seen != 0) rc = -1;
    return rc;
}

static int save_config(const double v[3])
{
    char temp[sizeof(VE_CONFIG_FILE) + 24];
    if (snprintf(temp, sizeof(temp), "%s.tmp.XXXXXX", VE_CONFIG_FILE) >= (int)sizeof(temp)) return -1;
    int fd = mkstemp(temp);
    if (fd < 0) return -1;
    FILE *f = fdopen(fd, "w");
    if (!f) { close(fd); unlink(temp); return -1; }
    int ok = fchmod(fd, 0644) == 0 &&
        fprintf(f, "max_temperature_c=%.6g\nmax_vibration_g=%.6g\nmin_voltage_v=%.6g\n",
                v[0], v[1], v[2]) > 0 &&
        fflush(f) == 0 && fsync(fd) == 0;
    if (fclose(f) != 0) ok = 0;
    if (ok) ok = rename(temp, VE_CONFIG_FILE) == 0;
    if (!ok) { unlink(temp); return -1; }
    return 0;
}

int main(int argc, char **argv)
{
    if (argc < 2) {
        fprintf(stderr, "Usage: virtualedge-config show | validate | set KEY VALUE\n");
        return 2;
    }
    double v[3];
    if (read_config(v) != 0) {
        fprintf(stderr, "Invalid existing configuration; refusing to overwrite\n");
        return 1;
    }
    if (argc == 2 && strcmp(argv[1], "validate") == 0) {
        puts("Configuration valid"); return 0;
    }
    if (argc == 2 && strcmp(argv[1], "show") == 0) {
        for (int i = 0; i < 3; ++i) printf("%s=%.6g\n", keys[i], v[i]);
        return 0;
    }
    if (argc == 4 && strcmp(argv[1], "set") == 0) {
        int index = -1;
        for (int i = 0; i < 3; ++i) if (strcmp(argv[2], keys[i]) == 0) index = i;
        if (index < 0 || parse_number(argv[3], index, &v[index])) {
            fprintf(stderr, "Unknown setting or out-of-range value\n"); return 2;
        }
        if (save_config(v) != 0) { perror("save configuration"); return 1; }
        puts("Configuration saved atomically. Restart API or send SIGHUP to apply.");
        return 0;
    }
    fprintf(stderr, "Usage: virtualedge-config show | validate | set KEY VALUE\n");
    return 2;
}
