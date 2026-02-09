// neg_inline_user.c
static inline int helper(int x) { return x * 7 + 3; }

int main(void) {
    return helper(5);
}
