#ifndef VECTOR_H
#define VECTOR_H

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* A simple dynamic array ("vector") implemented entirely in a header.
   All substantial logic lives here — .c files are thin wrappers.
   This makes the header the dominant file for most functions in DWARF. */

typedef struct {
    int *data;
    int  size;
    int  capacity;
} Vec;

static inline void vec_init(Vec *v) {
    v->data = NULL;
    v->size = 0;
    v->capacity = 0;
}

static inline void vec_free(Vec *v) {
    free(v->data);
    v->data = NULL;
    v->size = 0;
    v->capacity = 0;
}

static inline int vec_grow(Vec *v) {
    int new_cap = v->capacity == 0 ? 4 : v->capacity * 2;
    int *new_data = (int *)realloc(v->data, new_cap * sizeof(int));
    if (!new_data) return -1;
    v->data = new_data;
    v->capacity = new_cap;
    return 0;
}

static inline int vec_push(Vec *v, int val) {
    if (v->size >= v->capacity) {
        if (vec_grow(v) != 0) return -1;
    }
    v->data[v->size++] = val;
    return 0;
}

static inline int vec_pop(Vec *v) {
    if (v->size <= 0) return 0;
    return v->data[--v->size];
}

static inline int vec_get(const Vec *v, int idx) {
    if (idx < 0 || idx >= v->size) return 0;
    return v->data[idx];
}

static inline void vec_set(Vec *v, int idx, int val) {
    if (idx >= 0 && idx < v->size) {
        v->data[idx] = val;
    }
}

static inline int vec_find(const Vec *v, int val) {
    for (int i = 0; i < v->size; i++) {
        if (v->data[i] == val) return i;
    }
    return -1;
}

static inline void vec_print(const Vec *v, const char *label) {
    printf("%s[%d/%d]: ", label, v->size, v->capacity);
    for (int i = 0; i < v->size; i++) {
        printf("%d ", v->data[i]);
    }
    printf("\n");
}

static inline void vec_reverse(Vec *v) {
    int lo = 0, hi = v->size - 1;
    while (lo < hi) {
        int tmp = v->data[lo];
        v->data[lo] = v->data[hi];
        v->data[hi] = tmp;
        lo++;
        hi--;
    }
}

static inline int vec_sum(const Vec *v) {
    int s = 0;
    for (int i = 0; i < v->size; i++) s += v->data[i];
    return s;
}

/* Forward declarations for .c files */
void run_stack_tests(void);
void run_search_tests(void);

#endif /* VECTOR_H */
