#include "vector.h"

/* Thin wrapper — uses vec_* from header as a stack */

void run_stack_tests(void) {
    Vec stack;
    vec_init(&stack);

    printf("=== Stack Tests ===\n");

    /* Push values */
    for (int i = 1; i <= 10; i++) {
        vec_push(&stack, i * 10);
    }
    vec_print(&stack, "After push");

    /* Pop half */
    printf("Popped: ");
    for (int i = 0; i < 5; i++) {
        printf("%d ", vec_pop(&stack));
    }
    printf("\n");
    vec_print(&stack, "After pop");

    /* Sum */
    printf("Sum = %d\n", vec_sum(&stack));

    vec_free(&stack);
}
