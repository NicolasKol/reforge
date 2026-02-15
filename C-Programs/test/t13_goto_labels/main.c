#include "cleanup.h"

int main(void) {
    printf("=== t13_goto_labels ===\n\n");

    /* --- Test 1: resource acquisition + release --- */
    printf("--- Test 1: acquire/release resources ---\n");
    resource_t resources[MAX_RESOURCES];
    int count = acquire_resources(resources, 4);
    printf("  acquired: %d\n", count);
    if (count > 0)
        release_resources(resources, count);

    /* --- Test 2: multi-stage pipeline --- */
    printf("\n--- Test 2: pipeline processing ---\n");
    int input[]  = {5, 12, 3, 8, 1, 20, 7, 15};
    int output[8] = {0};
    int rc = process_pipeline(input, 8, output);
    printf("  pipeline result: %d\n", rc);
    if (rc == 0) {
        printf("  output:");
        for (int i = 0; i < 8; i++)
            printf(" %d", output[i]);
        printf("\n");
    }

    /* --- Test 3: multi-stage init + teardown --- */
    printf("\n--- Test 3: multi-stage init ---\n");
    resource_t pool[4];
    memset(pool, 0, sizeof(pool));
    rc = multi_stage_init(pool, 4);
    printf("  init result: %d\n", rc);
    if (rc == 0) {
        for (int i = 0; i < 4; i++) {
            if (pool[i].data) {
                printf("  stage %d: %s (size=%d)\n",
                       pool[i].id, pool[i].name, pool[i].size);
                free(pool[i].data);
            }
        }
    }

    /* --- Test 4: computed goto bytecode interpreter --- */
    printf("\n--- Test 4: computed goto interpreter ---\n");

    /* Program: push 10, push 20, add, print, halt */
    unsigned char prog1[] = {
        OP_PUSH, 10,
        OP_PUSH, 20,
        OP_ADD,
        OP_PRINT,
        OP_HALT
    };
    int r1 = run_bytecode(prog1, sizeof(prog1));
    printf("  result: %d\n", r1);

    /* Program: push 3, dup, mul, push 1, add, print, halt */
    unsigned char prog2[] = {
        OP_PUSH, 3,
        OP_DUP,
        OP_MUL,
        OP_PUSH, 1,
        OP_ADD,
        OP_PRINT,
        OP_HALT
    };
    int r2 = run_bytecode(prog2, sizeof(prog2));
    printf("  result: %d\n", r2);

    /* --- Test 5: safe interpreter (switch-based, same programs) --- */
    printf("\n--- Test 5: switch-based interpreter ---\n");
    int r3 = run_bytecode_safe(prog1, sizeof(prog1));
    printf("  safe result prog1: %d\n", r3);
    int r4 = run_bytecode_safe(prog2, sizeof(prog2));
    printf("  safe result prog2: %d\n", r4);

    printf("\nDone.\n");
    return 0;
}
