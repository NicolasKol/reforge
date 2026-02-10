#ifndef COMPUTE_H
#define COMPUTE_H

#include <stdio.h>
#include <string.h>

#define MAT_SIZE 16

/* matrix.c */
void mat_zero(int mat[MAT_SIZE][MAT_SIZE]);
void mat_identity(int mat[MAT_SIZE][MAT_SIZE]);
void mat_fill_pattern(int mat[MAT_SIZE][MAT_SIZE], int seed);
void mat_multiply(const int a[MAT_SIZE][MAT_SIZE],
                  const int b[MAT_SIZE][MAT_SIZE],
                  int       c[MAT_SIZE][MAT_SIZE]);
void mat_transpose(int mat[MAT_SIZE][MAT_SIZE]);
long mat_trace(const int mat[MAT_SIZE][MAT_SIZE]);
long mat_sum(const int mat[MAT_SIZE][MAT_SIZE]);
void mat_print(const int mat[MAT_SIZE][MAT_SIZE], const char *label);

/* sorting.c */
void bubble_sort(int *arr, int n);
void insertion_sort(int *arr, int n);
void selection_sort(int *arr, int n);
int  is_sorted(const int *arr, int n);
void reverse(int *arr, int n);
void rotate_left(int *arr, int n, int k);

#endif /* COMPUTE_H */
