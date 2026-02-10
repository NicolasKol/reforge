#include "compute.h"

void mat_zero(int mat[MAT_SIZE][MAT_SIZE]) {
    for (int i = 0; i < MAT_SIZE; i++)
        for (int j = 0; j < MAT_SIZE; j++)
            mat[i][j] = 0;
}

void mat_identity(int mat[MAT_SIZE][MAT_SIZE]) {
    mat_zero(mat);
    for (int i = 0; i < MAT_SIZE; i++)
        mat[i][i] = 1;
}

void mat_fill_pattern(int mat[MAT_SIZE][MAT_SIZE], int seed) {
    for (int i = 0; i < MAT_SIZE; i++)
        for (int j = 0; j < MAT_SIZE; j++)
            mat[i][j] = ((i + 1) * (j + 1) + seed) % 97 - 48;
}

void mat_multiply(const int a[MAT_SIZE][MAT_SIZE],
                  const int b[MAT_SIZE][MAT_SIZE],
                  int       c[MAT_SIZE][MAT_SIZE]) {
    /* Classic O(n^3) — triple nested loop, vectorization target at O3 */
    for (int i = 0; i < MAT_SIZE; i++) {
        for (int j = 0; j < MAT_SIZE; j++) {
            int sum = 0;
            for (int k = 0; k < MAT_SIZE; k++)
                sum += a[i][k] * b[k][j];
            c[i][j] = sum;
        }
    }
}

void mat_transpose(int mat[MAT_SIZE][MAT_SIZE]) {
    for (int i = 0; i < MAT_SIZE; i++)
        for (int j = i + 1; j < MAT_SIZE; j++) {
            int tmp = mat[i][j];
            mat[i][j] = mat[j][i];
            mat[j][i] = tmp;
        }
}

long mat_trace(const int mat[MAT_SIZE][MAT_SIZE]) {
    long tr = 0;
    for (int i = 0; i < MAT_SIZE; i++)
        tr += mat[i][i];
    return tr;
}

long mat_sum(const int mat[MAT_SIZE][MAT_SIZE]) {
    long s = 0;
    for (int i = 0; i < MAT_SIZE; i++)
        for (int j = 0; j < MAT_SIZE; j++)
            s += mat[i][j];
    return s;
}

void mat_print(const int mat[MAT_SIZE][MAT_SIZE], const char *label) {
    printf("%s (top-left 4x4):\n", label);
    for (int i = 0; i < 4 && i < MAT_SIZE; i++) {
        printf("  ");
        for (int j = 0; j < 4 && j < MAT_SIZE; j++)
            printf("%6d ", mat[i][j]);
        printf("...\n");
    }
    printf("  ...\n");
}
