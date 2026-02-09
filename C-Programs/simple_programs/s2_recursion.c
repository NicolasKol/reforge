// s2_recursion.c
#include <stdio.h>

int fib(int n) {
    if (n <= 1) return n;
    return fib(n - 1) + fib(n - 2);
}

int sum_upto(int n) {
    int s = 0;
    for (int i = 1; i <= n; i++) s += i;
    return s;
}

int main(void) {
    printf("fib(8)=%d sum(10)=%d\n", fib(8), sum_upto(10));
    return 0;
}
