#include "format.h"

int main(void) {
    printf("=== t09_string_format ===\n\n");

    int data[] = {42, -7, 100, 0, 13, 256};
    int n = sizeof(data) / sizeof(data[0]);
    char buf[FMT_BUF_SIZE];

    /* Test all format styles on the same array */
    printf("--- array formatting ---\n");
    for (int s = FMT_PLAIN; s <= FMT_TABLE_ROW; s++) {
        format_int_array(buf, sizeof(buf), data, n, (format_style_t)s);
        printf("  %-10s: %s\n", style_name((format_style_t)s), buf);
    }

    /* Key-value formatting */
    printf("\n--- key-value formatting ---\n");
    for (int s = FMT_PLAIN; s <= FMT_TABLE_ROW; s++) {
        format_key_value(buf, sizeof(buf), "compiler", "gcc-12.2",
                         (format_style_t)s);
        printf("  %-10s: %s\n", style_name((format_style_t)s), buf);
    }

    /* Record formatting */
    printf("\n--- record formatting ---\n");
    const char *names[] = {"Alice", "Bob", "Charlie"};
    int ids[]           = {1, 2, 3};
    int scores[]        = {95, 87, 72};

    for (int s = FMT_PLAIN; s <= FMT_TABLE_ROW; s++) {
        printf("  [%s]\n", style_name((format_style_t)s));
        for (int i = 0; i < 3; i++) {
            format_record(buf, sizeof(buf), names[i], ids[i], scores[i],
                          (format_style_t)s);
            printf("    %s\n", buf);
        }
    }

    /* Logger tests */
    printf("\n--- logger ---\n");
    log_init(LOG_DEBUG);
    log_msg(LOG_DEBUG, "starting test run with %d items", n);
    log_msg(LOG_INFO,  "processing array of %d elements", n);
    log_array(LOG_INFO, "data", data, n);
    log_msg(LOG_WARN,  "value at index 3 is zero");
    log_msg(LOG_ERROR, "hypothetical failure in module X");

    printf("\nLog counts: DBG=%d INF=%d WRN=%d ERR=%d\n",
           log_get_count(LOG_DEBUG), log_get_count(LOG_INFO),
           log_get_count(LOG_WARN),  log_get_count(LOG_ERROR));

    /* Test with higher min level */
    printf("\n--- logger (min=WARN) ---\n");
    log_init(LOG_WARN);
    log_msg(LOG_DEBUG, "should not appear");
    log_msg(LOG_INFO,  "should not appear");
    log_msg(LOG_WARN,  "this should appear");
    log_msg(LOG_ERROR, "this too");

    printf("\nDone.\n");
    return 0;
}
