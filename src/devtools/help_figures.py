#!/usr/bin/env python3
"""Help-figure generator: recipe -> deterministic PNGs, plus a drift check.

Devtool only. ``capture_surface`` is imported, never copied: it owns how a
surface is built, themed, translated, isolated and grabbed. This module owns
which figure is wanted (``help_figures.json``), where it belongs, how it is
cropped, and whether fresh bytes still match a recorded baseline. Generating
writes into ``--out`` (a fresh temp dir by default), never into
``src/**/resources/help/assets/``, so a routine run cannot churn a shipped
figure. See ``docs/dev/SCREENSHOTS.md`` §Help-figure generator.

    python src/devtools/help_figures.py --list            # no display
    python src/devtools/help_figures.py --all --out /tmp/shots   # + WxH parity table
    python src/devtools/help_figures.py --check
    python src/devtools/help_figures.py --compare         # WxH parity report (exit 1)
    python src/devtools/help_figures.py --all --write-manifest

Audit-Meta: pattern=devtool-pipeline size=exempt reason="one devtool contract: recipe schema+IO, capture adapter, drift/apply and display lifecycle all compare against the same manifest — splitting forks the schema"
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Iterator, Sequence

#: Repo root (``<repo>/src/devtools/help_figures.py`` -> ``<repo>``).
REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from devtools import capture_surface  # noqa: E402  — the surface API we reuse

MANIFEST_PATH = Path(__file__).with_name("help_figures.json")
SCHEMA_VERSION = 1
#: Alphabetical canonical order, so the file is byte-stable whatever filters a
#: caller passes.
LOCALES = ("en", "pt_BR", "ru", "zh")
THEMES = ("dark", "light")
BACKENDS = ("native", "xvfb")
#: Pins that really go through the surface API (``capture_surface`` CLI:
#: ``--theme`` -> ``ThemeManager.set_theme``, ``--lang`` -> ``emit_language_changed``).
PINNABLE = ("locale", "theme")
#: Pins the surface API cannot express. Recorded, never faked.
UNPINNABLE = ("font", "ui_scale")
#: Constructors that hardcode ``current_language="en"`` / ``current_theme="dark"``
#: (``SETTINGS_KWARGS``, the onboarding store): a non-default filter only reaches
#: text resolved through ``tr`` at build time, so it is recorded as a caveat.
_PINS_EN = frozenset({"settings", "settings-keyboard", "onboarding"})
_PINS_DARK = frozenset({"settings", "settings-keyboard"})
_SHA_LEN = 64
_BASELINE_KEYS = {"locale", "theme", "sha256", "size", "width", "height", "pins_applied", "pins_unavailable"}
_FIGURE_KEYS = {
    "id", "surface", "crop", "size", "locales", "themes", "destination", "covered",
    "reason", "note", "pins_applied", "pins_unavailable", "captures",
}


class ManifestError(ValueError):
    """The recipe/manifest file is malformed (bad id, surface, path, hash)."""


class FigureError(ValueError):
    """A figure could not be captured (surface failure, missing PNG)."""


class CropError(FigureError):
    """A crop rectangle is malformed or does not fit the captured image."""


@dataclass(frozen=True)
class Baseline:
    """Recorded result for one figure + locale + theme."""

    locale: str
    theme: str
    sha256: str
    size: int
    width: int
    height: int
    pins_applied: tuple[str, ...] = ()
    pins_unavailable: tuple[str, ...] = ()


@dataclass(frozen=True)
class Figure:
    """One recipe entry: what to capture and where the shot belongs."""

    id: str
    surface: str
    destination: str | None
    locales: tuple[str, ...] = ("en",)
    themes: tuple[str, ...] = ("dark",)
    crop: tuple[int, int, int, int] | None = None
    size: tuple[int, int] | None = None
    covered: bool = True
    reason: str = ""
    note: str = ""
    pins_applied: tuple[str, ...] = ()
    pins_unavailable: tuple[str, ...] = ()
    captures: tuple[Baseline, ...] = ()


@dataclass(frozen=True)
class Manifest:
    """Parsed ``help_figures.json`` (recipes + optional baseline hashes)."""

    figures: tuple[Figure, ...]
    schema_version: int = SCHEMA_VERSION


# --- Validation -------------------------------------------------------------


def validate_crop(
    crop: Sequence[int] | None, *, figure_id: str, size: tuple[int, int] | None = None
) -> tuple[int, int, int, int]:
    """Validate ``[x, y, w, h]``, optionally against the captured size.

    Every rejection names the figure and the offending axis — a bare
    ``ValueError`` from ``PIL.crop`` would not say which recipe entry is wrong.
    """
    if not isinstance(crop, (list, tuple)) or len(crop) != 4:
        raise CropError(f"{figure_id}: crop must be [x, y, w, h], got {crop!r}")
    if any(isinstance(v, bool) or not isinstance(v, int) for v in crop):
        raise CropError(f"{figure_id}: crop values must be integers, got {crop!r}")
    x, y, w, h = crop
    if x < 0 or y < 0:
        raise CropError(f"{figure_id}: crop origin must be >= 0, got x={x} y={y}")
    if w <= 0 or h <= 0:
        raise CropError(f"{figure_id}: crop width and height must be > 0, got w={w} h={h}")
    if size is not None and (x + w > size[0] or y + h > size[1]):
        raise CropError(f"{figure_id}: crop {w}x{h}+{x}+{y} exceeds captured image {size[0]}x{size[1]}")
    return (x, y, w, h)


def _strings(value, figure_id: str, key: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or not all(isinstance(v, str) for v in value):
        raise ManifestError(f"{figure_id}: {key} must be a list of strings, got {value!r}")
    return tuple(value)


def _parse_baseline(raw, figure_id: str) -> Baseline:
    if not isinstance(raw, dict):
        raise ManifestError(f"{figure_id}: capture entry must be an object")
    if unknown := set(raw) - _BASELINE_KEYS:
        raise ManifestError(f"{figure_id}: unknown capture keys {sorted(unknown)}")
    locale, theme, sha256 = raw.get("locale"), raw.get("theme"), raw.get("sha256")
    if locale not in LOCALES:
        raise ManifestError(f"{figure_id}: unknown capture locale {locale!r}")
    if theme not in THEMES:
        raise ManifestError(f"{figure_id}: unknown capture theme {theme!r}")
    try:
        valid_sha = isinstance(sha256, str) and len(sha256) == _SHA_LEN and bool(int(sha256, 16))
    except ValueError:
        valid_sha = False
    if not valid_sha:
        raise ManifestError(f"{figure_id}: capture sha256 must be 64 hex chars, got {sha256!r}")
    dims = {key: raw.get(key, 1) for key in ("size", "width", "height")}
    if any(isinstance(v, bool) or not isinstance(v, int) or v <= 0 for v in dims.values()):
        raise ManifestError(f"{figure_id}: capture size/width/height must be positive ints")
    return Baseline(
        locale=locale, theme=theme, sha256=sha256.lower(), size=dims["size"],
        width=dims["width"], height=dims["height"],
        pins_applied=_strings(raw.get("pins_applied", []), figure_id, "pins_applied"),
        pins_unavailable=_strings(raw.get("pins_unavailable", []), figure_id, "pins_unavailable"),
    )


def _parse_figure(raw) -> Figure:
    if not isinstance(raw, dict):
        raise ManifestError(f"figure entry must be an object, got {raw!r}")
    if unknown := set(raw) - _FIGURE_KEYS:
        raise ManifestError(f"figure has unknown keys {sorted(unknown)}")
    figure_id = raw.get("id")
    if not isinstance(figure_id, str) or not figure_id.strip():
        raise ManifestError(f"figure id must be a non-empty string, got {figure_id!r}")
    surface = raw.get("surface")
    if surface not in capture_surface.SURFACES:
        raise ManifestError(
            f"{figure_id}: unknown surface {surface!r}; known: {', '.join(sorted(capture_surface.SURFACES))}"
        )
    covered = raw.get("covered", True)
    if not isinstance(covered, bool):
        raise ManifestError(f"{figure_id}: covered must be a boolean")
    reason = raw.get("reason", "")
    if not isinstance(reason, str):
        raise ManifestError(f"{figure_id}: reason must be a string")
    if not covered and not reason.strip():
        raise ManifestError(f"{figure_id}: an uncovered figure needs a reason (new-surface/hand-composed)")
    destination = raw.get("destination")
    if destination is None:
        if covered:
            raise ManifestError(f"{figure_id}: a covered figure needs a destination")
        dest = None
    else:
        if not isinstance(destination, str) or not destination:
            raise ManifestError(f"{figure_id}: destination must be a path or null")
        dest = Path(destination)
        if dest.is_absolute() or ".." in dest.parts:
            raise ManifestError(f"{figure_id}: destination must be repo-relative without '..': {dest}")
        if "/resources/help/assets/" not in dest.as_posix():
            raise ManifestError(f"{figure_id}: destination must live under a help package assets dir: {dest}")
        if dest.suffix.lower() not in (".png", ".jpg"):
            raise ManifestError(f"{figure_id}: destination must be a .png/.jpg: {dest}")
        if covered and not (REPO_ROOT / dest).is_file():
            raise ManifestError(f"{figure_id}: covered destination does not exist: {dest}")
    size = raw.get("size")
    size_box = None
    if size is not None:
        if (not isinstance(size, (list, tuple)) or len(size) != 2
                or any(isinstance(v, bool) or not isinstance(v, int) or v <= 0 for v in size)):
            raise ManifestError(f"{figure_id}: size must be [width, height] positive ints, got {size!r}")
        size_box = (size[0], size[1])
    locales = _strings(raw.get("locales", ["en"]), figure_id, "locales")
    themes = _strings(raw.get("themes", ["dark"]), figure_id, "themes")
    if not locales or not themes:
        raise ManifestError(f"{figure_id}: locales and themes must not be empty")
    if bad := [v for v in locales if v not in LOCALES]:
        raise ManifestError(f"{figure_id}: unknown locales {bad}; known: {LOCALES}")
    if bad := [v for v in themes if v not in THEMES]:
        raise ManifestError(f"{figure_id}: unknown themes {bad}; known: {THEMES}")
    if not isinstance(raw.get("note", ""), str):
        raise ManifestError(f"{figure_id}: note must be a string")
    captures_raw = raw.get("captures", [])
    if not isinstance(captures_raw, list):
        raise ManifestError(f"{figure_id}: captures must be a list")
    captures = tuple(_parse_baseline(item, figure_id) for item in captures_raw)
    if len({(b.locale, b.theme) for b in captures}) != len(captures):
        raise ManifestError(f"{figure_id}: duplicate capture entries for the same locale+theme")
    crop = raw.get("crop")
    return Figure(
        id=figure_id, surface=surface, destination=None if dest is None else dest.as_posix(),
        locales=tuple(locales), themes=tuple(themes),
        crop=None if crop is None else validate_crop(crop, figure_id=figure_id), size=size_box,
        covered=covered, reason=reason, note=raw.get("note", ""),
        pins_applied=_strings(raw.get("pins_applied", []), figure_id, "pins_applied"),
        pins_unavailable=_strings(raw.get("pins_unavailable", []), figure_id, "pins_unavailable"),
        captures=captures,
    )


def load_manifest(path: Path | str = MANIFEST_PATH) -> Manifest:
    """Read + validate the recipe JSON. Raises :class:`ManifestError`."""
    path = Path(path)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ManifestError(f"manifest not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ManifestError(f"{path}: invalid JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise ManifestError(f"{path}: top level must be an object")
    if unknown := set(raw) - {"schema_version", "figures"}:
        raise ManifestError(f"{path}: unknown top-level keys {sorted(unknown)}")
    if raw.get("schema_version") != SCHEMA_VERSION:
        raise ManifestError(f"{path}: unsupported schema_version {raw.get('schema_version')!r}")
    figures_raw = raw.get("figures")
    if not isinstance(figures_raw, list) or not figures_raw:
        raise ManifestError(f"{path}: figures must be a non-empty list")
    figures = tuple(_parse_figure(item) for item in figures_raw)
    if len({figure.id for figure in figures}) != len(figures):
        raise ManifestError(f"{path}: duplicate figure ids: {[f.id for f in figures]}")
    destinations = [figure.destination for figure in figures if figure.destination]
    if len(set(destinations)) != len(destinations):
        raise ManifestError(f"{path}: two figures share one destination")
    return Manifest(figures=figures)


# --- (De)serialisation ------------------------------------------------------


def manifest_to_dict(manifest: Manifest) -> dict:
    """Canonical dict: sorted figures/captures; tuples serialise as JSON arrays."""
    figures = []
    for figure in sorted(manifest.figures, key=lambda item: item.id):
        entry = {
            key: value
            for key, value in asdict(figure).items()
            if key not in {"captures", "crop", "size"}
        }
        entry["crop"] = list(figure.crop) if figure.crop is not None else None
        entry["size"] = list(figure.size) if figure.size is not None else None
        entry["locales"] = sorted(figure.locales)
        entry["themes"] = sorted(figure.themes)
        entry["captures"] = [
            asdict(b) for b in sorted(figure.captures, key=lambda b: (b.locale, b.theme))
        ]
        figures.append(entry)
    return {"schema_version": manifest.schema_version, "figures": figures}


def dumps_manifest(manifest: Manifest) -> str:
    """Deterministic JSON text: sorted keys, 2-space indent, trailing newline."""
    return json.dumps(manifest_to_dict(manifest), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def write_manifest(path: Path | str, manifest: Manifest) -> Path:
    """Write the canonical text (``\n`` newlines, no timestamp)."""
    path = Path(path)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(dumps_manifest(manifest))
    return path


# --- Pins -------------------------------------------------------------------


def pin_report(
    figure: Figure,
    locale: str,
    theme: str,
    *,
    captured_size: tuple[int, int] | None = None,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Which pins the surface API really applied for this capture.

    Constructors that hardcode their own language/theme are recorded as caveats
    instead of being claimed as applied. A ``size`` pin is only claimed when the
    grabbed pixels really are that size; a surface that refuses the pin is
    recorded as unavailable WITH the achieved size (never silently resized —
    that would fake parity).
    """
    unavailable = list(UNPINNABLE)
    applied = list(PINNABLE)
    if figure.surface in _PINS_EN:
        unavailable.append("locale:constructor-pins-en")
    if figure.surface in _PINS_DARK and theme != "dark":
        unavailable.append("theme:constructor-pins-dark")
    if figure.size is not None and captured_size is not None:
        if tuple(captured_size) == tuple(figure.size):
            applied.append("size")
        else:
            unavailable.append(
                f"size:surface-ignores-pin:{captured_size[0]}x{captured_size[1]}"
            )
    return tuple(applied), tuple(sorted(unavailable))


# --- Capture (reuses capture_surface by import) -----------------------------


def _assets_root(destination: Path) -> Path:
    """``assets`` ancestor of a repo-relative destination (variant roots)."""
    parts = destination.parts
    for index in range(len(parts) - 1, -1, -1):
        if parts[index] == "assets":
            return Path(*parts[: index + 1])
    return destination.parent


def figure_variant_count(figure: Figure) -> int:
    """How many locale/theme images this recipe produces."""
    return len(set(figure.locales)) * len(set(figure.themes))


def install_destination(figure: Figure, locale: str, theme: str) -> Path:
    """Repo-relative path one generated variant installs to.

    A single-variant recipe keeps today's flat destination (the 25 shipped
    figures do not move). A multi-variant recipe declares the full matrix, so
    every cell goes under ``assets/<locale>/<theme>/<name>`` — the layout the
    runtime resolver (``plugins.help.tree.resolve_help_asset``) probes first.
    """
    destination = Path(figure.destination or "")
    if figure_variant_count(figure) <= 1:
        return destination
    return _assets_root(destination) / locale / theme / destination.name


def crop_png(path: Path | str, crop, *, figure_id: str) -> Path:
    """Crop a captured PNG in place; rejects a rect larger than the image."""
    from PIL import Image

    path = Path(path)
    with Image.open(path) as image:
        x, y, w, h = validate_crop(crop, figure_id=figure_id, size=image.size)
        image.crop((x, y, x + w, y + h)).save(path)
    return path


class _RecordingSession(capture_surface.CaptureSession):
    """``CaptureSession`` that remembers what ``grab`` wrote (no fork of grab)."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.saved: list[Path] = []

    def grab(self, widget, filename, default_w, default_h, delay: int = 1200) -> Path:
        path = super().grab(widget, filename, default_w, default_h, delay=delay)
        self.saved.append(path)
        return path


def _run_surface(
    surface: capture_surface.Surface, dest: Path, theme: str, locale: str, size=None
) -> Path:
    """Build one surface through ``capture_surface`` and return its PNG.

    Non-isolated surfaces are built in-process (imported builders + bootstrap).
    Isolated ones (QRhi/GL, may hard-exit) go through ``capture_surface.main``,
    which re-execs itself offscreen.
    """
    if surface.isolated:
        cmd = [surface.name, "--out", str(dest), "--theme", theme, "--lang", locale]
        if size:
            cmd += ["--width", str(size[0]), "--height", str(size[1])]
        code = capture_surface.main(cmd)
        if code != 0:
            raise FigureError(f"{surface.name}: capture_surface exited {code}")
        pngs = sorted(path for path in dest.glob("*.png") if path.is_file())
        if not pngs:
            raise FigureError(f"{surface.name}: capture_surface produced no PNG in {dest}")
        return pngs[-1]
    width, height = size if size else (None, None)
    session = _RecordingSession(
        capture_surface._bootstrap_qt(theme, locale), dest, width=width, height=height
    )
    surface.build(session)
    if not session.saved:
        raise FigureError(f"{surface.name}: surface builder saved no PNG")
    return session.saved[-1]


def capture_png(figure: Figure, locale: str, theme: str, out_dir: Path | str) -> Path:
    """Capture one figure into ``out_dir/<id>__<locale>__<theme>/`` + apply crop."""
    dest = Path(out_dir) / f"{figure.id}__{locale}__{theme}"
    dest.mkdir(parents=True, exist_ok=True)
    path = _run_surface(capture_surface.SURFACES[figure.surface], dest, theme, locale, figure.size)
    return crop_png(path, figure.crop, figure_id=figure.id) if figure.crop else path


def _fingerprint(path: Path) -> tuple[str, int, int, int]:
    """``(sha256, bytes, width, height)`` of a generated PNG (no app imports)."""
    from PIL import Image

    with Image.open(path) as image:
        width, height = image.size
    return hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_size, width, height


# --- Generation / drift -----------------------------------------------------


def _pairs(figure: Figure, locales: Sequence[str] | None, themes: Sequence[str] | None):
    wanted_locales = set(locales) if locales else set(figure.locales)
    wanted_themes = set(themes) if themes else set(figure.themes)
    for locale in sorted(wanted_locales & set(figure.locales)):
        for theme in sorted(wanted_themes & set(figure.themes)):
            yield locale, theme


def generate(
    manifest: Manifest, out_dir: Path | str, *, locales=None, themes=None, capture=None, stream=None
) -> list[dict]:
    """Capture every selected (figure, locale, theme) pair; return records."""
    capture = capture or capture_png
    stream = sys.stdout if stream is None else stream
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    records: list[dict] = []
    for figure in manifest.figures:
        if not figure.covered:
            continue
        for locale, theme in _pairs(figure, locales, themes):
            captured = Path(capture(figure, locale, theme, out_dir))
            asset = install_destination(figure, locale, theme)
            if figure_variant_count(figure) > 1:
                # Multi-variant: stage into the assets/<locale>/<theme>/ layout
                # the runtime resolver probes (inside --out, never the repo).
                staged = out_dir / asset
                staged.parent.mkdir(parents=True, exist_ok=True)
                if staged.resolve() != captured.resolve():
                    shutil.copyfile(captured, staged)
                captured = staged
            sha256, size, width, height = _fingerprint(captured)
            applied, unavailable = pin_report(
                figure, locale, theme, captured_size=(width, height)
            )
            records.append({
                "figure": figure.id, "surface": figure.surface, "locale": locale, "theme": theme,
                "sha256": sha256, "size": size, "width": width, "height": height,
                "asset": asset.as_posix(),
                "pins_applied": list(applied), "pins_unavailable": list(unavailable),
                "path": str(captured),
            })
            print(
                f"captured {figure.id} [{locale}/{theme}] -> {captured} ({width}x{height}, {size} B)",
                file=stream,
            )
            if figure.size is not None and (width, height) != tuple(figure.size):
                print(
                    f"pin_unavailable {figure.id} [{locale}/{theme}]: "
                    f"pinned {figure.size[0]}x{figure.size[1]}, achieved {width}x{height} "
                    "(recorded as pins_unavailable; the grab is not resampled)",
                    file=stream,
                )
    return records


def compare(manifest: Manifest, records: Sequence[dict]) -> tuple[list[dict], bool]:
    """Compare generated records against recorded hashes.

    A capture with no baseline is ``unbaselined`` — reported, never counted as
    drift (a fresh recipe has no hashes until someone runs with a display).

    A pinned capture whose fresh frame differs from the pin is drift even when
    its bytes match the baseline: the baseline records what was generated, the
    pin records the frame that has to be reproduced. Otherwise a run could
    baseline an ignored pin and later call the wrong size ``ok``.
    """
    index = {
        (figure.id, baseline.locale, baseline.theme): baseline
        for figure in manifest.figures
        for baseline in figure.captures
    }
    by_id = {figure.id: figure for figure in manifest.figures}
    rows: list[dict] = []
    drifted = False
    for record in sorted(records, key=lambda r: (r["figure"], r["locale"], r["theme"])):
        baseline = index.get((record["figure"], record["locale"], record["theme"]))
        pinned = by_id[record["figure"]].size
        if baseline is None:
            status, detail = "unbaselined", "no recorded sha256"
        elif pinned is not None and (record["width"], record["height"]) != tuple(pinned):
            drifted, status = True, "drift"
            detail = f"pinned {pinned[0]}x{pinned[1]} != achieved {record['width']}x{record['height']}"
        elif baseline.sha256 == record["sha256"]:
            status, detail = "ok", ""
        else:
            drifted, status = True, "drift"
            detail = f"expected {baseline.sha256[:12]} got {record['sha256'][:12]}"
        rows.append({**record, "status": status, "detail": detail})
    return rows, drifted


def check_figures(
    manifest: Manifest, out_dir: Path | str, *, locales=None, themes=None, capture=None, stream=None
) -> int:
    """Regenerate + compare. Returns 0 (identical/unbaselined) or 1 (drift)."""
    stream = sys.stdout if stream is None else stream
    rows, drifted = compare(
        manifest,
        generate(manifest, out_dir, locales=locales, themes=themes, capture=capture, stream=stream),
    )
    header = f"{'figure':<30} {'locale':<7} {'theme':<6} {'status':<12} detail"
    print(header, file=stream)
    print("-" * len(header), file=stream)
    counts: dict[str, int] = {}
    for row in rows:
        print(
            f"{row['figure']:<30} {row['locale']:<7} {row['theme']:<6} "
            f"{row['status']:<12} {row['detail']}",
            file=stream,
        )
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    summary = ", ".join(f"{s}={counts[s]}" for s in sorted(counts)) or "no captures"
    print(f"drift check: {summary}", file=stream)
    uncovered = [f"{f.id} ({f.reason})" for f in manifest.figures if not f.covered]
    if uncovered:
        print("uncovered (not checked): " + ", ".join(uncovered), file=stream)
    return 1 if drifted else 0


def _shipped_size(figure: Figure, repo_root: Path = REPO_ROOT) -> tuple[int, int] | None:
    """Measured shipped image size (for figures with no explicit size pin)."""
    if not figure.destination:
        return None
    path = Path(repo_root) / figure.destination
    if not path.is_file():
        return None
    from PIL import Image

    with Image.open(path) as image:
        return image.size


def compare_parity(
    manifest: Manifest,
    records: Sequence[dict],
    *,
    repo_root: Path = REPO_ROOT,
) -> tuple[list[dict], bool]:
    """Per capture: generated WxH vs the pinned (else shipped) WxH.

    ``parity`` means the freshly generated frame has exactly the target size;
    ``dims-differ`` means it does not; ``no-target`` means neither a pin nor a
    shipped file exists. Pixel content is not judged here — that is ``--check``.
    """
    if not records:
        return [], False
    by_id = {figure.id: figure for figure in manifest.figures}
    rows: list[dict] = []
    mismatched = False
    for record in sorted(records, key=lambda r: (r["figure"], r["locale"], r["theme"])):
        figure = by_id[record["figure"]]
        if figure.size is not None:
            target, source = tuple(figure.size), "pin"
        else:
            target, source = _shipped_size(figure, repo_root), "shipped"
        if target is None:
            status = "no-target"
        elif (record["width"], record["height"]) == target:
            status = "parity"
        else:
            mismatched, status = True, "dims-differ"
        rows.append({**record, "target": target, "target_source": source, "status": status})
    return rows, mismatched


def compare_sizes(
    manifest: Manifest, out_dir: Path | str, *, locales=None, themes=None, capture=None, stream=None
) -> int:
    """Regenerate + report size parity. Returns 0 (all parity/no-target) or 1."""
    stream = sys.stdout if stream is None else stream
    rows, mismatched = compare_parity(
        manifest,
        generate(manifest, out_dir, locales=locales, themes=themes, capture=capture, stream=stream),
    )
    header = f"{'figure':<30} {'locale':<7} {'theme':<6} {'generated':<12} {'target':<12} status"
    print(header, file=stream)
    print("-" * len(header), file=stream)
    counts: dict[str, int] = {}
    for row in rows:
        generated = f"{row['width']}x{row['height']}"
        target = "?" if row["target"] is None else "%dx%d" % tuple(row["target"])
        source = "" if row["target"] is None else f" ({row['target_source']})"
        print(
            f"{row['figure']:<30} {row['locale']:<7} {row['theme']:<6} "
            f"{generated:<12} {target + source:<12} {row['status']}",
            file=stream,
        )
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    summary = ", ".join(f"{s}={counts[s]}" for s in sorted(counts)) or "no captures"
    print(f"size parity: {summary}", file=stream)
    return 1 if mismatched else 0


def print_parity_table(
    manifest: Manifest,
    records: Sequence[dict],
    *,
    stream=None,
    repo_root: Path = REPO_ROOT,
) -> tuple[list[dict], bool]:
    """Print figure/pinned/achieved/verdict after a generation run.

    One row per capture, so a live run answers "did the pin hold?" before any
    baseline is written. ``dims-differ`` from :func:`compare_parity` prints as
    ``differ`` here (the word the recipe discussion uses).
    """
    stream = sys.stdout if stream is None else stream
    rows, mismatched = compare_parity(manifest, records, repo_root=repo_root)
    header = f"{'figure':<30} {'pinned':<12} {'achieved':<12} verdict"
    print("", file=stream)
    print(header, file=stream)
    print("-" * len(header), file=stream)
    for row in rows:
        pinned = "?" if row["target"] is None else "%dx%d" % tuple(row["target"])
        achieved = f"{row['width']}x{row['height']}"
        verdict = "parity" if row["status"] == "parity" else "differ"
        print(f"{row['figure']:<30} {pinned:<12} {achieved:<12} {verdict}", file=stream)
    return rows, mismatched


def apply_results(manifest: Manifest, records: Sequence[dict]) -> Manifest:
    """Return a manifest whose baselines/pins describe the generated records."""
    by_figure: dict[str, dict[tuple[str, str], dict]] = {}
    for record in records:
        by_figure.setdefault(record["figure"], {})[(record["locale"], record["theme"])] = record
    figures = []
    for figure in manifest.figures:
        fresh = by_figure.get(figure.id, {})
        merged = {(b.locale, b.theme): b for b in figure.captures if (b.locale, b.theme) not in fresh}
        for key, record in fresh.items():
            merged[key] = Baseline(
                locale=record["locale"], theme=record["theme"], sha256=record["sha256"],
                size=record["size"], width=record["width"], height=record["height"],
                pins_applied=tuple(record["pins_applied"]),
                pins_unavailable=tuple(record["pins_unavailable"]),
            )
        pins_applied, pins_unavailable = figure.pins_applied, figure.pins_unavailable
        if fresh:
            pins_applied = tuple(sorted({p for r in fresh.values() for p in r["pins_applied"]}))
            pins_unavailable = tuple(sorted({p for r in fresh.values() for p in r["pins_unavailable"]}))
        figures.append(replace(
            figure, pins_applied=pins_applied, pins_unavailable=pins_unavailable,
            captures=tuple(merged[key] for key in sorted(merged)),
        ))
    return replace(manifest, figures=tuple(figures))


# --- Display (xvfb starts a private server, never :0) -----------------------


def _display_exists(number: int) -> bool:
    return Path(f"/tmp/.X11-unix/X{number}").exists() or Path(f"/tmp/.X{number}-lock").exists()


def _free_display_number(start: int = 90, stop: int = 140) -> int:
    for number in range(start, stop):
        if not _display_exists(number):
            return number
    raise FigureError(f"no free X display number in {start}..{stop}")


@contextmanager
def display_context(backend: str = "xvfb") -> Iterator[str]:
    """Provide a DISPLAY for the captures; never defaults to ``:0``.

    ``native`` uses the caller's DISPLAY (fails loudly when absent); ``xvfb``
    starts a private server, waits for its socket, and tears it down.
    """
    if backend not in BACKENDS:
        raise ValueError(f"unknown backend {backend!r}; expected one of {BACKENDS}")
    previous = os.environ.get("DISPLAY")
    if backend == "native":
        if not (previous or "").strip():
            raise FigureError("backend 'native' needs an existing DISPLAY; use --backend xvfb to start one")
        os.environ.setdefault("LIBGL_ALWAYS_SOFTWARE", "1")
        yield previous
        return
    if shutil.which("Xvfb") is None:
        raise FigureError("Xvfb not found on PATH; use --backend native with a private DISPLAY")
    number = _free_display_number()
    proc = subprocess.Popen(
        ["Xvfb", f":{number}", "-screen", "0", "1400x1000x24"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 10.0
        while not _display_exists(number):
            if proc.poll() is not None:
                raise FigureError(f"Xvfb :{number} exited with {proc.returncode}")
            if time.monotonic() > deadline:
                raise FigureError(f"Xvfb :{number} did not create its socket within 10s")
            time.sleep(0.05)
        os.environ["DISPLAY"] = f":{number}"
        os.environ.setdefault("LIBGL_ALWAYS_SOFTWARE", "1")
        yield os.environ["DISPLAY"]
    finally:
        if previous is None:
            os.environ.pop("DISPLAY", None)
        else:
            os.environ["DISPLAY"] = previous
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)


# --- CLI --------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="help_figures",
        description="Generate Help figures from a recipe and check them for drift.",
    )
    parser.add_argument("--list", action="store_true", help="list recipes and exit (no display)")
    parser.add_argument("--figure", action="append", metavar="ID", help="generate one figure (repeatable)")
    parser.add_argument("--all", action="store_true", help="generate every recipe figure")
    parser.add_argument(
        "--check", action="store_true",
        help="regenerate and compare sha256 against the manifest (exit 1 on drift)",
    )
    parser.add_argument(
        "--compare", action="store_true",
        help="regenerate and report generated WxH vs pinned/shipped WxH (exit 1 on dims-differ)",
    )
    parser.add_argument(
        "--write-manifest", "--update", dest="write_manifest", action="store_true",
        help="record sha256/size/dims for what was generated",
    )
    parser.add_argument("--out", default=None, help="output dir (default: a fresh temp dir)")
    parser.add_argument(
        "--backend", choices=BACKENDS, default="xvfb",
        help="xvfb: start a private server (default); native: use the current DISPLAY",
    )
    parser.add_argument("--locale", action="append", choices=LOCALES, help="restrict locales")
    parser.add_argument("--theme", action="append", choices=THEMES, help="restrict themes")
    parser.add_argument(
        "--manifest", default=str(MANIFEST_PATH), help=f"recipe path (default: {MANIFEST_PATH.name})"
    )
    return parser


def _list_recipes(manifest: Manifest) -> int:
    print(f"Help figures ({len(manifest.figures)}) — schema_version {manifest.schema_version}:")
    for figure in sorted(manifest.figures, key=lambda item: item.id):
        crop = "crop=%dx%d+%d+%d" % figure.crop if figure.crop else "crop=none"
        status = "covered" if figure.covered else f"uncovered:{figure.reason}"
        size = "%dx%d" % figure.size if figure.size else "default"
        variants = figure_variant_count(figure)
        layout = "flat" if variants <= 1 else "assets/<locale>/<theme>"
        print(
            f"  {figure.id:<26} surface={figure.surface:<18} size={size:<9} "
            f"locales={','.join(sorted(figure.locales))} "
            f"themes={','.join(sorted(figure.themes))} variants={variants}({layout}) {crop} {status}"
        )
        print(f"    -> {figure.destination or '(no shipped figure)'}")
        if figure.note:
            print(f"    note: {figure.note}")
    print("Surfaces (capture_surface.SURFACES): " + ", ".join(sorted(capture_surface.SURFACES)))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        manifest = load_manifest(args.manifest)
    except ManifestError as exc:
        print(f"manifest error: {exc}", file=sys.stderr)
        return 2

    if args.list:
        return _list_recipes(manifest)
    if args.all and args.figure:
        parser.error("--all and --figure are mutually exclusive")
    if not (args.all or args.figure or args.check or args.compare):
        parser.error("choose one of: --all, --figure ID, --check, --compare, --list")
    if args.check and args.write_manifest:
        parser.error("--check does not write the manifest")
    if args.compare and (args.check or args.write_manifest):
        parser.error("--compare only reports sizes; do not combine it with --check/--write-manifest")

    selected = manifest
    if args.figure:
        known = {figure.id for figure in manifest.figures}
        if unknown := [figure_id for figure_id in args.figure if figure_id not in known]:
            print(f"unknown figure: {', '.join(unknown)}; known: {', '.join(sorted(known))}", file=sys.stderr)
            return 2
        picked = {f.id: f for f in manifest.figures if f.id in args.figure}
        for figure in picked.values():
            if not figure.covered:
                print(
                    f"figure {figure.id!r} is uncovered ({figure.reason}) — nothing to generate",
                    file=sys.stderr,
                )
                return 2
        selected = replace(manifest, figures=tuple(picked.values()))

    out_dir = Path(args.out).expanduser() if args.out else Path(tempfile.mkdtemp(prefix="help-figures-"))
    print(f"output: {out_dir}", file=sys.stderr)
    try:
        with display_context(args.backend):
            if args.check:
                return check_figures(selected, out_dir, locales=args.locale, themes=args.theme)
            if args.compare:
                return compare_sizes(selected, out_dir, locales=args.locale, themes=args.theme)
            records = generate(selected, out_dir, locales=args.locale, themes=args.theme)
            print_parity_table(selected, records)
    except FigureError as exc:  # CropError subclasses FigureError
        print(f"capture failed: {exc}", file=sys.stderr)
        return 2

    if args.write_manifest:
        write_manifest(args.manifest, apply_results(manifest, records))
        print(f"wrote {args.manifest}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
