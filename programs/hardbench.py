#!/usr/bin/env python3
"""hardbench: build programs in baseline and hardened configs, verify the
protections in the ELF, and compare correctness, runtime and size."""
import argparse
import os
import re
import shutil
import statistics
import subprocess
import sys
import time
from pathlib import Path

PROGRAMS_DIR = Path("programs")
BUILD_DIR = Path("build")

CONFIGS = {
    "baseline": [
        "-O2",
        "-fno-stack-protector",
        "-no-pie",
        "-U_FORTIFY_SOURCE",
        "-Wl,-z,norelro",
    ],
    "hardened": [
        "-O2",
        "-fstack-protector-strong",
        "-fPIE",
        "-pie",
        "-D_FORTIFY_SOURCE=2",
        "-Wl,-z,relro,-z,now",
    ],
}

COMPILERS = {
    ".c": ["gcc"],
    ".cpp": ["g++", "-std=c++17"],
}


def build(src: Path, cfg: str, outdir: Path) -> Path:
    """Compile one source file with one config. Exit with a clear error on failure."""
    out = outdir / f"{src.stem}.{cfg}"
    cmd = [*COMPILERS[src.suffix], *CONFIGS[cfg], str(src), "-o", str(out)]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
    except FileNotFoundError:
        sys.exit(f"compiler not found: {cmd[0]} (is build-essential installed?)")

    if result.returncode != 0:
        sys.exit(
            f"build failed: {src.name} [{cfg}]\n"
            f"command: {' '.join(cmd)}\n"
            f"{result.stderr}"
        )
    return out


def find_sources() -> list[Path]:
    """Return .c and .cpp files in programs/, sorted for stable order."""
    return sorted(p for p in PROGRAMS_DIR.iterdir() if p.suffix in COMPILERS)


def readelf(flags: list[str], binary: Path) -> str:
    """Run readelf and return its text output. Exit clearly on failure."""
    cmd = ["readelf", *flags, str(binary)]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
    except FileNotFoundError:
        sys.exit("readelf not found (is binutils installed?)")
    if result.returncode != 0:
        sys.exit(f"readelf failed on {binary}: {result.stderr}")
    return result.stdout


def inspect_binary(binary: Path) -> dict:
    """Read protections straight from the ELF file, not from the flags we passed."""
    header = readelf(["-h"], binary)
    segments = readelf(["-lW"], binary)
    dynamic = readelf(["-dW"], binary)
    dynsyms = readelf(["--dyn-syms", "-W"], binary)

    type_line = next(
        (l for l in header.splitlines() if l.strip().startswith("Type:")), ""
    )
    has_relro_segment = "GNU_RELRO" in segments
    bind_now = (
        "BIND_NOW" in dynamic
        or re.search(r"FLAGS_1.*\bNOW\b", dynamic) is not None
    )

    if has_relro_segment and bind_now:
        relro = "full"
    elif has_relro_segment:
        relro = "partial"
    else:
        relro = "none"

    chk_syms = set(re.findall(r"\b__\w+_chk\b", dynsyms)) - {"__stack_chk_fail"}

    return {
        "pie": "DYN" in type_line,
        "canary": "__stack_chk_fail" in dynsyms,
        "relro": relro,
        "fortify": bool(chk_syms),
        "size_bytes": binary.stat().st_size,
    }


# ---------------------------------------------------------------- benchmarking

def pin_prefix() -> list[str]:
    """Pin runs to one CPU core (if taskset exists) to reduce timing noise."""
    if shutil.which("taskset") is None:
        return []
    cpu = max(os.sched_getaffinity(0))
    return ["taskset", "-c", str(cpu)]


def run_once(binary: Path, prefix: list[str]) -> tuple[str, int, float]:
    """Run a binary once. Return (stdout, exit code, wall time in seconds)."""
    start = time.perf_counter()
    result = subprocess.run(
        [*prefix, str(binary)], capture_output=True, text=True
    )
    elapsed = time.perf_counter() - start
    return result.stdout, result.returncode, elapsed


def benchmark_pair(bins: dict[str, Path], runs: int) -> dict:
    """Run every config's binary `runs` times, interleaved, after one warm-up.

    Interleaving (baseline, hardened, baseline, hardened, ...) means thermal
    drift and background load affect both configs equally.
    """
    prefix = pin_prefix()
    outputs = {cfg: set() for cfg in bins}
    times = {cfg: [] for cfg in bins}

    for cfg, b in bins.items():          # warm-up: not timed
        run_once(b, prefix)

    for _ in range(runs):
        for cfg, b in bins.items():
            out, rc, dt = run_once(b, prefix)
            outputs[cfg].add((out, rc))
            times[cfg].append(dt)

    return {"outputs": outputs, "times": times}


def check_correctness(outputs: dict) -> tuple[bool, str]:
    """All runs of all configs must give the same stdout and exit code 0."""
    all_results = set().union(*outputs.values())
    if len(all_results) != 1:
        return False, f"outputs differ: {sorted(all_results)}"
    (out, rc), = all_results
    if rc != 0:
        return False, f"non-zero exit code {rc}"
    return True, "identical output, exit code 0"


def median_and_stdev(values: list[float]) -> tuple[float, float]:
    sd = statistics.stdev(values) if len(values) > 1 else 0.0
    return statistics.median(values), sd


def pct(new: float, old: float) -> float:
    return (new / old - 1) * 100


# ------------------------------------------------------------------------ main

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=15, help="timed runs per config")
    args = parser.parse_args()

    sources = find_sources()
    if not sources:
        sys.exit(f"no .c or .cpp files found in {PROGRAMS_DIR}/")

    BUILD_DIR.mkdir(exist_ok=True)
    all_ok = True

    for src in sources:
        print(f"\n{src.name}")
        bins = {cfg: build(src, cfg, BUILD_DIR) for cfg in CONFIGS}
        info = {cfg: inspect_binary(b) for cfg, b in bins.items()}

        for cfg in CONFIGS:
            i = info[cfg]
            print(
                f"  {cfg:9} pie={i['pie']!s:5} canary={i['canary']!s:5} "
                f"relro={i['relro']:7} fortify={i['fortify']!s:5} "
                f"size={i['size_bytes']}"
            )

        result = benchmark_pair(bins, args.runs)
        ok, msg = check_correctness(result["outputs"])
        all_ok &= ok
        print(f"  correctness: {'OK' if ok else 'FAIL'} ({msg})")

        base_med, base_sd = median_and_stdev(result["times"]["baseline"])
        hard_med, hard_sd = median_and_stdev(result["times"]["hardened"])
        size_pct = pct(info["hardened"]["size_bytes"], info["baseline"]["size_bytes"])
        print(f"  baseline  median {base_med:.3f}s  stdev {base_sd:.3f}s")
        print(f"  hardened  median {hard_med:.3f}s  stdev {hard_sd:.3f}s")
        print(
            f"  overhead: time {pct(hard_med, base_med):+.1f}%  "
            f"size {size_pct:+.1f}%  ({args.runs} runs, interleaved)"
        )

    if not all_ok:
        sys.exit("\nFAILED: at least one program behaved differently when hardened")


if __name__ == "__main__":
    main()