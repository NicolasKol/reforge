#include "helpers.h"

/* Uses macros and inline helpers extensively */

static int gcd(int a, int b) {
    a = ABS(a);
    b = ABS(b);
    while (b != 0) {
        int t = b;
        b = safe_mod(a, b);
        a = t;
    }
    return a;
}

static int lcm(int a, int b) {
    int g = gcd(a, b);
    return safe_div(ABS(a) * ABS(b), g);
}

static int sum_of_squares(const int *arr, int n) {
    int total = 0;
    for (int i = 0; i < n; i++) {
        total += square(arr[i]);
    }
    return total;
}

void run_arith_tests(void) {
    print_sep("Arithmetic");

    int vals[] = {12, 8, -3, 15, -7, 20};
    int n = ARRAY_LEN(vals);

    printf("GCD(12, 8) = %d\n", gcd(12, 8));
    printf("LCM(12, 8) = %d\n", lcm(12, 8));
    printf("Sum of squares = %d\n", sum_of_squares(vals, n));

    int mx = vals[0], mn = vals[0];
    for (int i = 1; i < n; i++) {
        mx = MAX2(mx, vals[i]);
        mn = MIN2(mn, vals[i]);
    }
    printf("Max = %d, Min = %d\n", mx, mn);

    for (int i = 0; i < n; i++) {
        printf("  %d is %s\n", vals[i], is_even(vals[i]) ? "even" : "odd");
    }
}
