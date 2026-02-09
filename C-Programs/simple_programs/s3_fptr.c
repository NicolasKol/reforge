// s3_fptr.c
#include <stdio.h>

typedef int (*op_t)(int, int);

int add(int a, int b) { return a + b; }
int xor(int a, int b) { return a ^ b; }

int apply(op_t op, int a, int b) {
    return op(a, b);
}

int main(void) {
    printf("%d %d\n", apply(add, 5, 6), apply(xor, 5, 6));
    return 0;
}
