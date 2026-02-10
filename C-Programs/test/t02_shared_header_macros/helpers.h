#ifndef HELPERS_H
#define HELPERS_H

#include <stdio.h>

/* --- Macros (no DWARF name) --- */
#define ABS(x)      ((x) < 0 ? -(x) : (x))
#define MAX2(a, b)  ((a) > (b) ? (a) : (b))
#define MIN2(a, b)  ((a) < (b) ? (a) : (b))
#define SWAP(a, b)  do { int _t = (a); (a) = (b); (b) = _t; } while(0)
#define ARRAY_LEN(a) ((int)(sizeof(a) / sizeof((a)[0])))

/* --- Static inline helpers (appear in DWARF per TU) --- */
static inline int safe_div(int a, int b) {
    if (b == 0) return 0;
    return a / b;
}

static inline int safe_mod(int a, int b) {
    if (b == 0) return 0;
    return a % b;
}

static inline int is_even(int x) {
    return (x & 1) == 0;
}

static inline int square(int x) {
    return x * x;
}

static inline void print_sep(const char *label) {
    printf("--- %s ---\n", label);
}

/* Forward declarations */
void run_arith_tests(void);
void run_sort_tests(void);

#endif /* HELPERS_H */
