"""Ratchet: every painted text in the app must be scale-resolved.

Mirror of the toolkit's ``tests/test_text_paint_scan.py`` (which guards
``sli_ui_toolkit``): a paint function calling ``drawText`` must either set
its font from a scale-resolving helper itself, or carry a documented
allowance explaining why its font is already scale-resolved.

Two failure classes (both found live):

* **Unscaled text** — drawn with the raw painter font (design-sized app
  font); at UI scale > 1.0 the label stays small (UI-inspector tag, drop
  preview hint).
* **Double-scaled text** — ``paint_font()``/``rebase_font()`` over a font
  that is already scale-resolved, multiplying the factor a second time
  (context-menu rows, fixed in the toolkit).

Canvas scene text (labels rasterized in framebuffer-px for the QRhi scene)
is intentionally *not* UI-scaled — it is allowlisted below.
"""

from __future__ import annotations

import ast
from pathlib import Path

from tests.contracts._framework import SRC

_SCALE_FONT_HELPERS = ("ui_font", "paint_font", "rebase_family", "rebase_font", "apply_ui_font")
_PAINT_FONT_HELPERS = ("paint_font", "rebase_font")

# (path, function name) -> reason. These paint functions draw text without a
# scale-resolving helper because the font they use is either already
# scale-resolved (HUD labels pinned via apply_ui_font) or sized in
# framebuffer-px for the canvas scene (not UI space).
_TEXT_WITHOUT_SET_FONT: dict[tuple[str, str], str] = {
    ("tabs/multi_compare/ui/layer_labels.py", "paint_layer_label"): (
        "canvas scene text: label rasterized in framebuffer px (fb-space), "
        "sized by the scene style, not the UI scale"
    ),
    ("tabs/multi_compare/ui/layer_labels.py", "rasterize_layer_label"): (
        "canvas scene text: label rasterized in framebuffer px (fb-space), "
        "sized by the scene style, not the UI scale"
    ),
    (
        "tabs/image_compare/canvas/features/filename_overlay/render/label_raster.py",
        "rasterize_label",
    ): (
        "canvas scene text: filename label rasterized from a caller-supplied "
        "scene font (design px of the overlay style), not the UI scale"
    ),
}

# (path, function name) -> reason. paint_font()/rebase_font() multiply the
# UiScale factor — only safe on design-sized widget fonts.
_PAINT_FONT_ALLOWED: dict[tuple[str, str], str] = {
    ("shared_toolkit/ui/message_dialog.py", "paintEvent"): (
        "badge glyph paints with paint_font(self, pixel_size=...) over the "
        "dialog's design-sized font"
    ),
}


def _paint_functions() -> list[tuple[Path, ast.FunctionDef]]:
    found: list[tuple[Path, ast.FunctionDef]] = []
    for path in sorted(SRC.rglob("*.py")):
        if "resources" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            calls = [c for c in ast.walk(node) if isinstance(c, ast.Call)]
            has_text = any(
                isinstance(c.func, ast.Attribute) and c.func.attr == "drawText"
                for c in calls
            )
            if has_text:
                found.append((path, node))
    return found


def _calls(fn: ast.FunctionDef, names: set[str]) -> list[ast.Call]:
    out = []
    for c in ast.walk(fn):
        if not isinstance(c, ast.Call):
            continue
        if isinstance(c.func, ast.Attribute) and c.func.attr in names:
            out.append(c)
        elif isinstance(c.func, ast.Name) and c.func.id in names:
            out.append(c)
    return out


def _rel_path(path: Path) -> str:
    return str(path.relative_to(SRC)).replace("\\", "/")


def test_every_painted_text_has_a_scale_resolved_font():
    """drawText requires setFont / scale helper / documented reason."""
    violations: list[str] = []
    for path, fn in _paint_functions():
        key = (_rel_path(path), fn.name)
        if _calls(fn, {"setFont"}):
            continue
        if _calls(fn, set(_SCALE_FONT_HELPERS)):
            continue
        if key in _TEXT_WITHOUT_SET_FONT:
            continue
        violations.append(
            f"{key[0]}::{key[1]} draws text but never calls setFont() or a "
            f"scale-resolving helper ({', '.join(_SCALE_FONT_HELPERS)}) — add "
            "a setFont(ui_font(...))/paint_font(...) call, or an entry in "
            "_TEXT_WITHOUT_SET_FONT with the reason the font is already "
            "scale-resolved"
        )
    assert not violations, "\n".join(violations)


def test_paint_font_only_on_design_sized_fonts():
    """paint_font()/rebase_font() near drawText needs an allowance."""
    violations: list[str] = []
    for path, fn in _paint_functions():
        key = (_rel_path(path), fn.name)
        if not _calls(fn, set(_PAINT_FONT_HELPERS)):
            continue
        if key in _PAINT_FONT_ALLOWED:
            continue
        violations.append(
            f"{key[0]}::{key[1]} calls {_PAINT_FONT_HELPERS} while drawing "
            "text — these multiply the UiScale factor, so they are only safe "
            "on design-sized fonts; use rebase_family() (size-preserving) for "
            "already scale-resolved fonts, or add an entry in "
            "_PAINT_FONT_ALLOWED with the reason"
        )
    assert not violations, "\n".join(violations)


def test_scan_catalogue_stays_current():
    """Allowlists must not rot: every entry must still exist and draw text."""
    functions = {(_rel_path(p), fn.name) for p, fn in _paint_functions()}
    for key in list(_TEXT_WITHOUT_SET_FONT) + list(_PAINT_FONT_ALLOWED):
        assert key in functions, (
            f"allowlist entry {key} no longer matches any drawText function — "
            "remove it"
        )