#!/usr/bin/env python3
"""Compile every GLSL shader pair found under src/ into Qt's .qsb format.

Run from repo root:

    python3 src/devtools/compile_shaders.py                   # compile everything
    python3 src/devtools/compile_shaders.py --check           # exit non-zero if any .qsb is stale or lacks DXBC
    python3 src/devtools/compile_shaders.py --verify-variants # audit committed .qsb variant lists only
    python3 src/devtools/compile_shaders.py --clean           # remove .qsb files and exit

Looks for *.vert / *.frag files under src/ and emits a sibling *.qsb file
for each. The .qsb files are committed to the repo — that way runtime does
not need qsb installed, only Qt itself.

DXBC, not HLSL source
----------------------
Every .qsb is baked with qsb's ``-c`` (``--fxc``) flag, so the D3D11 variant
is stored as compiled bytecode (``QShader::DxbcShader``) instead of HLSL
source. qrhid3d11 looks up ``{QShader::DxbcShader, 50}`` first and only falls
back to HLSL source + a D3DCompile call, so an HLSL-only .qsb makes every
cold D3D11 pipeline creation pay a shader compile (~4 s per canvas, measured
2026-10-25). Baking DXBC moves that cost to this script.

That makes ``fxc.exe`` a build-host requirement (Windows SDK 8.1+ x64; on Linux
run it under wine behind a ``fxc`` shim on PATH — see
``docs/dev/rendering/overview.md`` § Shader compilation). The script refuses to
bake when fxc is unavailable, rather than silently shipping an HLSL-only .qsb.

Some shaders are too heavy for qsb's own compile window: qsb runs the external
compiler with a FIXED 30 s timeout (``QProcess::waitForFinished()`` with no
argument) and still exits 0 when it fires, so a legitimate multi-minute fxc
build can never be baked through ``qsb -c``. For such a pack the script falls
back to an out-of-band path instead of exempting it: extract the HLSL qsb already
wrote (``qsb -x hlsl,50``), mark every loop ``[loop]`` (an unroll guard —
semantics unchanged; measured on ``magnifier/.../mag.frag``: >20 min unbounded
versus 5.5 s with the hints), compile it with fxc directly under a generous
timeout, then add the bytecode back with qsb's documented
``-r dxbc,50,<file>`` mode (never by editing bytes) and re-check the variant.
The fallback is automatic, prints a ``slow-path`` line with the measured fxc
time, and is not a weaker guarantee: same fxc, no 30 s wall.

Inline shader strings (those defined as Python triple-quoted strings inside
gl_passes.py modules) are not in scope here. As the QRhi migration progresses,
those inline shaders will be moved to standalone .vert/.frag files so this
script can compile them.
"""

from __future__ import annotations

import argparse
import hashlib
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
# (see ui.canvas_infra.rhi.rhi_backend.resolve_rhi_backend_with_fallback).
DEFAULT_TARGETS = [
    "--glsl", "330,300 es",
    "--hlsl", "50",
    "--msl", "12",
]

# qsb's -c/--fxc: store DXBC bytecode for the --hlsl variant instead of HLSL
# source. Keep this out of DEFAULT_TARGETS so `--help` text and the target list
# stay readable; compile_one concatenates it.
DXBC_FLAG = "-c"

# The D3D11 backend's first lookup key (qrhid3d11.cpp): compiled SM 5.0
# bytecode. A .qsb without it forces a runtime D3DCompile per pipeline create.
DXBC_SOURCE_NAME = "DxbcShader"
DXBC_VERSION = 50

# Deliberate, visible exceptions to the DXBC requirement. Keyed by repo-relative
# .qsb path; the value is (reason, content pin). Only a pack that genuinely
# cannot be baked on any available bake host belongs here — an entry is a known
# runtime D3DCompile cost plus a follow-up, never a convenience switch.
#
# The slow path below (loop hints + out-of-band fxc + `qsb -r`) removed the only
# entry this list ever had; keep the mechanism for a future pack that even that
# path cannot compile, but do not reach for it while the slow path can run.
#
# The pin is "<byte size>:<sha256[:16]>" of the exempted pack (see
# pack_fingerprint). A content change invalidates the entry so the reason is
# re-verified rather than silently inherited; refresh it only after re-reading
# the reason and re-baking on a host where the bake works.
DXBC_EXEMPT: dict[str, tuple[str, str]] = {}

FXC_REQUIREMENT = """\
DXBC baking requires fxc.exe (the HLSL compiler from the Windows SDK 8.1+ x64).

  Windows: install the SDK (or the standalone DirectX Shader Compiler) and put
           ...\\Windows Kits\\10\\bin\\<ver>\\x64 on PATH; qsb invokes `fxc`.
  Linux:   run Microsoft's fxc.exe under wine behind an executable named `fxc`
           on PATH, e.g.
             WINEPREFIX=<prefix> WINEDEBUG=-all \\
             PATH=<shim-dir>:$PATH python3 src/devtools/compile_shaders.py

Refusing to bake an HLSL-only .qsb: D3D11 would then run D3DCompile at every
pipeline creation instead of loading the baked DXBC (~4 s per canvas).\
"""


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


def find_fxc() -> str | None:
    """Locate the fxc front-end qsb shells out to (PATH lookup, like qsb)."""
    for candidate in ("fxc", "fxc.exe"):
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    return None


def require_fxc() -> str:
    fxc = find_fxc()
    if not fxc:
        raise SystemExit(FXC_REQUIREMENT)
    return fxc


# qsb's external-compiler window is fixed at 30 s (QProcess::waitForFinished()
# default, no override in qsb.cpp) and qsb exits 0 when it fires. The slow path
# keeps no window at all: fxc gets this budget instead.
FXC_SLOW_TIMEOUT_S = 900

# HLSL unroll guard. "[loop]" tells fxc to keep the loop instead of unrolling
# it; semantics are unchanged. Without it fxc's optimiser explodes on nested
# sampling loops (measured on the magnifier fragment shader: >20 min unbounded
# versus 5.5 s with the hints).
LOOP_HINT = "[loop]"

_FXC_PROFILE_BY_SUFFIX = {".vert": "vs_5_0", ".frag": "ps_5_0"}


def loop_hint_hlsl(hlsl: str) -> tuple[str, int]:
    """Return *hlsl* with ``[loop]`` before every for/while loop, plus the count.

    Used only on the slow path, i.e. for a shader whose unrolled build does not
    finish inside qsb's window.
    """
    out: list[str] = []
    hinted = 0
    for line in hlsl.splitlines():
        stripped = line.lstrip()
        if stripped.startswith(("for (", "for(", "while (", "while(")):
            out.append(line[: len(line) - len(stripped)] + LOOP_HINT)
            hinted += 1
        out.append(line)
    return "\n".join(out) + "\n", hinted


def fxc_profile_for(src: Path) -> str:
    try:
        return _FXC_PROFILE_BY_SUFFIX[src.suffix]
    except KeyError:
        raise SystemExit(f"{src}: no fxc profile for suffix {src.suffix!r} (slow path)")


def extract_hlsl(qsb: str, pack: Path, dest: Path) -> int:
    """Write the pack's HLSL source to *dest* with qsb's extract mode."""
    proc = subprocess.run(
        [qsb, "-x", f"hlsl,{DXBC_VERSION}", "-o", str(dest), str(pack)],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0 or not dest.is_file():
        sys.stderr.write(proc.stdout)
        sys.stderr.write(proc.stderr)
        return proc.returncode or 1
    return 0


def compile_slow(qsb: str, fxc: str, src: Path, pack: Path) -> int:
    """Bake *pack* when qsb's 30 s compiler window is too short (module docs).

    The bytecode still comes from fxc; it is added back with qsb's documented
    ``-r`` mode (add a target that was not present before), never by editing
    the pack's bytes.
    """
    import tempfile
    import time

    rel = pack.relative_to(REPO_ROOT).as_posix()
    profile = fxc_profile_for(src)
    elapsed = 0.0
    count = 0
    with tempfile.TemporaryDirectory(prefix="qsb-slow-") as tmp:
        tmp_pack = Path(tmp) / pack.name
        tmp_pack.write_bytes(pack.read_bytes())
        hlsl_path = Path(tmp) / "shader.hlsl"
        if extract_hlsl(qsb, tmp_pack, hlsl_path) != 0:
            sys.stderr.write(f"  slow-path: could not extract HLSL from {rel}\n")
            return 1
        hinted, count = loop_hint_hlsl(hlsl_path.read_text(encoding="utf-8"))
        hlsl_path.write_text(hinted, encoding="utf-8")
        dxbc_path = Path(tmp) / "shader.dxbc"
        started = time.monotonic()
        try:
            proc = subprocess.run(
                [fxc, "/nologo", "/E", "main", "/T", profile, "/Fo", str(dxbc_path), str(hlsl_path)],
                capture_output=True,
                text=True,
                timeout=FXC_SLOW_TIMEOUT_S,
            )
        except subprocess.TimeoutExpired:
            sys.stderr.write(
                f"  slow-path: fxc exceeded {FXC_SLOW_TIMEOUT_S} s even with {count} "
                f"{LOOP_HINT} hint(s) on {rel}\n"
            )
            return 1
        elapsed = time.monotonic() - started
        if proc.returncode != 0 or not dxbc_path.is_file():
            sys.stderr.write(proc.stdout)
            sys.stderr.write(proc.stderr)
            sys.stderr.write(f"  slow-path: fxc failed on {rel}\n")
            return 1
        # `qsb -r` edits the pack in place (it ignores -o), so work on a copy and
        # only replace the committed file after the variant check passes.
        rep = subprocess.run(
            [qsb, str(tmp_pack), "-r", f"dxbc,{DXBC_VERSION},{dxbc_path}"],
            capture_output=True,
            text=True,
        )
        if rep.returncode != 0:
            sys.stderr.write(rep.stdout)
            sys.stderr.write(rep.stderr)
            sys.stderr.write(f"  slow-path: qsb -r failed on {rel}\n")
            return 1
        if not has_dxbc(variant_list(tmp_pack)):
            sys.stderr.write(f"  slow-path: {rel} still lacks {DXBC_SOURCE_NAME} v{DXBC_VERSION}\n")
            return 1
        shutil.copyfile(tmp_pack, pack)
    print(
        f"  slow-path: {rel} baked out-of-band (fxc {elapsed:.1f} s, {count} {LOOP_HINT} hint(s); "
        f"qsb's 30 s window bypassed with -r)"
    )
    return 0


def find_shader_sources() -> list[Path]:
    return sorted(
        path
        for path in SRC_ROOT.rglob("*")
        if path.suffix in {".vert", ".frag"} and path.is_file()
    )


def find_committed_qsb() -> list[Path]:
    return sorted(SRC_ROOT.rglob("*.qsb"))


def out_path_for(src: Path) -> Path:
    return src.with_suffix(src.suffix + ".qsb")


def is_stale(src: Path, dst: Path) -> bool:
    if not dst.exists():
        return True
    return src.stat().st_mtime > dst.stat().st_mtime


def variant_list(path: Path) -> list[tuple[str, int]]:
    """Return [(source-name, version), ...] for a serialized .qsb.

    Requires PySide6 (a hard runtime dependency of the app), so this works with
    both the venv interpreter and the system python3. Raises SystemExit on an
    unreadable/invalid file — a corrupt .qsb is a failure, not a skip.
    """
    try:
        from PySide6.QtGui import QShader
    except ImportError as exc:  # pragma: no cover - environment guard
        raise SystemExit(
            f"PySide6 is required to inspect .qsb variants ({exc}). "
            "Run this script with the app's interpreter."
        ) from exc

    shader = QShader.fromSerialized(path.read_bytes())
    if not shader.isValid():
        raise SystemExit(f"{path}: not a valid serialized QShader")
    return [
        (key.source().name, int(key.sourceVersion().version()))
        for key in shader.availableShaders()
    ]


def has_dxbc(variants: list[tuple[str, int]]) -> bool:
    return (DXBC_SOURCE_NAME, DXBC_VERSION) in variants


def format_variants(variants: list[tuple[str, int]]) -> str:
    return ", ".join(f"{name} v{version}" for name, version in variants)


def pack_fingerprint(path: Path) -> str:
    """Content pin for an exempted pack: size + short sha256 (cheap, stable)."""
    data = path.read_bytes()
    return f"{len(data)}:{hashlib.sha256(data).hexdigest()[:16]}"


def validate_exemptions(committed: list[Path]) -> list[str]:
    """Check that DXBC_EXEMPT entries are live and still describe the same pack."""
    present = {path.relative_to(REPO_ROOT).as_posix() for path in committed}
    problems: list[str] = []
    for rel, (reason, pin) in DXBC_EXEMPT.items():
        if rel not in present:
            problems.append(f"{rel}: listed in DXBC_EXEMPT but no such .qsb exists (drop the entry)")
            continue
        actual = pack_fingerprint(REPO_ROOT / rel)
        if actual != pin:
            problems.append(
                f"{rel}: exempt pack changed (pinned {pin}, now {actual}); re-read the reason "
                f"({reason}) and update DXBC_EXEMPT only if it still holds"
            )
    return problems


def verify_variants(*, verbose: bool = True) -> int:
    """Audit every committed .qsb; return the number of files that fail the DXBC rule."""
    files = find_committed_qsb()
    if not files:
        print(f"No .qsb files found under {SRC_ROOT.relative_to(REPO_ROOT)}/.", file=sys.stderr)
        return 1

    missing: list[Path] = []
    exempted = 0
    for path in files:
        variants = variant_list(path)
        rel = path.relative_to(REPO_ROOT).as_posix()
        exemption = DXBC_EXEMPT.get(rel)
        if exemption is not None:
            # Visible exception: printed with its reason, never counted missing.
            exempted += 1
            if verbose:
                print(f"EXEMPT {rel} {exemption[0]} (variants: {format_variants(variants)})")
            continue
        if verbose:
            status = "ok" if has_dxbc(variants) else f"MISSING {DXBC_SOURCE_NAME} v{DXBC_VERSION}"
            print(f"  {rel}: {format_variants(variants)}  [{status}]")
        if not has_dxbc(variants):
            missing.append(path)

    problems = validate_exemptions(files)

    if missing:
        print(
            f"\n{len(missing)} of {len(files)} .qsb file(s) lack {DXBC_SOURCE_NAME} "
            f"v{DXBC_VERSION} (D3D11 would D3DCompile at runtime):",
            file=sys.stderr,
        )
        for path in missing:
            print(f"  {path.relative_to(REPO_ROOT).as_posix()}", file=sys.stderr)
    if problems:
        print("\nDXBC_EXEMPT problem(s):", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
    if missing or problems:
        return len(missing) + len(problems)

    baked = len(files) - exempted
    if exempted:
        pins = ", ".join(pin for _rel, (_reason, pin) in DXBC_EXEMPT.items())
        print(
            f"{baked} regular pack(s) carry {DXBC_SOURCE_NAME} v{DXBC_VERSION}; "
            f"{exempted} exempt (pinned {pins})."
        )
    else:
        print(f"All {len(files)} .qsb file(s) carry {DXBC_SOURCE_NAME} v{DXBC_VERSION}.")
    return 0


def compile_one(qsb: str, fxc: str, src: Path) -> int:
    dst = out_path_for(src)
    cmd = [qsb, *DEFAULT_TARGETS, DXBC_FLAG, "-o", str(dst), str(src)]
    print(f"  qsb {src.relative_to(REPO_ROOT)} -> {dst.name}")
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        sys.stderr.write(proc.stdout)
        sys.stderr.write(proc.stderr)
        return proc.returncode
    # qsb can succeed while silently omitting the DXBC variant: fxc vanished
    # between the preflight and the bake, or (the usual cause) the shader needs
    # longer than qsb's fixed 30 s compiler window. Retry out-of-band before
    # declaring failure; never leave an HLSL-only .qsb behind.
    if not has_dxbc(variant_list(dst)):
        print(
            f"  no {DXBC_SOURCE_NAME} v{DXBC_VERSION} from qsb "
            f"({dst.relative_to(REPO_ROOT)}); retrying with the slow path"
        )
        if compile_slow(qsb, fxc, src, dst) == 0:
            return 0
        sys.stderr.write(
            f"  {dst.relative_to(REPO_ROOT)}: neither qsb nor the slow path produced "
            f"{DXBC_SOURCE_NAME} v{DXBC_VERSION}; refusing to keep an HLSL-only .qsb.\n"
            f"{FXC_REQUIREMENT}\n"
        )
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit non-zero if any .qsb is stale or lacks a DXBC v50 variant; do not write.",
    )
    parser.add_argument(
        "--verify-variants",
        action="store_true",
        help="Print every committed .qsb with its variant list; exit non-zero if DXBC v50 is missing.",
    )
    parser.add_argument("--clean", action="store_true", help="Remove all .qsb files under src/ and exit.")
    args = parser.parse_args()

    if args.clean:
        removed = 0
        for path in SRC_ROOT.rglob("*.qsb"):
            path.unlink()
            removed += 1
        print(f"Removed {removed} .qsb file(s).")
        return 0

    if args.verify_variants:
        return verify_variants()

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
        if verify_variants(verbose=False):
            return 1
        return 0

    fxc = require_fxc()
    print(f"Using fxc: {fxc}")
    print(f"Compiling {len(sources)} shader(s) with DXBC baking (-c):")
    failed = 0
    skipped = 0
    for src in sources:
        rel = out_path_for(src).relative_to(REPO_ROOT).as_posix()
        exemption = DXBC_EXEMPT.get(rel)
        if exemption is not None:
            print(f"  skip {rel} (DXBC_EXEMPT: {exemption[0]})")
            skipped += 1
            continue
        rc = compile_one(qsb, fxc, src)
        if rc != 0:
            failed += 1
    if failed:
        print(f"\n{failed} shader(s) failed to compile.", file=sys.stderr)
        return 1
    detail = f" ({skipped} exempt, not baked here)" if skipped else ""
    print(f"\nAll {len(sources) - skipped} shader(s) compiled successfully{detail}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
