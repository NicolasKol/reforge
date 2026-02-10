#ifndef DISPATCH_H
#define DISPATCH_H

#include <stdio.h>
#include <stdlib.h>

/* Callback signature: takes an int array and length, returns result */
typedef int (*operation_fn)(const int *data, int n);

/* Transformer: mutates data in place */
typedef void (*transform_fn)(int *data, int n);

/* Dispatch table entry */
typedef struct {
    const char   *name;
    operation_fn  op;
} dispatch_entry_t;

/* Transformer chain entry */
typedef struct {
    const char    *name;
    transform_fn   fn;
} transform_entry_t;

/* handlers.c */
int op_sum(const int *data, int n);
int op_product(const int *data, int n);
int op_max(const int *data, int n);
int op_count_positive(const int *data, int n);

void tx_double(int *data, int n);
void tx_negate(int *data, int n);
void tx_clamp(int *data, int n);

/* dispatcher.c */
int run_dispatch_table(const dispatch_entry_t *table, int count,
                       const int *data, int n);
void run_transform_chain(const transform_entry_t *chain, int count,
                         int *data, int n);

#endif /* DISPATCH_H */
