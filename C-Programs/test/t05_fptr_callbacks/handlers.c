#include "dispatch.h"

/* ---------- operation callbacks ---------- */

int op_sum(const int *data, int n) {
    int s = 0;
    for (int i = 0; i < n; i++)
        s += data[i];
    return s;
}

int op_product(const int *data, int n) {
    if (n == 0) return 0;
    int p = 1;
    for (int i = 0; i < n; i++)
        p *= data[i];
    return p;
}

int op_max(const int *data, int n) {
    if (n == 0) return 0;
    int m = data[0];
    for (int i = 1; i < n; i++) {
        if (data[i] > m) m = data[i];
    }
    return m;
}

int op_count_positive(const int *data, int n) {
    int c = 0;
    for (int i = 0; i < n; i++) {
        if (data[i] > 0) c++;
    }
    return c;
}

/* ---------- transform callbacks ---------- */

void tx_double(int *data, int n) {
    for (int i = 0; i < n; i++)
        data[i] *= 2;
}

void tx_negate(int *data, int n) {
    for (int i = 0; i < n; i++)
        data[i] = -data[i];
}

void tx_clamp(int *data, int n) {
    for (int i = 0; i < n; i++) {
        if (data[i] < -100) data[i] = -100;
        if (data[i] >  100) data[i] =  100;
    }
}
