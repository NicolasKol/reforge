#ifndef STATE_H
#define STATE_H

#include <stdio.h>
#include <string.h>

/* State identifiers */
typedef enum {
    STATE_IDLE = 0,
    STATE_CONNECTING,
    STATE_AUTHENTICATING,
    STATE_READY,
    STATE_PROCESSING,
    STATE_ERROR,
    STATE_SHUTDOWN,
    STATE_COUNT
} state_id_t;

/* Events that trigger transitions */
typedef enum {
    EVT_START = 0,
    EVT_CONNECT_OK,
    EVT_CONNECT_FAIL,
    EVT_AUTH_OK,
    EVT_AUTH_FAIL,
    EVT_REQUEST,
    EVT_DONE,
    EVT_ERROR,
    EVT_RETRY,
    EVT_QUIT,
    EVT_COUNT
} event_t;

/* Forward declare context */
typedef struct sm_context sm_context_t;

/* State handler function types */
typedef void (*on_enter_fn)(sm_context_t *ctx);
typedef void (*on_exit_fn)(sm_context_t *ctx);
typedef state_id_t (*on_event_fn)(sm_context_t *ctx, event_t evt);

/* State descriptor */
typedef struct {
    state_id_t   id;
    const char  *name;
    on_enter_fn  enter;
    on_exit_fn   exit;
    on_event_fn  handle;
} state_desc_t;

/* State machine context */
struct sm_context {
    state_id_t       current;
    int              retry_count;
    int              process_count;
    int              error_count;
    char             last_error[64];
    const state_desc_t *states[STATE_COUNT];
};

/* transitions.c */
void sm_init(sm_context_t *ctx);
void sm_dispatch(sm_context_t *ctx, event_t evt);
void sm_run_sequence(sm_context_t *ctx, const event_t *events, int count);
const char *event_name(event_t evt);

/* handlers.c */
const state_desc_t *get_idle_state(void);
const state_desc_t *get_connecting_state(void);
const state_desc_t *get_authenticating_state(void);
const state_desc_t *get_ready_state(void);
const state_desc_t *get_processing_state(void);
const state_desc_t *get_error_state(void);
const state_desc_t *get_shutdown_state(void);

#endif /* STATE_H */
