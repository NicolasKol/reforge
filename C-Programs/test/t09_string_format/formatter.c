#include "format.h"

const char *style_name(format_style_t s) {
    switch (s) {
    case FMT_PLAIN:     return "plain";
    case FMT_BRACKETS:  return "brackets";
    case FMT_CSV:       return "csv";
    case FMT_JSON_LIKE: return "json";
    case FMT_TABLE_ROW: return "table";
    }
    return "unknown";
}

int format_int_array(char *buf, int bufsz, const int *arr, int n,
                     format_style_t style) {
    int pos = 0;
    switch (style) {
    case FMT_PLAIN:
        for (int i = 0; i < n; i++)
            pos += snprintf(buf + pos, bufsz - pos, "%d ", arr[i]);
        break;

    case FMT_BRACKETS:
        pos += snprintf(buf + pos, bufsz - pos, "[ ");
        for (int i = 0; i < n; i++) {
            pos += snprintf(buf + pos, bufsz - pos, "%d", arr[i]);
            if (i < n - 1) pos += snprintf(buf + pos, bufsz - pos, ", ");
        }
        pos += snprintf(buf + pos, bufsz - pos, " ]");
        break;

    case FMT_CSV:
        for (int i = 0; i < n; i++) {
            pos += snprintf(buf + pos, bufsz - pos, "%d", arr[i]);
            if (i < n - 1) pos += snprintf(buf + pos, bufsz - pos, ",");
        }
        break;

    case FMT_JSON_LIKE:
        pos += snprintf(buf + pos, bufsz - pos, "[");
        for (int i = 0; i < n; i++) {
            pos += snprintf(buf + pos, bufsz - pos, "%d", arr[i]);
            if (i < n - 1) pos += snprintf(buf + pos, bufsz - pos, ", ");
        }
        pos += snprintf(buf + pos, bufsz - pos, "]");
        break;

    case FMT_TABLE_ROW:
        pos += snprintf(buf + pos, bufsz - pos, "| ");
        for (int i = 0; i < n; i++)
            pos += snprintf(buf + pos, bufsz - pos, "%6d | ", arr[i]);
        break;
    }
    return pos;
}

int format_key_value(char *buf, int bufsz, const char *key, const char *value,
                     format_style_t style) {
    switch (style) {
    case FMT_PLAIN:     return snprintf(buf, bufsz, "%s: %s", key, value);
    case FMT_BRACKETS:  return snprintf(buf, bufsz, "[%s=%s]", key, value);
    case FMT_CSV:       return snprintf(buf, bufsz, "%s,%s", key, value);
    case FMT_JSON_LIKE: return snprintf(buf, bufsz, "\"%s\": \"%s\"", key, value);
    case FMT_TABLE_ROW: return snprintf(buf, bufsz, "| %-12s | %-20s |", key, value);
    }
    return 0;
}

int format_record(char *buf, int bufsz, const char *name, int id,
                  int score, format_style_t style) {
    switch (style) {
    case FMT_PLAIN:
        return snprintf(buf, bufsz, "%s #%d score=%d", name, id, score);
    case FMT_BRACKETS:
        return snprintf(buf, bufsz, "[%s id=%d score=%d]", name, id, score);
    case FMT_CSV:
        return snprintf(buf, bufsz, "%s,%d,%d", name, id, score);
    case FMT_JSON_LIKE:
        return snprintf(buf, bufsz,
            "{\"name\": \"%s\", \"id\": %d, \"score\": %d}",
            name, id, score);
    case FMT_TABLE_ROW:
        return snprintf(buf, bufsz, "| %-12s | %4d | %6d |",
                        name, id, score);
    }
    return 0;
}
