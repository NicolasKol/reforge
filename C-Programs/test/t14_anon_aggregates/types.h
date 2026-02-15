#ifndef TYPES_H
#define TYPES_H

#include <stdio.h>
#include <string.h>
#include <stdint.h>

/* Named top-level struct with anonymous nested members */
typedef struct {
    int type;     /* message type tag */

    /* Anonymous union: variant payload */
    union {
        struct {
            uint32_t src_ip;
            uint32_t dst_ip;
            uint16_t src_port;
            uint16_t dst_port;
        };  /* anonymous struct inside anonymous union */

        struct {
            char     text[64];
            uint16_t text_len;
        };  /* another anonymous struct */

        struct {
            uint8_t  data[128];
            uint32_t data_len;
            uint8_t  checksum;
        };  /* raw data variant */
    };  /* anonymous union */
} message_t;

/* Struct with bitfields and anonymous enum */
typedef struct {
    unsigned int active   : 1;
    unsigned int priority : 3;
    unsigned int category : 4;

    /* Anonymous enum for status codes */
    enum {
        STATUS_OK = 0,
        STATUS_PENDING,
        STATUS_ERROR,
        STATUS_TIMEOUT
    } status;

    char label[32];
} entry_t;

/* Deeply nested anonymous aggregate */
typedef struct {
    int id;
    struct {
        int x, y;
        struct {
            int w, h;
        };  /* double-nested anonymous struct */
    };  /* anonymous struct with nested anonymous */
    union {
        float  value_f;
        int    value_i;
    };  /* anonymous union */
} shape_t;

/* protocol.c */
void  message_init_net(message_t *msg, uint32_t src, uint32_t dst,
                       uint16_t sport, uint16_t dport);
void  message_init_text(message_t *msg, const char *text);
void  message_print(const message_t *msg);
int   message_validate(const message_t *msg);

/* registry.c */
void  entry_init(entry_t *e, const char *label, int prio, int cat);
void  entry_print(const entry_t *e);
int   registry_process(entry_t *entries, int n);
void  shape_demo(void);

#endif /* TYPES_H */
