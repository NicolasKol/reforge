#include "nesting.h"

/*
 * deep_data.c — Deep nesting driven by data validation and search.
 *
 * Exercises: do_statement, goto_statement, labeled_statement, plus
 * the other structural node types at extreme depth. Designed so that
 * every function triggers DEEP_NESTING.
 */

/*
 * deep_validate_record — validates a multi-field record with nested checks.
 * Nesting: for > if > if > if > switch > if > if = depth ~8.
 * Structural nodes: for, if, switch, return, compound.
 */
int deep_validate_record(const int *fields, int nfields) {
    int valid_count = 0;

    for (int i = 0; i < nfields; i++) {
        if (fields[i] >= 0) {
            if (fields[i] < 10000) {
                if (i == 0 || fields[i] != fields[i - 1]) {
                    switch (i % 3) {
                    case 0:
                        if (fields[i] % 2 == 0) {
                            if (fields[i] > 10) {
                                valid_count++;
                            }
                        }
                        break;
                    case 1:
                        if (fields[i] % 3 == 0) {
                            if (fields[i] < 5000) {
                                valid_count++;
                            }
                        }
                        break;
                    case 2:
                        if (fields[i] > 0 && fields[i] < 1000) {
                            valid_count++;
                        }
                        break;
                    }
                }
            }
        }
    }
    return valid_count;
}

/*
 * deep_search_grid — searches an 8x8 grid for a target with neighborhood.
 * Nesting: for > for > if > for > for > if > if = depth ~8.
 * Structural nodes: for, if, compound, return.
 */
int deep_search_grid(int grid[GRID_SIZE][GRID_SIZE], int target) {
    for (int r = 0; r < GRID_SIZE; r++) {
        for (int c = 0; c < GRID_SIZE; c++) {
            if (grid[r][c] == target) {
                /* Found — now check neighborhood */
                int neighbors = 0;
                for (int dr = -1; dr <= 1; dr++) {
                    for (int dc = -1; dc <= 1; dc++) {
                        if (dr == 0 && dc == 0) continue;
                        int nr = r + dr, nc = c + dc;
                        if (nr >= 0 && nr < GRID_SIZE &&
                            nc >= 0 && nc < GRID_SIZE) {
                            if (grid[nr][nc] == target) {
                                neighbors++;
                            }
                        }
                    }
                }
                return neighbors;
            }
        }
    }
    return -1;
}

/*
 * deep_do_while_cascade — multi-pass transformation using do-while loops.
 * Nesting: do > for > if > do > if > while = depth ~7.
 * Structural nodes: do_statement, for, if, while, compound.
 */
int deep_do_while_cascade(int *buf, int n, int passes) {
    int iterations = 0;

    do {
        int changed = 0;
        for (int i = 0; i < n; i++) {
            if (buf[i] > 1) {
                int tmp = buf[i];
                do {
                    if (tmp % 2 == 0) {
                        tmp /= 2;
                    } else {
                        tmp = tmp * 3 + 1;
                    }
                    iterations++;

                    /* Inner while for convergence check */
                    int steps = 0;
                    while (tmp > 100 && steps < 10) {
                        tmp /= 2;
                        steps++;
                        iterations++;
                    }
                } while (tmp > 1 && iterations < 1000);

                if (tmp != buf[i]) {
                    buf[i] = tmp;
                    changed = 1;
                }
            }
        }

        if (!changed) break;
        passes--;
    } while (passes > 0);

    return iterations;
}

/*
 * deep_goto_error_cascade — multi-resource init with deep goto cleanup.
 * Nesting: if > if > for > if > if = depth ~6, plus labeled_statement.
 * Structural nodes: goto_statement, labeled_statement, if, for, compound.
 */
int deep_goto_error_cascade(int *resources, int n) {
    int *buf_a = NULL;
    int *buf_b = NULL;
    int *buf_c = NULL;
    int *buf_d = NULL;
    int  result = -1;

    if (n <= 0 || n > 1024)
        goto err_args;

    /* Allocate A */
    buf_a = malloc(n * sizeof(int));
    if (!buf_a)
        goto err_args;

    /* Allocate B */
    buf_b = malloc(n * sizeof(int));
    if (!buf_b)
        goto err_a;

    /* Initialize A from resources with deep validation */
    for (int i = 0; i < n; i++) {
        if (resources[i] >= 0) {
            if (resources[i] < 10000) {
                buf_a[i] = resources[i] * 2;
            } else {
                printf("    [cascade] value too large at %d\n", i);
                goto err_b;
            }
        } else {
            printf("    [cascade] negative value at %d\n", i);
            goto err_b;
        }
    }

    /* Allocate C */
    buf_c = malloc(n * sizeof(int));
    if (!buf_c)
        goto err_b;

    /* Transform A -> C */
    for (int i = 0; i < n; i++) {
        buf_c[i] = buf_a[i] + (i > 0 ? buf_a[i - 1] : 0);
    }

    /* Allocate D */
    buf_d = malloc(n * sizeof(int));
    if (!buf_d)
        goto err_c;

    /* Final merge */
    for (int i = 0; i < n; i++) {
        buf_d[i] = buf_b[i] + buf_c[i];
    }

    /* Compute result */
    result = 0;
    for (int i = 0; i < n; i++) {
        result += buf_d[i];
    }

    /* Success cleanup */
    free(buf_d);
err_c:
    free(buf_c);
err_b:
    free(buf_b);
err_a:
    free(buf_a);
err_args:
    return result;
}
