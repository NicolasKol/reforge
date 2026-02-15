#include "types.h"

/*
 * protocol.c — Message handling with anonymous aggregate access.
 *
 * Each function accesses members of anonymous structs/unions inside
 * message_t, which forces the compiler to emit unnamed DW_TAG members.
 * oracle_ts should detect ANONYMOUS_AGGREGATE_PRESENT within these
 * function spans.
 */

/* Static helper — uses anonymous struct members directly */
static int check_port_range(uint16_t port) {
    return port > 0 && port < 65535;
}

void message_init_net(message_t *msg, uint32_t src, uint32_t dst,
                      uint16_t sport, uint16_t dport) {
    memset(msg, 0, sizeof(*msg));
    msg->type     = 1;
    /* Accessing anonymous struct inside anonymous union */
    msg->src_ip   = src;
    msg->dst_ip   = dst;
    msg->src_port = sport;
    msg->dst_port = dport;
}

void message_init_text(message_t *msg, const char *text) {
    memset(msg, 0, sizeof(*msg));
    msg->type = 2;
    /* Accessing different anonymous struct variant */
    size_t len = strlen(text);
    if (len > 63) len = 63;
    memcpy(msg->text, text, len);
    msg->text[len] = '\0';
    msg->text_len  = (uint16_t)len;
}

void message_print(const message_t *msg) {
    switch (msg->type) {
    case 1:
        printf("  NET: %u:%u -> %u:%u\n",
               msg->src_ip, msg->src_port,
               msg->dst_ip, msg->dst_port);
        break;
    case 2:
        printf("  TEXT(%u): \"%s\"\n", msg->text_len, msg->text);
        break;
    case 3:
        printf("  DATA(%u bytes, chk=0x%02x)\n",
               msg->data_len, msg->checksum);
        break;
    default:
        printf("  UNKNOWN type=%d\n", msg->type);
        break;
    }
}

int message_validate(const message_t *msg) {
    switch (msg->type) {
    case 1:
        /* Validate network message — access anonymous members */
        if (!check_port_range(msg->src_port)) return 0;
        if (!check_port_range(msg->dst_port)) return 0;
        if (msg->src_ip == 0 || msg->dst_ip == 0) return 0;
        return 1;

    case 2:
        /* Validate text message */
        if (msg->text_len == 0) return 0;
        if (msg->text[0] == '\0') return 0;
        return 1;

    case 3: {
        /* Validate data message — compute checksum */
        uint8_t sum = 0;
        for (uint32_t i = 0; i < msg->data_len && i < 128; i++)
            sum ^= msg->data[i];
        return sum == msg->checksum;
    }

    default:
        return 0;
    }
}
