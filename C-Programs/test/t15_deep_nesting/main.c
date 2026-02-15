#include "nesting.h"

int main(void) {
    printf("=== t15_deep_nesting ===\n\n");

    /* --- Test 1: deep if chain --- */
    printf("--- Test 1: deep if chain ---\n");
    printf("  classify(5,3,2,1)  = %d\n", deep_if_chain(5, 3, 2, 1));
    printf("  classify(10,8,3,1) = %d\n", deep_if_chain(10, 8, 3, 1));
    printf("  classify(-1,-2,-3,-4) = %d\n", deep_if_chain(-1, -2, -3, -4));
    printf("  classify(2,4,6,8) = %d\n", deep_if_chain(2, 4, 6, 8));

    /* --- Test 2: deep loop nest (grid convolution) --- */
    printf("\n--- Test 2: deep loop nest ---\n");
    int grid[GRID_SIZE][GRID_SIZE];
    for (int r = 0; r < GRID_SIZE; r++)
        for (int c = 0; c < GRID_SIZE; c++)
            grid[r][c] = (r + 1) * (c + 1);
    int conv_max = deep_loop_nest(grid);
    printf("  convolution max = %d\n", conv_max);

    /* --- Test 3: deep mixed nesting --- */
    printf("\n--- Test 3: deep mixed nest ---\n");
    int data[] = {4, 8, 12, 1, 5, 9, 2, 6, 3, 7};
    int mixed = deep_mixed_nest(data, 10);
    printf("  mixed result = %d\n", mixed);

    /* --- Test 4: deep switch nesting --- */
    printf("\n--- Test 4: deep switch nest ---\n");
    printf("  decode(0,0,1) = %d\n", deep_switch_nest(0, 0, 1));
    printf("  decode(1,1,7) = %d\n", deep_switch_nest(1, 1, 7));
    printf("  decode(2,0,3) = %d\n", deep_switch_nest(2, 0, 3));
    printf("  decode(3,2,0) = %d\n", deep_switch_nest(3, 2, 0));

    /* --- Test 5: deep record validation --- */
    printf("\n--- Test 5: deep validate record ---\n");
    int fields[] = {100, 33, 500, 12, 999, 42, 3000, 60};
    int vc = deep_validate_record(fields, 8);
    printf("  valid count = %d\n", vc);

    /* --- Test 6: deep grid search --- */
    printf("\n--- Test 6: deep grid search ---\n");
    grid[3][4] = 99;
    grid[3][5] = 99;
    grid[4][4] = 99;
    int nb = deep_search_grid(grid, 99);
    printf("  neighbors of 99 = %d\n", nb);

    /* --- Test 7: do-while cascade --- */
    printf("\n--- Test 7: do-while cascade ---\n");
    int cascade_buf[] = {27, 15, 42, 7, 100, 3, 19, 64};
    int iters = deep_do_while_cascade(cascade_buf, 8, 3);
    printf("  iterations = %d\n  result:", iters);
    for (int i = 0; i < 8; i++) printf(" %d", cascade_buf[i]);
    printf("\n");

    /* --- Test 8: goto error cascade --- */
    printf("\n--- Test 8: goto error cascade ---\n");
    int resources[] = {10, 20, 30, 40, 50};
    int rc = deep_goto_error_cascade(resources, 5);
    printf("  result = %d\n", rc);

    /* Trigger error path */
    int bad_resources[] = {10, -5, 30};
    rc = deep_goto_error_cascade(bad_resources, 3);
    printf("  error path result = %d\n", rc);

    printf("\nDone.\n");
    return 0;
}
