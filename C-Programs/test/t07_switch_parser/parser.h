#ifndef PARSER_H
#define PARSER_H

#include <stdio.h>
#include <stdlib.h>
#include <ctype.h>
#include <string.h>

/* Token types — dense enum for jump-table generation */
typedef enum {
    TOK_EOF = 0,
    TOK_NUMBER,
    TOK_PLUS,
    TOK_MINUS,
    TOK_STAR,
    TOK_SLASH,
    TOK_PERCENT,
    TOK_LPAREN,
    TOK_RPAREN,
    TOK_COMMA,
    TOK_SEMICOLON,
    TOK_IDENT,
    TOK_ASSIGN,
    TOK_ERROR,
    TOK_COUNT
} token_type_t;

typedef struct {
    token_type_t type;
    int          value;   /* only for TOK_NUMBER */
    char         ident[32]; /* only for TOK_IDENT */
} token_t;

/* lexer.c */
const char *token_name(token_type_t t);
token_t next_token(const char **src);
void print_token(const token_t *tok);

/* evaluator.c */
int evaluate_expression(const char *src);
int evaluate_rpn(const token_t *tokens, int count);

#endif /* PARSER_H */
