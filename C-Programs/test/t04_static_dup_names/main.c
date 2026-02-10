#include "common.h"

int main(void) {
    int data[] = {42, 7, 100, 0, -3, 18, 256, 55, 12, 999};
    int n = sizeof(data) / sizeof(data[0]);

    printf("=== t04_static_dup_names ===\n");
    printf("Input: %d elements\n\n", n);

    run_module_a(data, n);
    printf("\n");
    run_module_b(data, n);
    printf("\n");
    run_module_c(data, n);

    printf("\nDone.\n");
    return 0;
}
