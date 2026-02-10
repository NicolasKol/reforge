#include "common.h"

/* Module B: filter-style processing */

static int validate(int x) {
    return x > 10 && x % 2 == 0;
}

static int process(int x) {
    /* Squaring */
    return x * x;
}

static void report(const char *tag, int val) {
    printf("[B:%s] %d\n", tag, val);
}

static int count_valid(const int *data, int n) {
    int cnt = 0;
    for (int i = 0; i < n; i++) {
        if (validate(data[i]))
            cnt++;
    }
    return cnt;
}

void run_module_b(int *data, int n) {
    printf("--- Module B (filter) ---\n");
    int valid = count_valid(data, n);
    report("valid_count", valid);

    for (int i = 0; i < n; i++) {
        if (validate(data[i])) {
            int r = process(data[i]);
            report("squared", r);
        }
    }
}
