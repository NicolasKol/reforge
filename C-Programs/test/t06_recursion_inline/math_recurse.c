#include "recurse.h"

/* Classic recursive fibonacci — exponential, not tail-callable */
int fibonacci(int n) {
    if (n <= 1) return clamp(n, 0, 1);  /* inlineable leaf */
    return fibonacci(n - 1) + fibonacci(n - 2);
}

/* Euclidean GCD — tail-recursive candidate at O2+ */
int gcd(int a, int b) {
    a = abs_val(a);
    b = abs_val(b);
    if (b == 0) return a;
    return gcd(b, a % b);
}

/* Integer exponentiation by squaring — partially tail-recursive */
int power(int base, int exp) {
    if (exp == 0) return 1;
    if (exp == 1) return base;
    if (exp % 2 == 0) {
        int half = power(base, exp / 2);
        return half * half;
    }
    return base * power(base, exp - 1);
}

/* Ackermann — hyper-recursive, grows stack fast.
 * Capped input to prevent stack overflow. */
int ackermann(int m, int n) {
    m = clamp(m, 0, 3);
    n = clamp(n, 0, 6);
    if (m == 0) return n + 1;
    if (n == 0) return ackermann(m - 1, 1);
    return ackermann(m - 1, ackermann(m, n - 1));
}
