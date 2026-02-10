#include "mixed.h"

/* ---------- Plugin A: summation with recursion ---------- */

/* static name collision with engine.c */
static int validate(int x) {
    return x > 0;
}

static int recursive_sum(const int *arr, int lo, int hi) {
    if (lo > hi) return 0;
    if (lo == hi) return arr[lo];
    int mid = lo + (hi - lo) / 2;
    return recursive_sum(arr, lo, mid) + recursive_sum(arr, mid + 1, hi);
}

static int plug_a_init(int *ws, int n) {
    (void)ws; (void)n;
    return 1;
}

static int plug_a_run(int *ws, int n) {
    int count = 0;
    for (int i = 0; i < n; i++) {
        if (validate(ws[i])) count++;
    }
    return recursive_sum(ws, 0, n - 1);
}

static void plug_a_report(const int *ws, int n, char *buf, int bufsz) {
    int sum = recursive_sum(ws, 0, n - 1);
    snprintf(buf, bufsz, "SumPlugin: total=%d over %d items", sum, n);
}

/* ---------- Plugin B: sorting + stats ---------- */

/* static name collision with engine.c */
static void process(int *arr, int n) {
    /* plugin's version: insertion sort */
    for (int i = 1; i < n; i++) {
        int key = arr[i];
        int j = i - 1;
        while (j >= 0 && arr[j] > key) {
            arr[j + 1] = arr[j];
            j--;
        }
        arr[j + 1] = key;
    }
}

static int plug_b_init(int *ws, int n) {
    (void)ws; (void)n;
    return 1;
}

static int plug_b_run(int *ws, int n) {
    /* Sort a copy */
    int copy[MAX_ITEMS];
    int m = n < MAX_ITEMS ? n : MAX_ITEMS;
    memcpy(copy, ws, m * sizeof(int));
    process(copy, m);
    /* Return median */
    return copy[m / 2];
}

static void plug_b_report(const int *ws, int n, char *buf, int bufsz) {
    int copy[MAX_ITEMS];
    int m = n < MAX_ITEMS ? n : MAX_ITEMS;
    memcpy(copy, ws, m * sizeof(int));
    process(copy, m);
    snprintf(buf, bufsz, "SortPlugin: min=%d median=%d max=%d",
             copy[0], copy[m / 2], copy[m - 1]);
}

/* ---------- Plugin C: string-heavy analysis ---------- */

static int plug_c_init(int *ws, int n) {
    (void)ws; (void)n;
    return 1;
}

static int plug_c_run(int *ws, int n) {
    int neg = 0, zero = 0, pos = 0;
    for (int i = 0; i < n; i++) {
        if (ws[i] < 0) neg++;
        else if (ws[i] == 0) zero++;
        else pos++;
    }
    return pos - neg;
}

static void plug_c_report(const int *ws, int n, char *buf, int bufsz) {
    int neg = 0, zero = 0, pos = 0;
    for (int i = 0; i < n; i++) {
        if (ws[i] < 0) neg++;
        else if (ws[i] == 0) zero++;
        else pos++;
    }
    int pos2 = 0;
    pos2 += snprintf(buf + pos2, bufsz - pos2,
                     "AnalysisPlugin: { ");
    pos2 += snprintf(buf + pos2, bufsz - pos2,
                     "\"negative\": %d, ", neg);
    pos2 += snprintf(buf + pos2, bufsz - pos2,
                     "\"zero\": %d, ", zero);
    pos2 += snprintf(buf + pos2, bufsz - pos2,
                     "\"positive\": %d, ", pos);
    pos2 += snprintf(buf + pos2, bufsz - pos2,
                     "\"balance\": %d }", pos - neg);
    (void)pos2;
}

/* ---------- Registration ---------- */

void register_all_plugins(void) {
    static const plugin_t a = { "sum_recursive",  plug_a_init, plug_a_run, plug_a_report };
    static const plugin_t b = { "sort_stats",     plug_b_init, plug_b_run, plug_b_report };
    static const plugin_t c = { "analysis",       plug_c_init, plug_c_run, plug_c_report };
    engine_register(&a);
    engine_register(&b);
    engine_register(&c);
}
