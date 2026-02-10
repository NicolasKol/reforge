#include "format.h"

static log_level_t g_min_level = LOG_DEBUG;
static int         g_counts[4] = {0, 0, 0, 0};

static const char *level_tag(log_level_t lv) {
    switch (lv) {
    case LOG_DEBUG: return "DBG";
    case LOG_INFO:  return "INF";
    case LOG_WARN:  return "WRN";
    case LOG_ERROR: return "ERR";
    }
    return "???";
}

static const char *level_prefix(log_level_t lv) {
    switch (lv) {
    case LOG_DEBUG: return "  ";
    case LOG_INFO:  return "* ";
    case LOG_WARN:  return "! ";
    case LOG_ERROR: return "# ";
    }
    return "  ";
}

void log_init(log_level_t min_level) {
    g_min_level = min_level;
    memset(g_counts, 0, sizeof(g_counts));
}

void log_msg(log_level_t level, const char *fmt, ...) {
    g_counts[level]++;
    if (level < g_min_level)
        return;

    char body[FMT_BUF_SIZE];
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(body, sizeof(body), fmt, ap);
    va_end(ap);

    char line[FMT_BUF_SIZE + 32];
    snprintf(line, sizeof(line), "%s[%s] %s",
             level_prefix(level), level_tag(level), body);
    printf("%s\n", line);
}

void log_array(log_level_t level, const char *label,
               const int *arr, int n) {
    g_counts[level]++;
    if (level < g_min_level)
        return;

    char formatted[FMT_BUF_SIZE];
    format_int_array(formatted, sizeof(formatted), arr, n, FMT_BRACKETS);

    printf("%s[%s] %s = %s\n",
           level_prefix(level), level_tag(level), label, formatted);
}

int log_get_count(log_level_t level) {
    return g_counts[level];
}
