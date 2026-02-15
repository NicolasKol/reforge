#include "cleanup.h"

/*
 * resource.c — Resource management using goto-based cleanup patterns.
 *
 * Every function here uses the standard C idiom:
 *   allocate A → allocate B → ... → use → cleanup in reverse order.
 * On failure at any step, goto the appropriate cleanup label.
 * This produces goto_statement and labeled_statement nodes that
 * oracle_ts v0.1.1 must index.
 */

/* ---------- helpers (static, name-collision with interpreter.c) ---------- */

static int validate(int id) {
    return id > 0 && id < 10000;
}

static void log_action(const char *action, const char *name) {
    printf("    [resource] %s: %s\n", action, name);
}

/* ---------- acquire_resources ---------- */

int acquire_resources(resource_t *out, int count) {
    if (count <= 0 || count > MAX_RESOURCES)
        return -1;

    int acquired = 0;

    for (int i = 0; i < count; i++) {
        out[i].data = malloc(64);
        if (!out[i].data)
            goto fail_alloc;

        out[i].id   = i + 1;
        out[i].size = 64;
        snprintf(out[i].name, sizeof(out[i].name), "res_%d", i);
        memset(out[i].data, 0, 64);
        acquired++;
        log_action("acquired", out[i].name);
    }

    return acquired;

fail_alloc:
    /* Rollback: free everything already allocated */
    for (int j = acquired - 1; j >= 0; j--) {
        log_action("rollback", out[j].name);
        free(out[j].data);
        out[j].data = NULL;
    }
    return -1;
}

/* ---------- release_resources ---------- */

void release_resources(resource_t *res, int count) {
    for (int i = count - 1; i >= 0; i--) {
        if (res[i].data) {
            log_action("released", res[i].name);
            free(res[i].data);
            res[i].data = NULL;
        }
    }
}

/* ---------- process_pipeline ----------
 * Multi-stage pipeline with goto cleanup on each failure point.
 * Exercises multiple labeled_statement targets and goto_statement nodes.
 */

int process_pipeline(const int *input, int n, int *output) {
    int *buf_a = NULL;
    int *buf_b = NULL;
    int *buf_c = NULL;
    int  result = -1;

    /* Stage 1: allocate working buffer A */
    buf_a = malloc(n * sizeof(int));
    if (!buf_a) {
        printf("    [pipeline] stage 1 alloc failed\n");
        goto done;
    }

    /* Stage 2: transform into buf_a */
    for (int i = 0; i < n; i++) {
        if (!validate(input[i])) {
            printf("    [pipeline] stage 2 validation failed at %d\n", i);
            goto cleanup_a;
        }
        buf_a[i] = input[i] * 3 + 1;
    }

    /* Stage 3: allocate buffer B */
    buf_b = malloc(n * sizeof(int));
    if (!buf_b) {
        printf("    [pipeline] stage 3 alloc failed\n");
        goto cleanup_a;
    }

    /* Stage 4: filter into buf_b */
    for (int i = 0; i < n; i++) {
        buf_b[i] = buf_a[i] > 10 ? buf_a[i] : 0;
    }

    /* Stage 5: allocate buffer C */
    buf_c = malloc(n * sizeof(int));
    if (!buf_c) {
        printf("    [pipeline] stage 5 alloc failed\n");
        goto cleanup_b;
    }

    /* Stage 6: accumulate into buf_c */
    buf_c[0] = buf_b[0];
    for (int i = 1; i < n; i++) {
        buf_c[i] = buf_c[i - 1] + buf_b[i];
    }

    /* Stage 7: copy result */
    for (int i = 0; i < n; i++) {
        output[i] = buf_c[i];
    }
    result = 0;

/* Cleanup labels — reverse order */
    free(buf_c);
cleanup_b:
    free(buf_b);
cleanup_a:
    free(buf_a);
done:
    return result;
}

/* ---------- multi_stage_init ----------
 * Initializes N resource stages with goto-based rollback.
 * Each stage depends on the previous.
 */

int multi_stage_init(resource_t *pool, int stages) {
    if (stages < 1 || stages > 4)
        return -1;

    /* Stage 1 */
    pool[0].data = malloc(128);
    if (!pool[0].data)
        goto fail_0;
    pool[0].id = 1;
    snprintf(pool[0].name, sizeof(pool[0].name), "stage_1");
    pool[0].size = 128;
    log_action("init", pool[0].name);

    if (stages < 2) goto success;

    /* Stage 2 */
    pool[1].data = malloc(256);
    if (!pool[1].data)
        goto fail_1;
    pool[1].id = 2;
    snprintf(pool[1].name, sizeof(pool[1].name), "stage_2");
    pool[1].size = 256;
    log_action("init", pool[1].name);

    if (stages < 3) goto success;

    /* Stage 3 */
    pool[2].data = malloc(512);
    if (!pool[2].data)
        goto fail_2;
    pool[2].id = 3;
    snprintf(pool[2].name, sizeof(pool[2].name), "stage_3");
    pool[2].size = 512;
    log_action("init", pool[2].name);

    if (stages < 4) goto success;

    /* Stage 4 */
    pool[3].data = malloc(1024);
    if (!pool[3].data)
        goto fail_3;
    pool[3].id = 4;
    snprintf(pool[3].name, sizeof(pool[3].name), "stage_4");
    pool[3].size = 1024;
    log_action("init", pool[3].name);

success:
    return 0;

fail_3:
    free(pool[2].data); pool[2].data = NULL;
fail_2:
    free(pool[1].data); pool[1].data = NULL;
fail_1:
    free(pool[0].data); pool[0].data = NULL;
fail_0:
    return -1;
}
