#include "recurse.h"

int main(void) {
    printf("=== t06_recursion_inline ===\n\n");

    /* --- tree operations on a small heap --- */
    int heap[] = {10, -5, 20, 3, -8, 15, 7, 1, -2, 4, 0, 12, -6, 9, 11};
    int n = sizeof(heap) / sizeof(heap[0]);

    printf("Tree (heap, %d nodes):\n", n);
    printf("  depth = %d\n", tree_depth(heap, n, 0));
    printf("  sum   = %d\n", tree_sum(heap, n, 0));
    printf("  max   = %d\n\n", tree_max(heap, n, 0));

    /* --- math recursion --- */
    printf("Fibonacci:\n");
    for (int i = 0; i <= 12; i++)
        printf("  fib(%2d) = %d\n", i, fibonacci(i));

    printf("\nGCD:\n");
    printf("  gcd(48, 18) = %d\n", gcd(48, 18));
    printf("  gcd(100, 75) = %d\n", gcd(100, 75));
    printf("  gcd(-36, 24) = %d\n", gcd(-36, 24));

    printf("\nPower:\n");
    printf("  2^10 = %d\n", power(2, 10));
    printf("  3^5  = %d\n", power(3, 5));
    printf("  7^0  = %d\n", power(7, 0));

    printf("\nAckermann (capped):\n");
    printf("  A(0,0) = %d\n", ackermann(0, 0));
    printf("  A(1,2) = %d\n", ackermann(1, 2));
    printf("  A(2,3) = %d\n", ackermann(2, 3));
    printf("  A(3,4) = %d\n", ackermann(3, 4));

    printf("\nDone.\n");
    return 0;
}
