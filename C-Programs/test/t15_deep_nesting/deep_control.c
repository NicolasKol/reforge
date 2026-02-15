#include "nesting.h"

/*
 * deep_control.c — Functions with extreme control-flow nesting.
 *
 * Each function is designed to exceed the DEEP_NESTING threshold
 * (typically depth >= 6) and exercise multiple structural node types
 * simultaneously: if, for, while, do-while, switch, goto, labels.
 */

/*
 * deep_if_chain — 8-level nested if/else chain.
 * Classifies a 4-dimensional point into regions.
 * Nesting depth: ~8 (if inside if inside if...).
 * Structural nodes: if_statement, compound_statement, return_statement.
 */
int deep_if_chain(int a, int b, int c, int d) {
    if (a > 0) {
        if (b > 0) {
            if (c > 0) {
                if (d > 0) {
                    if (a + b > c + d) {
                        if (a * b > c * d) {
                            if ((a ^ b) > (c ^ d)) {
                                if (a % 2 == 0) {
                                    return 1;  /* class 1: all positive, even a */
                                } else {
                                    return 2;  /* class 2: all positive, odd a */
                                }
                            } else {
                                return 3;
                            }
                        } else {
                            return 4;
                        }
                    } else {
                        if (c - d > a - b) {
                            return 5;
                        } else {
                            return 6;
                        }
                    }
                } else {
                    if (a + b + c > 100) {
                        return 7;
                    } else {
                        return 8;
                    }
                }
            } else {
                return 9;
            }
        } else {
            return 10;
        }
    } else {
        if (b < 0 && c < 0) {
            if (d < 0) {
                return -1;  /* all negative */
            }
            return -2;
        }
        return 0;
    }
}

/*
 * deep_loop_nest — 4-level loop nest with inner conditionals.
 * Simulates a grid convolution with bounds checking.
 * Nesting: for > for > if > for > for > if = depth ~7.
 * Structural nodes: for_statement, if_statement, compound_statement.
 */
int deep_loop_nest(int grid[GRID_SIZE][GRID_SIZE]) {
    int result = 0;
    int kernel[3][3] = {
        {1, 2, 1},
        {2, 4, 2},
        {1, 2, 1}
    };

    for (int r = 0; r < GRID_SIZE; r++) {
        for (int c = 0; c < GRID_SIZE; c++) {
            if (r > 0 && r < GRID_SIZE - 1 && c > 0 && c < GRID_SIZE - 1) {
                int sum = 0;
                for (int kr = -1; kr <= 1; kr++) {
                    for (int kc = -1; kc <= 1; kc++) {
                        int val = grid[r + kr][c + kc];
                        if (val > 0) {
                            sum += val * kernel[kr + 1][kc + 1];
                        }
                    }
                }
                if (sum > result)
                    result = sum;
            }
        }
    }
    return result;
}

/*
 * deep_mixed_nest — mixes for/while/do/if/switch in one deep tower.
 * Nesting: for > while > if > switch > do > if > for = depth ~8+.
 * Exercises all loop + branch structural nodes together.
 */
int deep_mixed_nest(const int *data, int n) {
    int total = 0;

    for (int pass = 0; pass < 3; pass++) {
        int i = 0;
        while (i < n) {
            if (data[i] > 0) {
                switch (data[i] % 4) {
                case 0: {
                    int acc = 0;
                    do {
                        if (i < n && data[i] >= 0) {
                            for (int k = 0; k < data[i] && k < 5; k++) {
                                acc += k * pass;
                            }
                        }
                        i++;
                    } while (i < n && data[i] % 4 == 0);
                    total += acc;
                    break;
                }
                case 1: {
                    int mul = 1;
                    do {
                        if (data[i] > 1) {
                            mul *= data[i];
                            if (mul > 10000)
                                mul = 10000;
                        }
                        i++;
                    } while (i < n && data[i] % 4 == 1);
                    total += mul;
                    break;
                }
                case 2:
                    total += data[i] * 3;
                    i++;
                    break;
                default:
                    total -= data[i];
                    i++;
                    break;
                }
            } else {
                i++;
            }
        }
    }
    return total;
}

/*
 * deep_switch_nest — switch inside switch inside if inside loops.
 * Decodes a two-byte instruction (opcode + mode) with flag modifiers.
 * Nesting: if > switch > switch > if > for = depth ~7.
 * Exercises switch_statement deeply.
 */
int deep_switch_nest(int opcode, int mode, int flags) {
    int result = 0;

    if (opcode >= 0 && opcode < 8) {
        switch (opcode & 0x3) {
        case 0:
            switch (mode) {
            case 0:
                if (flags & 1) {
                    for (int i = 0; i < 4; i++) {
                        result += i * opcode;
                    }
                } else {
                    result = opcode + mode;
                }
                break;
            case 1:
                if (flags & 2) {
                    for (int i = 0; i < 3; i++) {
                        if (i % 2 == 0)
                            result += flags;
                        else
                            result -= flags;
                    }
                }
                break;
            default:
                result = mode * 7;
                break;
            }
            break;

        case 1:
            switch (mode) {
            case 0:
                result = opcode * 11;
                break;
            case 1:
                if (flags > 0) {
                    do {
                        result += flags;
                        flags >>= 1;
                    } while (flags > 0);
                }
                break;
            default:
                result = -1;
                break;
            }
            break;

        case 2:
            result = opcode ^ mode ^ flags;
            break;

        default:
            result = opcode + mode + flags;
            break;
        }
    }
    return result;
}
