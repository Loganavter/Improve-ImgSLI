#!/usr/bin/env python3
"""Compile every GLSL shader pair found under src/ into Qt's .qsb format.

Run from repo root:

    python3 src/devtools/compile_shaders.py            # compile everything
    python3 src/devtools/compile_shaders.py --check    # exit non-zero if any .qsb is stale
    python3 src/devtools/compile_shaders.py --clean    # remove .qsb files and exit

Looks for *.vert / *.frag files under src/ and emits a sibling *.qsb file
for each. The .qsb files are committed to the repo — that way runtime does
not need qsb installed, only Qt itself.

Inline shader strings (those defined as Python triple-quoted strings inside
gl_passes.py modules) are not in scope here. As the QRhi migration progresses,
those inline shaders will be moved to standalone .vert/.frag files so this
script can compile them.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"

# Targets — covers desktop OpenGL 3.3+, OpenGL ES 3.0+, D3D11 (SM 5.0),
# Metal 1.2+. SPIR-V (the canonical RHI intermediate) is emitted by qsb
# automatically.
#
# Do NOT add GLSL 120/130: sources use #version 440 / UBO layouts that cannot
# target those profiles. Legacy Windows OpenGL must fall back to D3D11 instead
# (see ui.widgets.canvas.rhi_backend.resolve_rhi_backend_with_fallback).
DEFAULT_TARGETS = [
    "--glsl", "330,300 es",
    "--hlsl", "50",
    "--msl", "12",
]


def find_qsb() -> str:
    candidates = [
        "qsb",
        "/usr/lib/qt6/bin/qsb",
        "/usr/local/lib/qt6/bin/qsb",
    ]
    for candidate in candidates:
        resolved = shutil.which(candidate) or (candidate if Path(candidate).is_file() else None)
        if resolved:
            return resolved
    raise SystemExit(
        "qsb not found. Install qt6-shadertools (Arch: pacman -S qt6-shadertools) "
        "or PySide6 with the shadertools extra."
    )


def find_shader_sources() -> list[Path]:
    return sorted(
        path
        for path in SRC_ROOT.rglob("*")
        if path.suffix in {".vert", ".frag"} and path.is_file()
    )


def out_path_for(src: Path) -> Path:
    return src.with_suffix(src.suffix + ".qsb")


def is_stale(src: Path, dst: Path) -> bool:
    if not dst.exists():
        return True
    return src.stat().st_mtime > dst.stat().st_mtime


def compile_one(qsb: str, src: Path) -> int:
    dst = out_path_for(src)
    cmd = [qsb, *DEFAULT_TARGETS, "-o", str(dst), str(src)]
    print(f"  qsb {src.relative_to(REPO_ROOT)} -> {dst.name}")
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        sys.stderr.write(proc.stdout)
        sys.stderr.write(proc.stderr)
        return proc.returncode
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Exit non-zero if any .qsb is stale; do not write.")
    parser.add_argument("--clean", action="store_true", help="Remove all .qsb files under src/ and exit.")
    args = parser.parse_args()

    if args.clean:
        removed = 0
        for path in SRC_ROOT.rglob("*.qsb"):
            path.unlink()
            removed += 1
        print(f"Removed {removed} .qsb file(s).")
        return 0

    qsb = find_qsb()
    print(f"Using qsb: {qsb}")
    sources = find_shader_sources()
    if not sources:
        print(f"No .vert/.frag files found under {SRC_ROOT.relative_to(REPO_ROOT)}/ (yet).")
        return 0

    if args.check:
        stale = [s for s in sources if is_stale(s, out_path_for(s))]
        if stale:
            print("Stale .qsb files:", file=sys.stderr)
            for s in stale:
                print(f"  {s.relative_to(REPO_ROOT)}", file=sys.stderr)
            return 1
        print(f"All {len(sources)} shader(s) up to date.")
        return 0

    print(f"Compiling {len(sources)} shader(s):")
    failed = 0
    for src in sources:
        rc = compile_one(qsb, src)
        if rc != 0:
            failed += 1
    if failed:
        print(f"\n{failed} shader(s) failed to compile.", file=sys.stderr)
        return 1
    print(f"\nAll {len(sources)} shader(s) compiled successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
