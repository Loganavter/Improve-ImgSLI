"""Driver for the cross-language widget parity tester.

Walks ``cases.json``; for each visual case runs both renderers, computes
the per-pixel mean absolute difference, and fails if it exceeds the
case's threshold. For each query case runs both renderers, compares
stdout.

Both sides MUST agree because both are Qt on the same machine — Python
``sli_ui_toolkit`` is a Qt6 layer and C++ ``sli::toolkit`` is a Qt6
layer. Any sustained pixel divergence is a port bug, not a font /
DPI / theme artefact.

Required env vars (CMake sets them):
    IMGSLI_PARITY_CASES     absolute path to cases.json
    IMGSLI_PARITY_CPP       absolute path to parity_renderer executable
    IMGSLI_PARITY_PYTHON    optional, defaults to current python3
    IMGSLI_PARITY_PYRENDER  absolute path to python_renderer.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    from PIL import Image
except ImportError:  # PIL is the simplest cross-process PNG reader; bail out
    # gracefully so the test is clearly diagnosable rather than mysteriously
    # crashing on import.
    print("run_parity: Pillow is required to compare PNGs. Install with "
          "`pip install Pillow`.", file=sys.stderr)
    sys.exit(2)


def _env(name: str, required: bool = True) -> str | None:
    v = os.environ.get(name)
    if required and not v:
        print(f"run_parity: env var {name} must be set", file=sys.stderr)
        sys.exit(2)
    return v


def _mean_abs_diff(a_path: Path, b_path: Path) -> float:
    a = Image.open(a_path).convert("RGBA")
    b = Image.open(b_path).convert("RGBA")
    if a.size != b.size:
        return float("inf")
    total = 0
    count = 0
    for ap, bp in zip(a.getdata(), b.getdata()):
        for ch in range(4):
            total += abs(ap[ch] - bp[ch])
            count += 1
    return total / count if count else 0.0


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


def _render(renderer: list[str], case_id: str, out: Path) -> None:
    proc = _run(renderer + ["--mode", "render", "--case", case_id,
                            "--output", str(out)])
    if proc.returncode != 0:
        raise RuntimeError(
            f"renderer failed for case {case_id}: rc={proc.returncode}\n"
            f"stdout: {proc.stdout}\nstderr: {proc.stderr}"
        )


def _query(renderer: list[str], case_id: str) -> str:
    proc = _run(renderer + ["--mode", "query", "--case", case_id])
    if proc.returncode != 0:
        raise RuntimeError(
            f"renderer query failed for case {case_id}: rc={proc.returncode}\n"
            f"stdout: {proc.stdout}\nstderr: {proc.stderr}"
        )
    return proc.stdout.strip()


def main() -> int:
    cases_path = Path(_env("IMGSLI_PARITY_CASES"))
    cpp_exe = _env("IMGSLI_PARITY_CPP")
    py_script = _env("IMGSLI_PARITY_PYRENDER")
    py_exe = os.environ.get("IMGSLI_PARITY_PYTHON") or sys.executable

    cpp_renderer = [cpp_exe]
    py_renderer = [py_exe, py_script]

    with open(cases_path, "r", encoding="utf-8") as f:
        corpus = json.load(f)

    failures: list[str] = []
    visual_cases = corpus.get("cases", [])
    query_cases = corpus.get("queries", [])

    with tempfile.TemporaryDirectory(prefix="imgsli-parity-") as tmpdir:
        tmp = Path(tmpdir)
        for case in visual_cases:
            cid = case["id"]
            diff_max = float(case.get("diff_max_per_pixel", 0.0))
            py_png = tmp / f"{cid}.python.png"
            cpp_png = tmp / f"{cid}.cpp.png"
            try:
                _render(py_renderer, cid, py_png)
                _render(cpp_renderer, cid, cpp_png)
            except RuntimeError as exc:
                failures.append(f"[render] {cid}: {exc}")
                continue
            diff = _mean_abs_diff(py_png, cpp_png)
            if diff > diff_max:
                # Persist the failing pair under build/parity_failures/ so
                # the developer can eyeball the divergence after the test.
                keep = Path(os.environ.get("IMGSLI_PARITY_KEEP",
                                            tmp.parent / "parity_failures"))
                keep.mkdir(parents=True, exist_ok=True)
                (keep / py_png.name).write_bytes(py_png.read_bytes())
                (keep / cpp_png.name).write_bytes(cpp_png.read_bytes())
                failures.append(
                    f"[visual] {cid}: mean diff {diff:.2f} > threshold "
                    f"{diff_max:.2f} (saved {keep})"
                )
            else:
                print(f"[visual] {cid}: diff {diff:.2f} <= {diff_max:.2f} OK")

        for case in query_cases:
            cid = case["id"]
            try:
                py_val = _query(py_renderer, cid)
                cpp_val = _query(cpp_renderer, cid)
            except RuntimeError as exc:
                failures.append(f"[query] {cid}: {exc}")
                continue
            if "expect" in case:
                expected = case["expect"]
                expected_str = (
                    "true" if expected is True else
                    "false" if expected is False else
                    str(expected)
                )
                if py_val != expected_str:
                    failures.append(
                        f"[query.py] {cid}: python returned {py_val!r}, "
                        f"corpus expected {expected_str!r}"
                    )
                if cpp_val != expected_str:
                    failures.append(
                        f"[query.cpp] {cid}: c++ returned {cpp_val!r}, "
                        f"corpus expected {expected_str!r}"
                    )
            elif "expect_atleast" in case:
                threshold = int(case["expect_atleast"])
                if int(py_val) < threshold:
                    failures.append(
                        f"[query.py] {cid}: python returned {py_val!r} "
                        f"< expected ≥ {threshold}"
                    )
                if int(cpp_val) < threshold:
                    failures.append(
                        f"[query.cpp] {cid}: c++ returned {cpp_val!r} "
                        f"< expected ≥ {threshold}"
                    )
            else:
                # No anchor — assert C++ and Python at least agree.
                if py_val != cpp_val:
                    failures.append(
                        f"[query.parity] {cid}: python={py_val!r} != "
                        f"c++={cpp_val!r}"
                    )
                else:
                    print(f"[query.parity] {cid}: {py_val!r} OK")
                    continue
            if not failures or failures[-1].startswith("[query") is False:
                print(f"[query] {cid}: py={py_val!r} cpp={cpp_val!r} OK")

    if failures:
        print("\n=== parity FAILURES ===", file=sys.stderr)
        for f in failures:
            print(f, file=sys.stderr)
        return 1
    print(f"\n=== parity OK ({len(visual_cases)} visual + "
          f"{len(query_cases)} query cases) ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
