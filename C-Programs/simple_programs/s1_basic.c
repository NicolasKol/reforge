// s1_basic.c
#include <stdio.h>

int add(int a, int b) { return a + b; }
int sub(int a, int b) { return a - b; }

static int mul(int a, int b) { return a * b; }

int clamp(int x, int lo, int hi) {
    if (x < lo) return lo;
    if (x > hi) return hi;
    return x;
}

int main(void) {
    int a = 7, b = 3;
    int x = add(a, b);
    int y = mul(x, sub(a, b));
    printf("%d\n", clamp(y, 0, 50));
    return 0;
}
