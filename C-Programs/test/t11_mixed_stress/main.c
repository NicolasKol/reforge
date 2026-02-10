#include "mixed.h"

int main(void) {
    int workspace[] = {
        15, -3, 42, 0, 7, -10, 33, 8, -1, 100,
        5,  22, -7, 0, 19, 64, -25, 11, 3,  50
    };
    int n = sizeof(workspace) / sizeof(workspace[0]);

    print_divider("t11_mixed_stress");
    print_array("initial", workspace, n);

    /* Compute summary before plugins */
    int total = 0, mn = workspace[0], mx = workspace[0];
    for (int i = 0; i < n; i++) {
        total += workspace[i];
        if (workspace[i] < mn) mn = workspace[i];
        if (workspace[i] > mx) mx = workspace[i];
    }
    print_summary("before", total, n, mn, mx);

    /* Initialize engine and register plugins */
    engine_init();
    register_all_plugins();
    printf("\n  Registered %d plugins\n", engine_count());

    /* Run all plugins (modifies workspace via engine preprocessing) */
    print_divider("running plugins");
    engine_run_all(workspace, n);

    /* Post-plugin state */
    print_divider("after plugins");
    print_array("workspace", workspace, n);

    total = 0; mn = workspace[0]; mx = workspace[0];
    for (int i = 0; i < n; i++) {
        total += workspace[i];
        if (workspace[i] < mn) mn = workspace[i];
        if (workspace[i] > mx) mx = workspace[i];
    }
    print_summary("after", total, n, mn, mx);

    printf("\nDone.\n");
    return 0;
}
