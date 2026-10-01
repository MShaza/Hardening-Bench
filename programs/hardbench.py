#!/usr/bin/env python3
"""hardbench: build every program in programs/ in baseline and hardened configs,
then inspect each binary to verify which protections are really present."""
import re
import subprocess
import sys
from pathlib import Path

PROGRAMS_DIR = Path("programs")
BUILD_DIR = Path("build")

# All flags live here so later steps (benchmark, security demo) reuse them.
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

# Compiler (plus language-specific flags) chosen by source file extension.
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

    # Imported symbols named __xxx_chk (e.g. __memcpy_chk), excluding the stack canary.
    chk_syms = set(re.findall(r"\b__\w+_chk\b", dynsyms)) - {"__stack_chk_fail"}

    return {
        "pie": "DYN" in type_line,
        "canary": "__stack_chk_fail" in dynsyms,
        "relro": relro,
        "fortify": bool(chk_syms),
        "size_bytes": binary.stat().st_size,
    }


def main() -> None:
    sources = find_sources()
    if not sources:
        sys.exit(f"no .c or .cpp files found in {PROGRAMS_DIR}/")

    BUILD_DIR.mkdir(exist_ok=True)

    for src in sources:
        print(f"\n{src.name}")
        for cfg in CONFIGS:
            out = build(src, cfg, BUILD_DIR)
            info = inspect_binary(out)
            print(
                f"  {cfg:9} pie={info['pie']!s:5} canary={info['canary']!s:5} "
                f"relro={info['relro']:7} fortify={info['fortify']!s:5} "
                f"size={info['size_bytes']}"
            )


if __name__ == "__main__":
    main()