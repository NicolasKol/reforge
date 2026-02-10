#include "parser.h"

/*
 * Simple recursive-descent expression evaluator.
 * Grammar:
 *   expr   → term (('+' | '-') term)*
 *   term   → factor (('*' | '/' | '%') factor)*
 *   factor → NUMBER | '(' expr ')' | '-' factor
 */

static const char *g_src;
static token_t     g_cur;

static void advance(void) {
    g_cur = next_token(&g_src);
}

static int parse_expr(void);

static int parse_factor(void) {
    switch (g_cur.type) {
    case TOK_NUMBER: {
        int v = g_cur.value;
        advance();
        return v;
    }
    case TOK_MINUS: {
        advance();
        return -parse_factor();
    }
    case TOK_LPAREN: {
        advance();
        int v = parse_expr();
        if (g_cur.type == TOK_RPAREN) advance();
        return v;
    }
    default:
        printf("  [eval] unexpected token: %s\n", token_name(g_cur.type));
        advance();
        return 0;
    }
}

static int parse_term(void) {
    int left = parse_factor();
    while (1) {
        switch (g_cur.type) {
        case TOK_STAR:    advance(); left *= parse_factor(); break;
        case TOK_SLASH:   advance(); { int d = parse_factor(); left = d ? left / d : 0; } break;
        case TOK_PERCENT: advance(); { int d = parse_factor(); left = d ? left % d : 0; } break;
        default: return left;
        }
    }
}

static int parse_expr(void) {
    int left = parse_term();
    while (1) {
        switch (g_cur.type) {
        case TOK_PLUS:  advance(); left += parse_term(); break;
        case TOK_MINUS: advance(); left -= parse_term(); break;
        default: return left;
        }
    }
}

int evaluate_expression(const char *src) {
    g_src = src;
    advance();
    return parse_expr();
}

/* Simple RPN evaluator using switch dispatch */
int evaluate_rpn(const token_t *tokens, int count) {
    int stack[64];
    int sp = 0;

    for (int i = 0; i < count; i++) {
        switch (tokens[i].type) {
        case TOK_NUMBER:
            if (sp < 64) stack[sp++] = tokens[i].value;
            break;
        case TOK_PLUS:
            if (sp >= 2) { sp--; stack[sp-1] += stack[sp]; }
            break;
        case TOK_MINUS:
            if (sp >= 2) { sp--; stack[sp-1] -= stack[sp]; }
            break;
        case TOK_STAR:
            if (sp >= 2) { sp--; stack[sp-1] *= stack[sp]; }
            break;
        case TOK_SLASH:
            if (sp >= 2) { sp--; stack[sp-1] = stack[sp] ? stack[sp-1] / stack[sp] : 0; }
            break;
        case TOK_PERCENT:
            if (sp >= 2) { sp--; stack[sp-1] = stack[sp] ? stack[sp-1] % stack[sp] : 0; }
            break;
        default:
            break;
        }
    }
    return sp > 0 ? stack[0] : 0;
}
