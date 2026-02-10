#include "state.h"

const char *event_name(event_t evt) {
    switch (evt) {
    case EVT_START:        return "START";
    case EVT_CONNECT_OK:   return "CONNECT_OK";
    case EVT_CONNECT_FAIL: return "CONNECT_FAIL";
    case EVT_AUTH_OK:      return "AUTH_OK";
    case EVT_AUTH_FAIL:    return "AUTH_FAIL";
    case EVT_REQUEST:      return "REQUEST";
    case EVT_DONE:         return "DONE";
    case EVT_ERROR:        return "ERROR";
    case EVT_RETRY:        return "RETRY";
    case EVT_QUIT:         return "QUIT";
    case EVT_COUNT:        return "?";
    }
    return "UNKNOWN";
}

void sm_init(sm_context_t *ctx) {
    memset(ctx, 0, sizeof(*ctx));
    ctx->current       = STATE_IDLE;
    ctx->retry_count   = 0;
    ctx->process_count = 0;
    ctx->error_count   = 0;

    ctx->states[STATE_IDLE]           = get_idle_state();
    ctx->states[STATE_CONNECTING]     = get_connecting_state();
    ctx->states[STATE_AUTHENTICATING] = get_authenticating_state();
    ctx->states[STATE_READY]          = get_ready_state();
    ctx->states[STATE_PROCESSING]     = get_processing_state();
    ctx->states[STATE_ERROR]          = get_error_state();
    ctx->states[STATE_SHUTDOWN]       = get_shutdown_state();

    /* Enter initial state */
    if (ctx->states[ctx->current]->enter)
        ctx->states[ctx->current]->enter(ctx);
}

void sm_dispatch(sm_context_t *ctx, event_t evt) {
    const state_desc_t *cur = ctx->states[ctx->current];
    printf("  [%s] + %s", cur->name, event_name(evt));

    state_id_t next = cur->handle(ctx, evt);

    if (next != ctx->current) {
        printf(" -> %s\n", ctx->states[next]->name);

        /* Exit old state */
        if (cur->exit)
            cur->exit(ctx);

        ctx->current = next;

        /* Enter new state */
        const state_desc_t *ns = ctx->states[next];
        if (ns->enter)
            ns->enter(ctx);
    } else {
        printf(" (no transition)\n");
    }
}

void sm_run_sequence(sm_context_t *ctx, const event_t *events, int count) {
    for (int i = 0; i < count; i++) {
        sm_dispatch(ctx, events[i]);
        if (ctx->current == STATE_SHUTDOWN)
            break;
    }
}
