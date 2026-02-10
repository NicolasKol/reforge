#ifndef RECURSE_H
#define RECURSE_H

#include <stdio.h>

/* ---------- tiny leaf helpers (inline candidates) ---------- */

static inline int abs_val(int x) { return x < 0 ? -x : x; }
static inline int max2(int a, int b) { return a > b ? a : b; }
static inline int min2(int a, int b) { return a < b ? a : b; }
static inline int clamp(int x, int lo, int hi) {
    return x < lo ? lo : (x > hi ? hi : x);
}

/* tree_ops.c */
int tree_depth(const int *heap, int n, int idx);
int tree_sum(const int *heap, int n, int idx);
int tree_max(const int *heap, int n, int idx);

/* math_recurse.c */
int fibonacci(int n);
int gcd(int a, int b);
int power(int base, int exp);
int ackermann(int m, int n);

#endif /* RECURSE_H */
