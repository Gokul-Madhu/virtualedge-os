#include <assert.h>
#include <math.h>
#include <stdio.h>

#include "../services/telemetry/diagnostics.h"

int main(void)
{
    ve_thresholds limits = {
        .max_temperature_c = 35.0,
        .max_vibration_g = 0.30,
        .min_voltage_v = 3.00
    };

    ve_sensor_data sensor = {25.0, 0.10, 3.30};

    assert(ve_evaluate(sensor, limits) == VE_FAULT_NONE);
    puts("PASS: Normal readings");

    sensor.temperature_c = 40.0;
    assert(ve_evaluate(sensor, limits) == VE_FAULT_OVERTEMP);
    puts("PASS: Overtemperature detected");

    sensor = (ve_sensor_data){25.0, 0.50, 3.30};
    assert(ve_evaluate(sensor, limits) == VE_FAULT_VIBRATION);
    puts("PASS: Excessive vibration detected");

    sensor = (ve_sensor_data){25.0, 0.10, 2.80};
    assert(ve_evaluate(sensor, limits) == VE_FAULT_UNDERVOLTAGE);
    puts("PASS: Undervoltage detected");

    sensor = (ve_sensor_data){40.0, 0.50, 2.80};
    assert(ve_evaluate(sensor, limits) ==
           (VE_FAULT_OVERTEMP |
            VE_FAULT_VIBRATION |
            VE_FAULT_UNDERVOLTAGE));
    puts("PASS: Multiple simultaneous faults");

    sensor = (ve_sensor_data){NAN, 0.10, 3.30};
    assert(ve_evaluate(sensor, limits) == VE_FAULT_INVALID_SENSOR);
    puts("PASS: Invalid sensor data rejected");

    puts("All VirtualEdge diagnostics tests passed.");
    return 0;
}
