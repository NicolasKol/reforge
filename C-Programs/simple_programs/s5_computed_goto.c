// s5_computed_goto.c
#include <stdio.h>

int weird(int x) {
    static void* tbl[] = { &&L0, &&L1, &&L2, &&L3 };
    goto *tbl[(unsigned)x & 3];

L0: x += 1; goto END;
L1: x *= 3; goto END;
L2: x -= 7; goto END;
L3: x ^= 0x1234; goto END;

END:
    return x;
}

int main(void) {
    printf("%d\n", weird(9));
    return 0;
}
