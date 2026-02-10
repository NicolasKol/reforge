#include "recurse.h"

/*
 * Binary heap stored as array:
 *   children of node i → 2*i+1, 2*i+2
 *
 * All recursive — forces deep call stacks at O0,
 * tail-call candidates at O2+.
 */

int tree_depth(const int *heap, int n, int idx) {
    if (idx >= n) return 0;
    int left  = tree_depth(heap, n, 2 * idx + 1);
    int right = tree_depth(heap, n, 2 * idx + 2);
    return 1 + max2(left, right);      /* inlineable leaf */
}

int tree_sum(const int *heap, int n, int idx) {
    if (idx >= n) return 0;
    int val = abs_val(heap[idx]);       /* inlineable leaf */
    return val + tree_sum(heap, n, 2 * idx + 1)
               + tree_sum(heap, n, 2 * idx + 2);
}

int tree_max(const int *heap, int n, int idx) {
    if (idx >= n) return 0;
    int left  = tree_max(heap, n, 2 * idx + 1);
    int right = tree_max(heap, n, 2 * idx + 2);
    int child_max = max2(left, right);  /* inlineable leaf */
    return max2(abs_val(heap[idx]), child_max);
}
