#include "types.h"

/*
 * registry.c — Entry registry using anonymous enum and bitfields,
 * plus shape_demo using doubly-nested anonymous structs.
 *
 * Functions here exercise:
 *   - Anonymous enum member access (STATUS_OK, etc.)
 *   - Bitfield operations
 *   - Doubly-nested anonymous struct members
 *   - Anonymous union for type-punning
 *
 * oracle_ts should flag ANONYMOUS_AGGREGATE_PRESENT for functions
 * that define or locally use types with anonymous members.
 */

/* Static helper with local anonymous struct */
static int score_entry(const entry_t *e) {
    /* Local anonymous struct for scoring */
    struct {
        int base;
        int bonus;
    } score;

    score.base  = e->priority * 10;
    score.bonus  = (e->status == STATUS_OK) ? 5 : 0;

    if (e->active)
        return score.base + score.bonus;
    return 0;
}

void entry_init(entry_t *e, const char *label, int prio, int cat) {
    memset(e, 0, sizeof(*e));
    e->active   = 1;
    e->priority = prio & 0x7;    /* 3-bit field */
    e->category = cat & 0xF;     /* 4-bit field */
    e->status   = STATUS_PENDING;

    size_t len = strlen(label);
    if (len > 31) len = 31;
    memcpy(e->label, label, len);
    e->label[len] = '\0';
}

void entry_print(const entry_t *e) {
    const char *status_names[] = {"OK", "PENDING", "ERROR", "TIMEOUT"};
    printf("  [%s] active=%u prio=%u cat=%u status=%s score=%d\n",
           e->label, e->active, e->priority, e->category,
           status_names[e->status], score_entry(e));
}

int registry_process(entry_t *entries, int n) {
    int total_score = 0;

    /* Phase 1: activate and score */
    for (int i = 0; i < n; i++) {
        if (entries[i].active) {
            entries[i].status = STATUS_OK;
            total_score += score_entry(&entries[i]);
        }
    }

    /* Phase 2: demote low-priority entries */
    for (int i = 0; i < n; i++) {
        if (entries[i].priority < 2) {
            entries[i].status = STATUS_TIMEOUT;
            entries[i].active = 0;
        }
    }

    /* Phase 3: local anonymous union for result packing */
    union {
        struct {
            uint16_t count;
            uint16_t score;
        };
        uint32_t packed;
    } result;

    result.count = 0;
    result.score = 0;
    for (int i = 0; i < n; i++) {
        if (entries[i].active) {
            result.count++;
            result.score += score_entry(&entries[i]);
        }
    }

    printf("  registry: active=%u total_score=%u packed=0x%08x\n",
           result.count, result.score, result.packed);

    return total_score;
}

void shape_demo(void) {
    printf("  --- shape demo (double-nested anon) ---\n");

    /* Exercises doubly-nested anonymous struct access */
    shape_t shapes[3];

    shapes[0] = (shape_t){ .id = 1, .x = 10, .y = 20, .w = 100, .h = 50,
                            .value_f = 3.14f };
    shapes[1] = (shape_t){ .id = 2, .x = 30, .y = 40, .w = 200, .h = 80,
                            .value_i = 42 };
    shapes[2] = (shape_t){ .id = 3, .x = 0,  .y = 0,  .w = 640, .h = 480,
                            .value_f = 1.0f };

    for (int i = 0; i < 3; i++) {
        /* Accessing doubly-nested anonymous struct members */
        int area = shapes[i].w * shapes[i].h;
        printf("  shape %d: pos=(%d,%d) size=%dx%d area=%d",
               shapes[i].id,
               shapes[i].x, shapes[i].y,
               shapes[i].w, shapes[i].h,
               area);

        /* Access anonymous union member */
        if (shapes[i].id == 2)
            printf(" value_i=%d", shapes[i].value_i);
        else
            printf(" value_f=%.2f", shapes[i].value_f);

        printf("\n");
    }
}
