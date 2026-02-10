#include "parser.h"

const char *token_name(token_type_t t) {
    switch (t) {
    case TOK_EOF:       return "EOF";
    case TOK_NUMBER:    return "NUMBER";
    case TOK_PLUS:      return "PLUS";
    case TOK_MINUS:     return "MINUS";
    case TOK_STAR:      return "STAR";
    case TOK_SLASH:     return "SLASH";
    case TOK_PERCENT:   return "PERCENT";
    case TOK_LPAREN:    return "LPAREN";
    case TOK_RPAREN:    return "RPAREN";
    case TOK_COMMA:     return "COMMA";
    case TOK_SEMICOLON: return "SEMICOLON";
    case TOK_IDENT:     return "IDENT";
    case TOK_ASSIGN:    return "ASSIGN";
    case TOK_ERROR:     return "ERROR";
    case TOK_COUNT:     return "?COUNT?";
    }
    return "UNKNOWN";
}

token_t next_token(const char **src) {
    token_t tok = { .type = TOK_EOF, .value = 0, .ident = {0} };

    /* skip whitespace */
    while (**src && isspace((unsigned char)**src))
        (*src)++;

    if (**src == '\0')
        return tok;

    char c = **src;

    /* single-character tokens — another dense switch */
    switch (c) {
    case '+': tok.type = TOK_PLUS;      (*src)++; return tok;
    case '-': tok.type = TOK_MINUS;     (*src)++; return tok;
    case '*': tok.type = TOK_STAR;      (*src)++; return tok;
    case '/': tok.type = TOK_SLASH;     (*src)++; return tok;
    case '%': tok.type = TOK_PERCENT;   (*src)++; return tok;
    case '(': tok.type = TOK_LPAREN;    (*src)++; return tok;
    case ')': tok.type = TOK_RPAREN;    (*src)++; return tok;
    case ',': tok.type = TOK_COMMA;     (*src)++; return tok;
    case ';': tok.type = TOK_SEMICOLON; (*src)++; return tok;
    case '=': tok.type = TOK_ASSIGN;    (*src)++; return tok;
    default: break;
    }

    /* number */
    if (isdigit((unsigned char)c)) {
        tok.type = TOK_NUMBER;
        tok.value = 0;
        while (isdigit((unsigned char)**src)) {
            tok.value = tok.value * 10 + (**src - '0');
            (*src)++;
        }
        return tok;
    }

    /* identifier */
    if (isalpha((unsigned char)c) || c == '_') {
        tok.type = TOK_IDENT;
        int i = 0;
        while ((isalnum((unsigned char)**src) || **src == '_') && i < 31) {
            tok.ident[i++] = **src;
            (*src)++;
        }
        tok.ident[i] = '\0';
        return tok;
    }

    /* unrecognized */
    tok.type = TOK_ERROR;
    (*src)++;
    return tok;
}

void print_token(const token_t *tok) {
    switch (tok->type) {
    case TOK_NUMBER:
        printf("%-10s %d\n", token_name(tok->type), tok->value);
        break;
    case TOK_IDENT:
        printf("%-10s %s\n", token_name(tok->type), tok->ident);
        break;
    default:
        printf("%-10s\n", token_name(tok->type));
        break;
    }
}
