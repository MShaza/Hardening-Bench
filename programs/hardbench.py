#!/usr/bin/env python3
"""hardbench: build every program in programs/ in baseline and hardened configs."""
import subprocess
import sys
from pathlib import Path

PROGRAMS_DIR = Path("programs")
BUILD_DIR = Path("build")

# All flags live here so later steps (inspect, benchmark) reuse them.
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


def main() -> None:
    sources = find_sources()
    if not sources:
        sys.exit(f"no .c or .cpp files found in {PROGRAMS_DIR}/")

    BUILD_DIR.mkdir(exist_ok=True)

    for src in sources:
        for cfg in CONFIGS:
            out = build(src, cfg, BUILD_DIR)
            print(f"built {out}")


if __name__ == "__main__":
    main()