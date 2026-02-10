#include "common.h"

/* --- String utilities (exported) --- */

int string_length(const char *s) {
    int len = 0;
    while (s[len] != '\0') len++;
    return len;
}

int string_count_char(const char *s, char c) {
    int count = 0;
    for (int i = 0; s[i] != '\0'; i++) {
        if (s[i] == c) count++;
    }
    return count;
}

void string_to_upper(char *dst, const char *src, int maxlen) {
    int i;
    int limit = clamp_int(string_length(src), 0, maxlen - 1);
    for (i = 0; i < limit; i++) {
        char c = src[i];
        if (c >= 'a' && c <= 'z')
            dst[i] = c - ('a' - 'A');
        else
            dst[i] = c;
    }
    dst[i] = '\0';
}

void string_reverse(char *dst, const char *src, int maxlen) {
    int len = string_length(src);
    int limit = clamp_int(len, 0, maxlen - 1);
    for (int i = 0; i < limit; i++) {
        dst[i] = src[limit - 1 - i];
    }
    dst[limit] = '\0';
}

/* Static helper — only visible in this TU */
static int string_is_alpha(char c) {
    return (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z');
}
