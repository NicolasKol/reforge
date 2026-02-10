#include "common.h"

/* Module C: reduction-style processing */

static int validate(int x) {
    return x != 0;
}

static int process(int x) {
    /* Absolute value + 1 */
    return (x < 0 ? -x : x) + 1;
}

static void report(const char *tag, int val) {
    printf("[C:%s] %d\n", tag, val);
}

static int reduce_min(const int *data, int n) {
    if (n == 0) return 0;
    int mn = data[0];
    for (int i = 1; i < n; i++) {
        if (validate(data[i]) && data[i] < mn)
            mn = data[i];
    }
    return mn;
}

static int reduce_max(const int *data, int n) {
    if (n == 0) return 0;
    int mx = data[0];
    for (int i = 1; i < n; i++) {
        if (validate(data[i]) && data[i] > mx)
            mx = data[i];
    }
    return mx;
}

void run_module_c(int *data, int n) {
    printf("--- Module C (reduction) ---\n");
    int mn = reduce_min(data, n);
    int mx = reduce_max(data, n);
    report("min", process(mn));
    report("max", process(mx));
    report("range", mx - mn);
}
