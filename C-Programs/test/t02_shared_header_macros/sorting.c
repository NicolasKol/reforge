#include "helpers.h"

/* Also uses the same inline helpers — separate TU */

static void bubble_sort(int *arr, int n) {
    for (int i = 0; i < n - 1; i++) {
        for (int j = 0; j < n - 1 - i; j++) {
            if (arr[j] > arr[j + 1]) {
                SWAP(arr[j], arr[j + 1]);
            }
        }
    }
}

static void insertion_sort(int *arr, int n) {
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

static void print_array(const int *arr, int n) {
    for (int i = 0; i < n; i++) {
        printf("%d ", arr[i]);
    }
    printf("\n");
}

void run_sort_tests(void) {
    print_sep("Sorting");

    int a[] = {9, 4, 7, 1, 3, 8, 2, 6, 5};
    int n = ARRAY_LEN(a);
    int b[9];

    /* Copy and bubble sort */
    for (int i = 0; i < n; i++) b[i] = a[i];
    bubble_sort(b, n);
    printf("Bubble:    ");
    print_array(b, n);

    /* Copy and insertion sort */
    for (int i = 0; i < n; i++) b[i] = a[i];
    insertion_sort(b, n);
    printf("Insertion: ");
    print_array(b, n);

    /* Use safe_div from header */
    printf("Midpoint value: %d\n", b[safe_div(n, 2)]);
    printf("Square of max:  %d\n", square(b[n - 1]));
}
