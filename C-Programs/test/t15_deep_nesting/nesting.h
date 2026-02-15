#ifndef NESTING_H
#define NESTING_H

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define GRID_SIZE 8
#define MAX_DEPTH 12

/* deep_control.c — deeply nested control flow */
int  deep_if_chain(int a, int b, int c, int d);
int  deep_loop_nest(int grid[GRID_SIZE][GRID_SIZE]);
int  deep_mixed_nest(const int *data, int n);
int  deep_switch_nest(int opcode, int mode, int flags);

/* deep_data.c — deep nesting with data-dependent paths */
int  deep_validate_record(const int *fields, int nfields);
int  deep_search_grid(int grid[GRID_SIZE][GRID_SIZE], int target);
int  deep_do_while_cascade(int *buf, int n, int passes);
int  deep_goto_error_cascade(int *resources, int n);

#endif /* NESTING_H */
