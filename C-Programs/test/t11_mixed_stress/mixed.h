#ifndef MIXED_H
#define MIXED_H

#include <stdio.h>
#include <string.h>

#define MAX_ITEMS 64
#define BUF_SIZE  256

/* --- Plugin interface (fptr callbacks) --- */
typedef struct {
    const char *name;
    int (*init)(int *workspace, int n);
    int (*run)(int *workspace, int n);
    void (*report)(const int *workspace, int n, char *buf, int bufsz);
} plugin_t;

/* engine.c */
void engine_init(void);
void engine_register(const plugin_t *plugin);
void engine_run_all(int *workspace, int n);
int  engine_count(void);

/* plugins.c — registers plugins with duplicate static names */
void register_all_plugins(void);

/* reporting.c */
void print_divider(const char *title);
void print_array(const char *label, const int *arr, int n);
void print_summary(const char *label, int total, int count, int min, int max);

#endif /* MIXED_H */
