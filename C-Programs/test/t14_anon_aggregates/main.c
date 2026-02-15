#include "types.h"

int main(void) {
    printf("=== t14_anon_aggregates ===\n\n");

    /* --- Test 1: message protocol with anonymous union variants --- */
    printf("--- Test 1: protocol messages ---\n");

    message_t m1, m2;
    message_init_net(&m1, 0xC0A80001, 0xC0A80002, 8080, 443);
    message_init_text(&m2, "Hello, anonymous world!");

    message_print(&m1);
    message_print(&m2);

    printf("  m1 valid: %d\n", message_validate(&m1));
    printf("  m2 valid: %d\n", message_validate(&m2));

    /* Invalid message */
    message_t m3;
    memset(&m3, 0, sizeof(m3));
    m3.type = 1;  /* net type but no addresses */
    printf("  m3 valid: %d\n", message_validate(&m3));

    /* --- Test 2: registry with bitfields + anonymous enum --- */
    printf("\n--- Test 2: entry registry ---\n");

    entry_t entries[5];
    entry_init(&entries[0], "alpha",   5, 1);
    entry_init(&entries[1], "beta",    3, 2);
    entry_init(&entries[2], "gamma",   1, 1);
    entry_init(&entries[3], "delta",   7, 3);
    entry_init(&entries[4], "epsilon", 0, 0);

    printf("  Before processing:\n");
    for (int i = 0; i < 5; i++)
        entry_print(&entries[i]);

    int total = registry_process(entries, 5);
    printf("  Total score: %d\n", total);

    printf("  After processing:\n");
    for (int i = 0; i < 5; i++)
        entry_print(&entries[i]);

    /* --- Test 3: doubly-nested anonymous structs --- */
    printf("\n--- Test 3: shapes (nested anon) ---\n");
    shape_demo();

    printf("\nDone.\n");
    return 0;
}
