#include "common.h"

int main(void) {
    /* Test array operations */
    int data[] = {5, 3, 8, 1, 9, 2, 7};
    int n = sizeof(data) / sizeof(data[0]);

    printf("Array: ");
    array_print(data, n);
    printf("Sum: %d\n", array_sum(data, n));
    printf("Max: %d\n", array_max(data, n));
    printf("Min: %d\n", array_min(data, n));

    /* Use clamp from header (cross-file inline pressure) */
    int clamped = clamp_int(42, 0, 10);
    printf("Clamp(42, 0, 10) = %d\n", clamped);

    /* Test string operations */
    const char *msg = "Hello, Cross-file Calls!";
    printf("String: \"%s\"\n", msg);
    printf("Length: %d\n", string_length(msg));
    printf("Count 'l': %d\n", string_count_char(msg, 'l'));

    char upper[64];
    string_to_upper(upper, msg, sizeof(upper));
    printf("Upper: \"%s\"\n", upper);

    char rev[64];
    string_reverse(rev, msg, sizeof(rev));
    printf("Reversed: \"%s\"\n", rev);

    return 0;
}
