#ifndef COMMON_H
#define COMMON_H

#include <stdio.h>

/* Each module has its own static 'process', 'validate', and 'report'. */
void run_module_a(int *data, int n);
void run_module_b(int *data, int n);
void run_module_c(int *data, int n);

#endif
