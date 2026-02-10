#include "dispatch.h"
#include <string.h>

/* Build dispatch table at runtime — prevents constant-folding */
static dispatch_entry_t ops[] = {
    { "sum",            op_sum },
    { "product",        op_product },
    { "max",            op_max },
    { "count_positive", op_count_positive },
};

static transform_entry_t transforms[] = {
    { "double", tx_double },
    { "negate", tx_negate },
    { "clamp",  tx_clamp },
};

int main(void) {
    int data[] = {3, -1, 7, 0, 5, -4, 12, 2};
    int n = sizeof(data) / sizeof(data[0]);

    printf("=== t05_fptr_callbacks ===\n\n");

    /* Phase 1: dispatch table scan */
    printf("Phase 1: dispatch table\n");
    int grand = run_dispatch_table(ops, 4, data, n);
    printf("  grand total = %d\n\n", grand);

    /* Phase 2: transform chain (mutates a copy) */
    int copy[8];
    memcpy(copy, data, sizeof(data));

    printf("Phase 2: transform chain\n");
    run_transform_chain(transforms, 3, copy, n);

    /* Phase 3: re-dispatch on transformed data */
    printf("\nPhase 3: dispatch on transformed data\n");
    grand = run_dispatch_table(ops, 4, copy, n);
    printf("  grand total = %d\n", grand);

    printf("\nDone.\n");
    return 0;
}
