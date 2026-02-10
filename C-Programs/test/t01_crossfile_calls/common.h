#ifndef COMMON_H
#define COMMON_H

#include <stdio.h>
#include <string.h>

/* Shared error codes */
#define ERR_OK       0
#define ERR_OVERFLOW 1
#define ERR_INVALID  2
#define ERR_NOTFOUND 3

/* Shared small helper — used from multiple .c files.
   At O1+ the compiler may inline this, creating multi-file line spans. */
static inline int clamp_int(int val, int lo, int hi) {
    if (val < lo) return lo;
    if (val > hi) return hi;
    return val;
}

/* Forward declarations for cross-file calls */
int  array_sum(const int *arr, int n);
int  array_max(const int *arr, int n);
int  array_min(const int *arr, int n);
void array_print(const int *arr, int n);

int  string_length(const char *s);
int  string_count_char(const char *s, char c);
void string_to_upper(char *dst, const char *src, int maxlen);
void string_reverse(char *dst, const char *src, int maxlen);

#endif /* COMMON_H */
