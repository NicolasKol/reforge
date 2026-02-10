#include "dispatch.h"

int run_dispatch_table(const dispatch_entry_t *table, int count,
                       const int *data, int n) {
    int total = 0;
    for (int i = 0; i < count; i++) {
        int result = table[i].op(data, n);
        printf("  [dispatch] %-18s => %d\n", table[i].name, result);
        total += result;
    }
    return total;
}

void run_transform_chain(const transform_entry_t *chain, int count,
                         int *data, int n) {
    for (int i = 0; i < count; i++) {
        printf("  [transform] applying %-12s ... ", chain[i].name);
        chain[i].fn(data, n);
        /* print first few elements after transform */
        printf("[ ");
        for (int j = 0; j < n && j < 5; j++)
            printf("%d ", data[j]);
        if (n > 5) printf("...");
        printf("]\n");
    }
}
