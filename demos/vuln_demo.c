#include <stdio.h>
#include <string.h>

/* DELIBERATELY VULNERABLE: unbounded strcpy into a 16-byte stack buffer.
 * Used only to show how hardening reacts. Run it locally, never expose it. */
__attribute__((noinline))
static void copy_input(const char *input) {
    char buf[16];
    strcpy(buf, input);
    printf("copied: %s\n", buf);   /* use buf so it can't be optimized away */
}

int main(int argc, char **argv) {
    if (argc != 2) {
        fprintf(stderr, "usage: %s <input>\n", argv[0]);
        return 1;
    }
    copy_input(argv[1]);
    puts("returned normally");
    return 0;
}