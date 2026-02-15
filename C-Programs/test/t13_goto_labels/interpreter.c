#include "cleanup.h"

/*
 * interpreter.c — Bytecode interpreter using computed goto (GCC extension).
 *
 * The computed-goto pattern (&&label + goto *table[x]) is a common
 * optimization in interpreters and VMs. tree-sitter should parse the
 * label addresses and indirect goto, but oracle_ts must flag them as
 * NONSTANDARD_EXTENSION_PATTERN since &&label is a GCC extension.
 *
 * Also includes a standard-C fallback using a switch-based dispatch
 * for comparison.
 */

/* Bytecode opcodes are now in cleanup.h */

#define STACK_MAX 64

/* Static helper — name collision with resource.c */
static int validate(int value) {
    return value >= -10000 && value <= 10000;
}

static void log_action(const char *action, int pc) {
    printf("    [interp] pc=%d %s\n", pc, action);
}

/*
 * run_bytecode — computed goto dispatch (GCC extension).
 * Uses &&label to build a dispatch table, then goto *table[opcode].
 * This exercises:
 *   - labeled_statement (L_NOP:, L_PUSH:, etc.)
 *   - goto_statement (goto *dispatch[op])
 *   - NONSTANDARD_EXTENSION_PATTERN (&&L_NOP)
 */
int run_bytecode(const unsigned char *program, int len) {
    /* Dispatch table using label addresses — GCC extension */
    static void *dispatch[] = {
        &&L_NOP,   /* 0x00 */
        &&L_PUSH,  /* 0x01 */
        &&L_POP,   /* 0x02 */
        &&L_ADD,   /* 0x03 */
        &&L_SUB,   /* 0x04 */
        &&L_MUL,   /* 0x05 */
        &&L_DUP,   /* 0x06 */
        &&L_PRINT, /* 0x07 */
        &&L_JMP,   /* 0x08 */
        &&L_JZ,    /* 0x09 */
    };

    int stack[STACK_MAX];
    int sp = 0;
    int pc = 0;

    if (len <= 0)
        return -1;

    /* Initial dispatch */
    unsigned char op = program[pc];
    if (op == OP_HALT) goto L_HALT;
    if (op > 0x09)     goto L_HALT;
    goto *dispatch[op];

L_NOP:
    log_action("NOP", pc);
    pc++;
    if (pc >= len) goto L_HALT;
    op = program[pc];
    if (op == OP_HALT) goto L_HALT;
    if (op > 0x09)     goto L_HALT;
    goto *dispatch[op];

L_PUSH:
    pc++;
    if (pc >= len) goto L_HALT;
    if (sp < STACK_MAX) {
        stack[sp++] = (int)program[pc];
        log_action("PUSH", pc - 1);
    }
    pc++;
    if (pc >= len) goto L_HALT;
    op = program[pc];
    if (op == OP_HALT) goto L_HALT;
    if (op > 0x09)     goto L_HALT;
    goto *dispatch[op];

L_POP:
    if (sp > 0) sp--;
    log_action("POP", pc);
    pc++;
    if (pc >= len) goto L_HALT;
    op = program[pc];
    if (op == OP_HALT) goto L_HALT;
    if (op > 0x09)     goto L_HALT;
    goto *dispatch[op];

L_ADD:
    if (sp >= 2) { sp--; stack[sp - 1] += stack[sp]; }
    log_action("ADD", pc);
    pc++;
    if (pc >= len) goto L_HALT;
    op = program[pc];
    if (op == OP_HALT) goto L_HALT;
    if (op > 0x09)     goto L_HALT;
    goto *dispatch[op];

L_SUB:
    if (sp >= 2) { sp--; stack[sp - 1] -= stack[sp]; }
    log_action("SUB", pc);
    pc++;
    if (pc >= len) goto L_HALT;
    op = program[pc];
    if (op == OP_HALT) goto L_HALT;
    if (op > 0x09)     goto L_HALT;
    goto *dispatch[op];

L_MUL:
    if (sp >= 2) { sp--; stack[sp - 1] *= stack[sp]; }
    log_action("MUL", pc);
    pc++;
    if (pc >= len) goto L_HALT;
    op = program[pc];
    if (op == OP_HALT) goto L_HALT;
    if (op > 0x09)     goto L_HALT;
    goto *dispatch[op];

L_DUP:
    if (sp > 0 && sp < STACK_MAX) { stack[sp] = stack[sp - 1]; sp++; }
    log_action("DUP", pc);
    pc++;
    if (pc >= len) goto L_HALT;
    op = program[pc];
    if (op == OP_HALT) goto L_HALT;
    if (op > 0x09)     goto L_HALT;
    goto *dispatch[op];

L_PRINT:
    if (sp > 0) {
        printf("    [interp] PRINT: %d\n", stack[sp - 1]);
    }
    pc++;
    if (pc >= len) goto L_HALT;
    op = program[pc];
    if (op == OP_HALT) goto L_HALT;
    if (op > 0x09)     goto L_HALT;
    goto *dispatch[op];

L_JMP:
    pc++;
    if (pc >= len) goto L_HALT;
    pc += (int)program[pc];
    log_action("JMP", pc);
    if (pc >= len) goto L_HALT;
    op = program[pc];
    if (op == OP_HALT) goto L_HALT;
    if (op > 0x09)     goto L_HALT;
    goto *dispatch[op];

L_JZ:
    pc++;
    if (pc >= len) goto L_HALT;
    if (sp > 0 && stack[sp - 1] == 0) {
        pc += (int)program[pc];
        log_action("JZ (taken)", pc);
    } else {
        pc++;
        log_action("JZ (not taken)", pc);
    }
    if (pc >= len) goto L_HALT;
    op = program[pc];
    if (op == OP_HALT) goto L_HALT;
    if (op > 0x09)     goto L_HALT;
    goto *dispatch[op];

L_HALT:
    log_action("HALT", pc);
    return sp > 0 ? stack[sp - 1] : 0;
}

/*
 * run_bytecode_safe — switch-based dispatch (standard C).
 * Functionally equivalent to run_bytecode but without computed goto.
 * Uses do-while for the dispatch loop to exercise do_statement.
 */
int run_bytecode_safe(const unsigned char *program, int len) {
    int stack[STACK_MAX];
    int sp = 0;
    int pc = 0;
    int running = 1;

    do {
        if (pc >= len) break;
        unsigned char op = program[pc];

        switch (op) {
        case OP_NOP:
            pc++;
            break;

        case OP_PUSH:
            pc++;
            if (pc >= len) { running = 0; break; }
            if (sp < STACK_MAX) stack[sp++] = (int)program[pc];
            pc++;
            break;

        case OP_POP:
            if (sp > 0) sp--;
            pc++;
            break;

        case OP_ADD:
            if (sp >= 2) { sp--; stack[sp - 1] += stack[sp]; }
            pc++;
            break;

        case OP_SUB:
            if (sp >= 2) { sp--; stack[sp - 1] -= stack[sp]; }
            pc++;
            break;

        case OP_MUL:
            if (sp >= 2) { sp--; stack[sp - 1] *= stack[sp]; }
            pc++;
            break;

        case OP_DUP:
            if (sp > 0 && sp < STACK_MAX) { stack[sp] = stack[sp - 1]; sp++; }
            pc++;
            break;

        case OP_PRINT:
            if (sp > 0 && validate(stack[sp - 1]))
                printf("    [safe] PRINT: %d\n", stack[sp - 1]);
            pc++;
            break;

        case OP_JMP:
            pc++;
            if (pc < len) pc += (int)program[pc];
            break;

        case OP_JZ:
            pc++;
            if (pc < len && sp > 0 && stack[sp - 1] == 0)
                pc += (int)program[pc];
            else
                pc++;
            break;

        case OP_HALT:
        default:
            running = 0;
            break;
        }
    } while (running);

    return sp > 0 ? stack[sp - 1] : 0;
}
