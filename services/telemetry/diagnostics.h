#ifndef VIRTUALEDGE_DIAGNOSTICS_H
#define VIRTUALEDGE_DIAGNOSTICS_H

#include <stdbool.h>
#include <math.h>

typedef struct {
    double temperature_c;
    double vibration_g;
    double voltage_v;
} ve_sensor_data;

typedef struct {
    double max_temperature_c;
    double max_vibration_g;
    double min_voltage_v;
} ve_thresholds;

enum {
    VE_FAULT_NONE = 0,
    VE_FAULT_OVERTEMP = 1,
    VE_FAULT_VIBRATION = 2,
    VE_FAULT_UNDERVOLTAGE = 4,
    VE_FAULT_INVALID_SENSOR = 8
};

static inline unsigned ve_evaluate(
    ve_sensor_data sensor,
    ve_thresholds limits)
{
    if (!isfinite(sensor.temperature_c) ||
        !isfinite(sensor.vibration_g) ||
        !isfinite(sensor.voltage_v) ||
        sensor.vibration_g < 0 ||
        sensor.voltage_v < 0 ||
        !isfinite(limits.max_temperature_c) ||
        !isfinite(limits.max_vibration_g) ||
        !isfinite(limits.min_voltage_v) ||
        limits.max_vibration_g < 0 ||
        limits.min_voltage_v < 0) {
        return VE_FAULT_INVALID_SENSOR;
    }

    unsigned faults = VE_FAULT_NONE;

    if (sensor.temperature_c > limits.max_temperature_c)
        faults |= VE_FAULT_OVERTEMP;

    if (sensor.vibration_g > limits.max_vibration_g)
        faults |= VE_FAULT_VIBRATION;

    if (sensor.voltage_v < limits.min_voltage_v)
        faults |= VE_FAULT_UNDERVOLTAGE;

    return faults;
}

#endif
