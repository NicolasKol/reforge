#include "common.h"

/* Module A: accumulator-style processing */

static int validate(int x) {
    return x >= 0 && x < 1000;
}

static int process(int x) {
    /* Doubling */
    return x * 2;
}

static void report(const char *tag, int val) {
    printf("[A:%s] %d\n", tag, val);
}

static int accumulate(const int *data, int n) {
    int acc = 0;
    for (int i = 0; i < n; i++) {
        if (validate(data[i])) {
            acc += process(data[i]);
        }
    }
    return acc;
}

void run_module_a(int *data, int n) {
    printf("--- Module A (accumulator) ---\n");
    int result = accumulate(data, n);
    report("total", result);
}
