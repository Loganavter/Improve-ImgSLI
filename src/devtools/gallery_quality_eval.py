#!/usr/bin/env python3
"""Gallery quality mini-eval harness (plan-gallery-ai-quality, Phase 5).

Compares the local artifact detectors (and, when available, the cached VLM
analysis) against a small hand-labeled ground-truth set, per artifact axis. The
point is to answer the plan's open question: *which source is right per axis on
our content* — and to gate the cel-art false positive (a constant content bias
that the source-anchoring in ``services/artifacts.py`` must cancel).

Headless and Qt-free: it imports only the pure detector/cache modules.

Usage:
  python src/devtools/gallery_quality_eval.py --folder DIR \
      --source DIR/source.png --truth truth.yaml
  python src/devtools/gallery_quality_eval.py --folder DIR --write-template truth.yaml
  python src/devtools/gallery_quality_eval.py --folder DIR --truth truth.yaml --json out.json

Ground-truth YAML (per image basename; ``expect`` is the human's per-axis call):
  source: source.png            # optional default source for anchoring
  images:
    crisp_cartoon.png:          # a known content-bias trap
      cel_art: true             # listed axes must read clean after anchoring
      expect: {halo: clean, banding: clean}
    over_sharpened.png:
      expect: {halo: flagged}
    banded_sky.png:
      expect: {banding: flagged}

Severity values: clean | mild | flagged. A ``present``/``absent`` shorthand is
accepted (present == mild-or-flagged, absent == clean). Missing axes are
ignored. ``cel_art: true`` marks the anchoring regression gate.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Make ``tabs.*`` importable when run as a plain script.
_REPO = Path(__file__).resolve().parents[2]
if str(_REPO / "src") not in sys.path:
    sys.path.insert(0, str(_REPO / "src"))

_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}

# Canonical axes we score (the four anchored + the three source-relative).
_AXES = (
    "banding",
    "halo",
    "blocking",
    "chroma_fringing",
    "over_smoothing",
    "invented_texture",
    "noise_amplification",
)
_SEVERITIES = ("clean", "mild", "flagged")

# VLM defect kinds -> canonical artifact axes (only these overlap the detectors).
_VLM_KIND_TO_AXIS = {
    "halo": "halo",
    "banding": "banding",
    "blocking": "blocking",
    "chroma_fringing": "chroma_fringing",
    "over_smoothing": "over_smoothing",
    "invented_texture": "invented_texture",
    "noise": "noise_amplification",
}


def _discover_images(root: Path) -> list[Path]:
    out: list[Path] = []
    for p in sorted(root.rglob("*")):
        try:
            if p.is_file() and p.suffix.lower() in _IMAGE_EXTS:
                out.append(p)
        except OSError:
            continue
    return out


def _norm_severity(value: object) -> str:
    """Map truth values to a canonical severity; ``present``/``absent`` allowed."""
    text = str(value).strip().lower()
    if text == "present":
        return "flagged"
    if text == "absent":
        return "clean"
    return text if text in _SEVERITIES else "clean"


def _detector_calls(path: Path, source: Path | None) -> dict[str, str]:
    from tabs.image_gallery.services.artifacts import analyze_artifacts

    raw = analyze_artifacts(path, source) if source is not None else analyze_artifacts(path)
    out: dict[str, str] = {}
    for art, sev in raw.items():
        name = getattr(art, "value", None) or str(art).split(".")[-1]
        out[str(name).lower()] = getattr(sev, "value", None) or str(sev).lower()
    return out


def _vlm_calls(path: Path) -> dict[str, str]:
    """Artifact-axis presence from the cached VLM analysis (no network)."""
    try:
        from tabs.image_gallery.services import ai_cache

        try:
            mtime = path.stat().st_mtime_ns
        except OSError:
            return {}
        result = ai_cache.load_cached_analysis(path, mtime)
        if result is None:
            return {}
    except Exception:
        return {}
    out = {axis: "clean" for axis in _AXES}
    for d in getattr(result, "defects", ()) or ():
        axis = _VLM_KIND_TO_AXIS.get(str(getattr(d, "kind", "") or "").lower())
        if axis:
            sev = str(getattr(d, "severity", "") or "mild").lower()
            # keep the worst call if a kind repeats
            if out.get(axis, "clean") == "clean" or sev == "flagged":
                out[axis] = sev if sev in _SEVERITIES else "mild"
    return out


def _load_truth(path: Path) -> dict:
    import yaml

    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise SystemExit(f"truth file is not a mapping: {path}")
    return data


def _truth_for(truth: dict, image: Path) -> dict:
    images = truth.get("images") or {}
    return dict(images.get(image.name) or {})


def run_eval(folder: Path, source: Path | None, truth: dict) -> dict:
    default_source = truth.get("source")
    rows: list[dict] = []
    for image in _discover_images(folder):
        entry = _truth_for(truth, image)
        img_source = entry.get("source") or default_source
        src_path: Path | None = None
        if img_source:
            cand = (folder / img_source) if not Path(img_source).is_absolute() else Path(img_source)
            src_path = cand if cand.is_file() else None
        if source is not None and src_path is None:
            src_path = source
        det = _detector_calls(image, src_path)
        vlm = _vlm_calls(image)
        expect = {k: _norm_severity(v) for k, v in (entry.get("expect") or {}).items()}
        rows.append(
            {
                "image": image.name,
                "cel_art": bool(entry.get("cel_art", False)),
                "anchored": src_path is not None,
                "expect": expect,
                "detector": {a: det.get(a, "clean") for a in _AXES},
                "vlm": vlm,
            }
        )
    return {"folder": str(folder), "rows": rows, "axes": list(_AXES)}


def _summarize(result: dict) -> dict:
    per_axis: dict[str, dict] = {
        a: {"n": 0, "exact": 0, "present_agree": 0, "fp": 0, "fn": 0} for a in _AXES
    }
    vlm_axis: dict[str, dict] = {
        a: {"n": 0, "exact": 0, "present_agree": 0, "fp": 0, "fn": 0} for a in _AXES
    }
    cel_total = cel_clean = 0
    for row in result["rows"]:
        for axis, want in row["expect"].items():
            if axis not in per_axis:
                continue
            got = row["detector"].get(axis, "clean")
            per_axis[axis]["n"] += 1
            per_axis[axis]["exact"] += int(got == want)
            per_axis[axis]["present_agree"] += int((got != "clean") == (want != "clean"))
            if got != "clean" and want == "clean":
                per_axis[axis]["fp"] += 1
            if got == "clean" and want != "clean":
                per_axis[axis]["fn"] += 1
            v = row["vlm"].get(axis)
            if v is not None:
                vlm_axis[axis]["n"] += 1
                vlm_axis[axis]["exact"] += int(v == want)
                vlm_axis[axis]["present_agree"] += int((v != "clean") == (want != "clean"))
                if v != "clean" and want == "clean":
                    vlm_axis[axis]["fp"] += 1
                if v == "clean" and want != "clean":
                    vlm_axis[axis]["fn"] += 1
        if row["cel_art"]:
            for axis, want in row["expect"].items():
                if want == "clean":
                    cel_total += 1
                    cel_clean += int(row["detector"].get(axis, "clean") == "clean")
    return {"detector": per_axis, "vlm": vlm_axis, "cel_art": {"total": cel_total, "clean": cel_clean}}


def _print_report(result: dict, summary: dict) -> None:
    print(f"Gallery quality mini-eval — {result['folder']}")
    print(f"images: {len(result['rows'])}  axes: {', '.join(result['axes'])}")
    print()
    print(f"{'image':<28} {'axis':<18} {'truth':<8} {'detector':<9} {'vlm':<9}")
    for row in result["rows"]:
        if not row["expect"]:
            continue
        for axis, want in sorted(row["expect"].items()):
            got = row["detector"].get(axis, "clean")
            v = row["vlm"].get(axis, "n/a")
            flag = "" if got == want else "  <-- detector"
            print(f"{row['image'][:27]:<28} {axis:<18} {want:<8} {got:<9} {v:<9}{flag}")
    print()
    print("per-axis detector vs truth:")
    print(f"{'axis':<20} {'n':>3} {'exact':>6} {'present':>8} {'FP':>4} {'FN':>4}")
    for axis, s in summary["detector"].items():
        if s["n"]:
            print(f"{axis:<20} {s['n']:>3} {s['exact']:>3}/{s['n']:<2} {s['present_agree']:>5}/{s['n']:<2} {s['fp']:>4} {s['fn']:>4}")
    if any(s["n"] for s in summary["vlm"].values()):
        print()
        print("per-axis VLM (cached) vs truth:")
        for axis, s in summary["vlm"].items():
            if s["n"]:
                print(f"{axis:<20} {s['n']:>3} {s['exact']:>3}/{s['n']:<2} {s['present_agree']:>5}/{s['n']:<2} {s['fp']:>4} {s['fn']:>4}")
    cel = summary["cel_art"]
    if cel["total"]:
        verdict = "PASS" if cel["clean"] == cel["total"] else "FAIL"
        print()
        print(f"cel-art FP gate: {verdict} ({cel['clean']}/{cel['total']} expected-clean axes read clean)")


def _write_template(folder: Path, out: Path) -> None:
    lines = [
        "# Gallery quality mini-eval ground truth.",
        "# Fill `expect` per image with the human per-axis call:",
        "#   clean | mild | flagged   (or present/absent shorthand).",
        "# Mark content-bias traps with `cel_art: true` (must read clean).",
        "# `source:` enables source-anchored detection (fidelity).",
        "source: null",
        "images:",
    ]
    for image in _discover_images(folder):
        lines.append(f"  {image.name}:")
        lines.append("    # source: <basename>")
        lines.append("    # cel_art: false")
        lines.append("    expect: {}")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote truth template: {out}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Gallery quality mini-eval (plan-gallery-ai-quality P5).")
    parser.add_argument("--folder", required=True, type=Path, help="folder of images (scanned recursively)")
    parser.add_argument("--source", type=Path, default=None, help="default source image for anchoring")
    parser.add_argument("--truth", type=Path, default=None, help="ground-truth YAML")
    parser.add_argument("--json", type=Path, default=None, help="write structured results as JSON")
    parser.add_argument("--write-template", type=Path, default=None, help="write a truth YAML template and exit")
    args = parser.parse_args(argv)

    folder = args.folder
    if not folder.is_dir():
        print(f"not a folder: {folder}", file=sys.stderr)
        return 2
    if args.write_template is not None:
        _write_template(folder, args.write_template)
        return 0
    if args.truth is None:
        print("--truth is required (or use --write-template)", file=sys.stderr)
        return 2
    truth = _load_truth(args.truth)
    result = run_eval(folder, args.source, truth)
    summary = _summarize(result)
    _print_report(result, summary)
    if args.json is not None:
        args.json.write_text(
            json.dumps({"result": result, "summary": summary}, indent=2), encoding="utf-8"
        )
        print(f"\nwrote JSON: {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
