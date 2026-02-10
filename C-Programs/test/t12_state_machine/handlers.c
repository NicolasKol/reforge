#include "state.h"

/*
 * Each state has static on_enter / on_exit / handle functions.
 * The names "on_enter", "on_exit", "handle" repeat across states
 * but are scoped per-state via static + unique state descriptors.
 *
 * Note: all on_enter/on_exit/handle are static, creating many
 * identically-named DW_TAG_subprogram entries in the same CU.
 */

/* ========== IDLE ========== */
static void idle_enter(sm_context_t *ctx) {
    (void)ctx;
    printf("    [idle] entered — waiting for start\n");
}
static void idle_exit(sm_context_t *ctx) {
    (void)ctx;
}
static state_id_t idle_handle(sm_context_t *ctx, event_t evt) {
    (void)ctx;
    if (evt == EVT_START) return STATE_CONNECTING;
    if (evt == EVT_QUIT)  return STATE_SHUTDOWN;
    return STATE_IDLE;
}
static const state_desc_t s_idle = {
    STATE_IDLE, "IDLE", idle_enter, idle_exit, idle_handle
};

/* ========== CONNECTING ========== */
static void conn_enter(sm_context_t *ctx) {
    printf("    [connecting] attempt #%d\n", ctx->retry_count + 1);
}
static void conn_exit(sm_context_t *ctx) {
    (void)ctx;
}
static state_id_t conn_handle(sm_context_t *ctx, event_t evt) {
    if (evt == EVT_CONNECT_OK)   return STATE_AUTHENTICATING;
    if (evt == EVT_CONNECT_FAIL) {
        ctx->retry_count++;
        snprintf(ctx->last_error, sizeof(ctx->last_error), "connect failed");
        return STATE_ERROR;
    }
    if (evt == EVT_QUIT) return STATE_SHUTDOWN;
    return STATE_CONNECTING;
}
static const state_desc_t s_connecting = {
    STATE_CONNECTING, "CONNECTING", conn_enter, conn_exit, conn_handle
};

/* ========== AUTHENTICATING ========== */
static void auth_enter(sm_context_t *ctx) {
    (void)ctx;
    printf("    [auth] verifying credentials\n");
}
static void auth_exit(sm_context_t *ctx) {
    (void)ctx;
}
static state_id_t auth_handle(sm_context_t *ctx, event_t evt) {
    if (evt == EVT_AUTH_OK)   return STATE_READY;
    if (evt == EVT_AUTH_FAIL) {
        snprintf(ctx->last_error, sizeof(ctx->last_error), "auth failed");
        return STATE_ERROR;
    }
    if (evt == EVT_QUIT) return STATE_SHUTDOWN;
    return STATE_AUTHENTICATING;
}
static const state_desc_t s_auth = {
    STATE_AUTHENTICATING, "AUTHENTICATING", auth_enter, auth_exit, auth_handle
};

/* ========== READY ========== */
static void ready_enter(sm_context_t *ctx) {
    (void)ctx;
    printf("    [ready] accepting requests\n");
}
static void ready_exit(sm_context_t *ctx) {
    (void)ctx;
}
static state_id_t ready_handle(sm_context_t *ctx, event_t evt) {
    (void)ctx;
    if (evt == EVT_REQUEST) return STATE_PROCESSING;
    if (evt == EVT_QUIT)    return STATE_SHUTDOWN;
    return STATE_READY;
}
static const state_desc_t s_ready = {
    STATE_READY, "READY", ready_enter, ready_exit, ready_handle
};

/* ========== PROCESSING ========== */
static void proc_enter(sm_context_t *ctx) {
    ctx->process_count++;
    printf("    [processing] job #%d\n", ctx->process_count);
}
static void proc_exit(sm_context_t *ctx) {
    (void)ctx;
}
static state_id_t proc_handle(sm_context_t *ctx, event_t evt) {
    if (evt == EVT_DONE)  return STATE_READY;
    if (evt == EVT_ERROR) {
        snprintf(ctx->last_error, sizeof(ctx->last_error),
                 "processing error on job #%d", ctx->process_count);
        return STATE_ERROR;
    }
    if (evt == EVT_QUIT) return STATE_SHUTDOWN;
    return STATE_PROCESSING;
}
static const state_desc_t s_processing = {
    STATE_PROCESSING, "PROCESSING", proc_enter, proc_exit, proc_handle
};

/* ========== ERROR ========== */
static void err_enter(sm_context_t *ctx) {
    ctx->error_count++;
    printf("    [error] #%d: %s\n", ctx->error_count, ctx->last_error);
}
static void err_exit(sm_context_t *ctx) {
    (void)ctx;
}
static state_id_t err_handle(sm_context_t *ctx, event_t evt) {
    if (evt == EVT_RETRY) {
        /* Retry goes back to connecting */
        return STATE_CONNECTING;
    }
    if (evt == EVT_QUIT) return STATE_SHUTDOWN;
    (void)ctx;
    return STATE_ERROR;
}
static const state_desc_t s_error = {
    STATE_ERROR, "ERROR", err_enter, err_exit, err_handle
};

/* ========== SHUTDOWN ========== */
static void shut_enter(sm_context_t *ctx) {
    printf("    [shutdown] processed=%d errors=%d retries=%d\n",
           ctx->process_count, ctx->error_count, ctx->retry_count);
}
static void shut_exit(sm_context_t *ctx) {
    (void)ctx;
}
static state_id_t shut_handle(sm_context_t *ctx, event_t evt) {
    (void)ctx; (void)evt;
    return STATE_SHUTDOWN;  /* terminal state */
}
static const state_desc_t s_shutdown = {
    STATE_SHUTDOWN, "SHUTDOWN", shut_enter, shut_exit, shut_handle
};

/* ========== Accessors ========== */
const state_desc_t *get_idle_state(void)           { return &s_idle; }
const state_desc_t *get_connecting_state(void)     { return &s_connecting; }
const state_desc_t *get_authenticating_state(void) { return &s_auth; }
const state_desc_t *get_ready_state(void)          { return &s_ready; }
const state_desc_t *get_processing_state(void)     { return &s_processing; }
const state_desc_t *get_error_state(void)          { return &s_error; }
const state_desc_t *get_shutdown_state(void)       { return &s_shutdown; }
