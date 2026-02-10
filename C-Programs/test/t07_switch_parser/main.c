#include "parser.h"

static void test_lexer(const char *input) {
    printf("Lex: \"%s\"\n", input);
    const char *p = input;
    token_t tok;
    do {
        tok = next_token(&p);
        printf("  ");
        print_token(&tok);
    } while (tok.type != TOK_EOF && tok.type != TOK_ERROR);
    printf("\n");
}

static void test_eval(const char *expr) {
    int result = evaluate_expression(expr);
    printf("Eval: \"%s\" = %d\n", expr, result);
}

int main(void) {
    printf("=== t07_switch_parser ===\n\n");

    /* Lexer tests */
    test_lexer("42 + 7 * (3 - 1)");
    test_lexer("x = 100 / 5 % 3;");
    test_lexer("foo(a, b, c)");

    /* Evaluator tests */
    printf("--- expression evaluator ---\n");
    test_eval("2 + 3");
    test_eval("10 - 2 * 3");
    test_eval("(10 - 2) * 3");
    test_eval("100 / 5 % 3");
    test_eval("-5 + 3 * -(2 + 1)");
    test_eval("((4 + 6) * (3 + 2)) - 1");

    /* RPN evaluator test */
    printf("\n--- RPN evaluator ---\n");
    token_t rpn[] = {
        { TOK_NUMBER, 3, {0} },
        { TOK_NUMBER, 4, {0} },
        { TOK_PLUS,   0, {0} },
        { TOK_NUMBER, 2, {0} },
        { TOK_STAR,   0, {0} },
    };
    int rpn_result = evaluate_rpn(rpn, 5);
    printf("RPN: 3 4 + 2 * = %d\n", rpn_result);

    printf("\nDone.\n");
    return 0;
}
