#include <cstddef>
#include <cstdint>
#include <iostream>
#include <utility>
#include <vector>

constexpr std::size_t N = 4'000'000;
constexpr int ROUNDS = 3;

// Deterministic LCG: unsigned overflow wraps by definition (signed overflow is UB)
static std::uint32_t lcg_state = 0;

static std::uint32_t lcg_next() {
    lcg_state = lcg_state * 1664525u + 1013904223u;
    return lcg_state;
}

static void quicksort(std::uint32_t *arr, long lo, long hi) {
    while (lo < hi) {
        std::uint32_t pivot = arr[lo + (hi - lo) / 2];
        long i = lo, j = hi;
        while (i <= j) {
            while (arr[i] < pivot) i++;
            while (arr[j] > pivot) j--;
            if (i <= j) {
                std::swap(arr[i], arr[j]);
                i++;
                j--;
            }
        }
        // Recurse on the smaller half, loop on the larger: bounded stack depth
        if (j - lo < hi - i) {
            quicksort(arr, lo, j);
            lo = i;
        } else {
            quicksort(arr, i, hi);
            hi = j;
        }
    }
}

// FNV-1a style: order-dependent, so a broken sort changes the result
static std::uint64_t checksum(const std::uint32_t *arr, std::size_t n) {
    std::uint64_t h = 1469598103934665603ull;
    for (std::size_t i = 0; i < n; i++) {
        h ^= arr[i];
        h *= 1099511628211ull;
    }
    return h;
}

int main() {
    std::vector<std::uint32_t> data(N);
    std::uint64_t total = 0;

    for (int r = 0; r < ROUNDS; r++) {
        lcg_state = 12345u + static_cast<std::uint32_t>(r);  // fixed seed per round
        for (std::size_t i = 0; i < N; i++) data[i] = lcg_next();

        quicksort(data.data(), 0, static_cast<long>(N) - 1);

        for (std::size_t i = 1; i < N; i++) {
            if (data[i - 1] > data[i]) {
                std::cerr << "NOT SORTED\n";
                return 2;
            }
        }
        total ^= checksum(data.data(), N);
    }

    std::cout << "sort_bench checksum: " << total << "\n";
    return 0;
}