#ifndef FORMAT_H
#define FORMAT_H

#include <stdio.h>
#include <string.h>
#include <stdarg.h>

#define FMT_BUF_SIZE 256

/* Format styles */
typedef enum {
    FMT_PLAIN,
    FMT_BRACKETS,
    FMT_CSV,
    FMT_JSON_LIKE,
    FMT_TABLE_ROW
} format_style_t;

/* Log levels */
typedef enum {
    LOG_DEBUG,
    LOG_INFO,
    LOG_WARN,
    LOG_ERROR
} log_level_t;

/* formatter.c */
int format_int_array(char *buf, int bufsz, const int *arr, int n,
                     format_style_t style);
int format_key_value(char *buf, int bufsz, const char *key, const char *value,
                     format_style_t style);
int format_record(char *buf, int bufsz, const char *name, int id,
                  int score, format_style_t style);
const char *style_name(format_style_t s);

/* logger.c */
void log_init(log_level_t min_level);
void log_msg(log_level_t level, const char *fmt, ...);
void log_array(log_level_t level, const char *label,
               const int *arr, int n);
int  log_get_count(log_level_t level);

#endif /* FORMAT_H */
