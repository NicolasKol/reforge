#include "compute.h"

static void print_arr(const int *arr, int n, const char *label) {
    printf("%s: [ ", label);
    for (int i = 0; i < n && i < 10; i++)
        printf("%d ", arr[i]);
    if (n > 10) printf("...");
    printf("] sorted=%d\n", is_sorted(arr, n));
}

int main(void) {
    printf("=== t08_loop_heavy ===\n\n");

    /* --- Matrix operations --- */
    int A[MAT_SIZE][MAT_SIZE], B[MAT_SIZE][MAT_SIZE], C[MAT_SIZE][MAT_SIZE];

    mat_fill_pattern(A, 7);
    mat_fill_pattern(B, 13);
    mat_print(A, "A");
    mat_print(B, "B");

    mat_multiply(A, B, C);
    mat_print(C, "A*B");
    printf("trace(A*B) = %ld\n", mat_trace(C));
    printf("sum(A*B)   = %ld\n\n", mat_sum(C));

    mat_transpose(C);
    mat_print(C, "(A*B)^T");

    /* --- Sorting --- */
    printf("\n--- sorting ---\n");
    int d1[] = {34, -7, 12, 0, 55, -23, 8, 91, 3, -15, 44, 67, 2, 78, -1, 33};
    int n1 = sizeof(d1) / sizeof(d1[0]);

    int buf[16];

    memcpy(buf, d1, sizeof(d1));
    bubble_sort(buf, n1);
    print_arr(buf, n1, "bubble   ");

    memcpy(buf, d1, sizeof(d1));
    insertion_sort(buf, n1);
    print_arr(buf, n1, "insertion");

    memcpy(buf, d1, sizeof(d1));
    selection_sort(buf, n1);
    print_arr(buf, n1, "selection");

    /* --- Rotate --- */
    printf("\n--- rotate ---\n");
    int d2[] = {1, 2, 3, 4, 5, 6, 7, 8};
    print_arr(d2, 8, "before  ");
    rotate_left(d2, 8, 3);
    print_arr(d2, 8, "rot-L 3 ");
    rotate_left(d2, 8, -2);
    print_arr(d2, 8, "rot-L -2");

    printf("\nDone.\n");
    return 0;
}
