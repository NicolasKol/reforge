#include "state.h"

int main(void) {
    printf("=== t12_state_machine ===\n\n");

    sm_context_t ctx;
    sm_init(&ctx);

    /* Scenario 1: happy path */
    printf("--- Scenario 1: happy path ---\n");
    event_t happy[] = {
        EVT_START,
        EVT_CONNECT_OK,
        EVT_AUTH_OK,
        EVT_REQUEST,
        EVT_DONE,
        EVT_REQUEST,
        EVT_DONE,
        EVT_QUIT
    };
    sm_run_sequence(&ctx, happy, sizeof(happy) / sizeof(happy[0]));

    /* Scenario 2: connect failure + retry */
    printf("\n--- Scenario 2: connect fail + retry ---\n");
    sm_init(&ctx);
    event_t retry_path[] = {
        EVT_START,
        EVT_CONNECT_FAIL,   /* -> ERROR */
        EVT_RETRY,           /* -> CONNECTING */
        EVT_CONNECT_OK,      /* -> AUTHENTICATING */
        EVT_AUTH_OK,          /* -> READY */
        EVT_REQUEST,
        EVT_DONE,
        EVT_QUIT
    };
    sm_run_sequence(&ctx, retry_path, sizeof(retry_path) / sizeof(retry_path[0]));

    /* Scenario 3: auth failure + processing error */
    printf("\n--- Scenario 3: auth fail, then processing error ---\n");
    sm_init(&ctx);
    event_t error_path[] = {
        EVT_START,
        EVT_CONNECT_OK,
        EVT_AUTH_FAIL,       /* -> ERROR */
        EVT_RETRY,           /* -> CONNECTING */
        EVT_CONNECT_OK,
        EVT_AUTH_OK,
        EVT_REQUEST,
        EVT_ERROR,           /* -> ERROR (processing) */
        EVT_RETRY,
        EVT_CONNECT_OK,
        EVT_AUTH_OK,
        EVT_REQUEST,
        EVT_DONE,
        EVT_QUIT
    };
    sm_run_sequence(&ctx, error_path, sizeof(error_path) / sizeof(error_path[0]));

    printf("\nDone.\n");
    return 0;
}
