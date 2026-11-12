#ifndef VIRTUALEDGE_FAULT_INJECTION_H
#define VIRTUALEDGE_FAULT_INJECTION_H

#include <stdio.h>
#include <string.h>
#include "diagnostics.h"

#ifndef VE_FAULT_FILE
#define VE_FAULT_FILE "/run/virtualedge/fault-mode"
#endif

static inline void ve_apply_fault_injection(ve_sensor_data *sensor)
{
    char mode[32] = {0};

    FILE *file = fopen(VE_FAULT_FILE, "r");
    if (!file) return;

    if (!fgets(mode, sizeof(mode), file)) {
        fclose(file);
        return;
    }
    fclose(file);

    mode[strcspn(mode, "\r\n")] = '\0';

    if (strcmp(mode, "overtemp") == 0) {
        sensor->temperature_c = 45.0;
    } else if (strcmp(mode, "vibration") == 0) {
        sensor->vibration_g = 0.75;
    } else if (strcmp(mode, "undervoltage") == 0) {
        sensor->voltage_v = 2.70;
    } else if (strcmp(mode, "multiple") == 0) {
        sensor->temperature_c = 45.0;
        sensor->vibration_g = 0.75;
        sensor->voltage_v = 2.70;
    }
}

#endif
