#include "common.h"

/* --- Array utilities (exported) --- */

int array_sum(const int *arr, int n) {
    int total = 0;
    for (int i = 0; i < n; i++) {
        total += arr[i];
    }
    return total;
}

int array_max(const int *arr, int n) {
    if (n <= 0) return 0;
    int mx = arr[0];
    for (int i = 1; i < n; i++) {
        if (arr[i] > mx) mx = arr[i];
    }
    return mx;
}

int array_min(const int *arr, int n) {
    if (n <= 0) return 0;
    int mn = arr[0];
    for (int i = 1; i < n; i++) {
        if (arr[i] < mn) mn = arr[i];
    }
    return mn;
}

void array_print(const int *arr, int n) {
    printf("[");
    for (int i = 0; i < n; i++) {
        printf("%d", arr[i]);
        if (i < n - 1) printf(", ");
    }
    printf("]\n");
}

/* Static helper — only visible in this TU */
static int array_range(const int *arr, int n) {
    return array_max(arr, n) - array_min(arr, n);
}
