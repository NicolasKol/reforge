#include "compute.h"

void bubble_sort(int *arr, int n) {
    for (int i = 0; i < n - 1; i++) {
        int swapped = 0;
        for (int j = 0; j < n - 1 - i; j++) {
            if (arr[j] > arr[j + 1]) {
                int tmp = arr[j];
                arr[j] = arr[j + 1];
                arr[j + 1] = tmp;
                swapped = 1;
            }
        }
        if (!swapped) break;
    }
}

void insertion_sort(int *arr, int n) {
    for (int i = 1; i < n; i++) {
        int key = arr[i];
        int j = i - 1;
        while (j >= 0 && arr[j] > key) {
            arr[j + 1] = arr[j];
            j--;
        }
        arr[j + 1] = key;
    }
}

void selection_sort(int *arr, int n) {
    for (int i = 0; i < n - 1; i++) {
        int mn = i;
        for (int j = i + 1; j < n; j++) {
            if (arr[j] < arr[mn])
                mn = j;
        }
        if (mn != i) {
            int tmp = arr[i];
            arr[i] = arr[mn];
            arr[mn] = tmp;
        }
    }
}

int is_sorted(const int *arr, int n) {
    for (int i = 1; i < n; i++) {
        if (arr[i] < arr[i - 1])
            return 0;
    }
    return 1;
}

void reverse(int *arr, int n) {
    for (int lo = 0, hi = n - 1; lo < hi; lo++, hi--) {
        int tmp = arr[lo];
        arr[lo] = arr[hi];
        arr[hi] = tmp;
    }
}

void rotate_left(int *arr, int n, int k) {
    if (n <= 1) return;
    k = k % n;
    if (k < 0) k += n;
    /* Three-reverse rotation */
    reverse(arr, k);
    reverse(arr + k, n - k);
    reverse(arr, n);
}
