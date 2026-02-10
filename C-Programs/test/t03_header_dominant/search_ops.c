#include "vector.h"

/* Thin wrapper — uses vec_* from header for searching */

static int linear_search(const Vec *v, int target) {
    return vec_find(v, target);
}

void run_search_tests(void) {
    Vec v;
    vec_init(&v);

    printf("=== Search Tests ===\n");

    /* Build data */
    for (int i = 0; i < 20; i++) {
        vec_push(&v, i * 3);
    }
    vec_print(&v, "Data");

    /* Search for values */
    int targets[] = {0, 15, 30, 42, 57, 99};
    int nt = sizeof(targets) / sizeof(targets[0]);
    for (int i = 0; i < nt; i++) {
        int idx = linear_search(&v, targets[i]);
        if (idx >= 0)
            printf("  Found %d at index %d\n", targets[i], idx);
        else
            printf("  %d not found\n", targets[i]);
    }

    /* Reverse and re-search */
    vec_reverse(&v);
    vec_print(&v, "Reversed");
    printf("  Find 15 in reversed: idx=%d\n", linear_search(&v, 15));

    vec_free(&v);
}
