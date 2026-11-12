/* Include implementation to exercise static bounded-serialization helpers. */
#define VE_EVENT_FILE "/tmp/virtualedge-host-event-capacity.log"
#define VE_LOG_MAX_BYTES 512
#define main virtualedge_server_main
#include "../services/telemetry/virtualedge-api.c"
#undef main
#include <assert.h>

int main(void)
{
    char json[BODY_CAP];
    (void)remove(VE_EVENT_FILE);
    (void)remove(VE_EVENT_FILE ".1");
    for (unsigned i = 0; i < EVENT_CAP + 15; ++i) {
        current_uptime = (long)i;
        record_event(i, i + 1);
    }
    build_events(json, sizeof(json));
    assert(strlen(json) < sizeof(json));
    assert(strstr(json, "\"events\":[{") != NULL);
    assert(strstr(json, "\"fault_mask\":47}") != NULL);
    assert(strlen(json) >= 2 && strcmp(json + strlen(json) - 2, "]}") == 0);
    /* Declared count must correspond to actual complete entries. */
    unsigned declared = 0;
    assert(sscanf(json, "{\"source\":\"simulation\",\"count\":%u", &declared) == 1);
    unsigned actual = 0;
    const char *cursor = json;
    while ((cursor = strstr(cursor, "\"fault_mask\":")) != NULL) {
        actual++;
        cursor += 13;
    }
    assert(actual == declared);
    assert(declared > 0 && declared <= EVENT_CAP);
    (void)remove(VE_EVENT_FILE);
    (void)remove(VE_EVENT_FILE ".1");
    puts("PASS: Bounded event JSON is complete, count accurate, latest event retained");
    return 0;
}
