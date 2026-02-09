// s4_switch.c
#include <stdio.h>

int step(int x, int k) {
    switch (k & 3) {
        case 0: return x + 11;
        case 1: return x * 3;
        case 2: return x - 7;
        default: return x ^ 0x5a;
    }
}

int transform(int x) {
    int v = x;
    for (int i = 0; i < 20; i++) v = step(v, i);
    return v;
}

int main(void) {
    printf("%d\n", transform(9));
    return 0;
}
