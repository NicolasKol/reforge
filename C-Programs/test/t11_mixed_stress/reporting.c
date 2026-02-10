#include "mixed.h"

void print_divider(const char *title) {
    printf("\n");
    for (int i = 0; i < 40; i++) putchar('=');
    printf("\n %s\n", title);
    for (int i = 0; i < 40; i++) putchar('=');
    printf("\n");
}

void print_array(const char *label, const int *arr, int n) {
    char buf[BUF_SIZE];
    int pos = 0;
    pos += snprintf(buf + pos, BUF_SIZE - pos, "%s: [ ", label);
    for (int i = 0; i < n && i < 12; i++)
        pos += snprintf(buf + pos, BUF_SIZE - pos, "%d ", arr[i]);
    if (n > 12)
        pos += snprintf(buf + pos, BUF_SIZE - pos, "... ");
    snprintf(buf + pos, BUF_SIZE - pos, "] (%d items)", n);
    printf("  %s\n", buf);
}

void print_summary(const char *label, int total, int count, int min, int max) {
    char buf[BUF_SIZE];
    snprintf(buf, BUF_SIZE,
             "%s: total=%d count=%d min=%d max=%d avg=%.1f",
             label, total, count, min, max,
             count > 0 ? (double)total / count : 0.0);
    printf("  %s\n", buf);
}
