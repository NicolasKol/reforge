#ifndef CLEANUP_H
#define CLEANUP_H

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define MAX_RESOURCES 8

/* Bytecode opcodes (used by interpreter.c and main.c) */
#define OP_NOP   0x00
#define OP_PUSH  0x01  /* push next byte as value */
#define OP_POP   0x02
#define OP_ADD   0x03
#define OP_SUB   0x04
#define OP_MUL   0x05
#define OP_DUP   0x06
#define OP_PRINT 0x07
#define OP_JMP   0x08  /* jump forward by next byte */
#define OP_JZ    0x09  /* jump if top is zero */
#define OP_HALT  0xFF

/* Opaque resource handle */
typedef struct {
    int   id;
    char  name[32];
    void *data;
    int   size;
} resource_t;

/* resource.c — goto-based resource management */
int  acquire_resources(resource_t *out, int count);
void release_resources(resource_t *res, int count);
int  process_pipeline(const int *input, int n, int *output);
int  multi_stage_init(resource_t *pool, int stages);

/* interpreter.c — computed goto dispatch (GCC extension) */
int  run_bytecode(const unsigned char *program, int len);
int  run_bytecode_safe(const unsigned char *program, int len);

#endif /* CLEANUP_H */
