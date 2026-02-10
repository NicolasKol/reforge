#include "mixed.h"

/* Engine: plugin registry with function-pointer dispatch */

static plugin_t g_plugins[16];
static int      g_count = 0;

/* static helpers — name collides with plugins.c statics */
static int validate(int x) {
    return x >= 0;
}

static void process(int *arr, int n) {
    /* engine's version: absolute value normalization */
    for (int i = 0; i < n; i++) {
        if (!validate(arr[i]))
            arr[i] = -arr[i];
    }
}

void engine_init(void) {
    g_count = 0;
    memset(g_plugins, 0, sizeof(g_plugins));
}

void engine_register(const plugin_t *plugin) {
    if (g_count < 16) {
        g_plugins[g_count++] = *plugin;
    }
}

int engine_count(void) {
    return g_count;
}

void engine_run_all(int *workspace, int n) {
    /* Pre-process: normalize via engine's static process() */
    process(workspace, n);

    for (int i = 0; i < g_count; i++) {
        printf("  >> plugin [%s]\n", g_plugins[i].name);

        /* init via fptr */
        int init_ok = g_plugins[i].init(workspace, n);
        if (!init_ok) {
            printf("     init FAILED, skipping\n");
            continue;
        }

        /* run via fptr */
        int result = g_plugins[i].run(workspace, n);
        printf("     run result = %d\n", result);

        /* report via fptr */
        char buf[BUF_SIZE];
        g_plugins[i].report(workspace, n, buf, BUF_SIZE);
        printf("     %s\n", buf);
    }
}
