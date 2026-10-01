#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <iostream>

constexpr int ITERS = 10'000'000;

// Same deterministic LCG as sort_bench
static std::uint32_t lcg_state = 777;

static std::uint32_t lcg_next() {
    lcg_state = lcg_state * 1664525u + 1013904223u;
    return lcg_state;
}

int main() {
    char src[256];
    char dst[256];
    char num[32];
    char copy[32];

    for (int i = 0; i < 255; i++) src[i] = static_cast<char>('a' + lcg_next() % 26);
    src[255] = '\0';

    std::uint64_t h = 1469598103934665603ull;

    for (int it = 0; it < ITERS; it++) {
        // Runtime length, always 1..200, so it always fits in dst[256]
        std::size_t n = 1 + (lcg_next() % 200);
        std::memcpy(dst, src, n);
        dst[n] = '\0';

        // Format a number, then strcpy it: both are fortifiable calls
        std::snprintf(num, sizeof num, "%u", lcg_next());
        std::strcpy(copy, num);

        h ^= static_cast<unsigned char>(dst[n - 1]);
        h ^= static_cast<unsigned char>(dst[n / 2]);
        h ^= std::strlen(copy);
        h *= 1099511628211ull;
    }

    std::cout << "string_bench checksum: " << h << "\n";
    return 0;
}