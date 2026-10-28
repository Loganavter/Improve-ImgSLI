"""Icons must be rasterized at the paint device's ratio, not the application's.

Measured 2026-10-28 (KDE/Wayland, 125 %): `QGuiApplication.devicePixelRatio()`
is **2.0** while the window paints at **1.25**. `QIcon.pixmap(size)` (and
`pixmap(w, h)`) uses the application ratio, so a 22 px icon came back as
44x44 @2.0 and the painter squeezed it into 27.5 device px — a 0.625 resample
that left every thin stroke ragged. The same icons were crisp at 100 %.

The sanctioned shapes are `normalized_icon_pixmap(icon, px, dpr=...)` (the
toolkit helper) and `QIcon.pixmap(size, ratio)` when going direct. This gate
scans `src/` for the two bare forms; the allowlist below is shrink-only and
carries a reason per entry.

Recolouring sites are legitimate: they rasterize an icon at its own native
size to tint it and return a `QIcon`, and the consumer rasterizes again at the
paint ratio.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src"

#: ``(relative_path, function) -> reason``. Shrink-only.
ALLOWLIST: dict[tuple[str, str], str] = {
    (
        "src/plugins/help/icons.py",
        "_monochrome",
    ): (
        "recolour source: rasterizes at the icon's own availableSizes() (or a "
        "256 px fallback) to alpha-mask it into one colour and returns a QIcon; "
        "the consumer rasterizes again at the paint ratio."
    ),
    (
        "src/tabs/image_gallery/ui/card/context_menu/icons.py",
        "_resolve_menu_icon",
    ): (
        "recolour source: 64 px pixmap tinted and wrapped back into a QIcon "
        "(cached, resolved lazily at paint time by the toolkit row, which then "
        "uses its own dpr)."
    ),
    (
        "src/tabs/image_gallery/ui/quick_look/overlay_build/icons.py",
        "_resolve_danger_trash_icon",
    ): (
        "recolour source: same shape as the card menu icon — 64 px tinted "
        "pixmap returned as a QIcon for the toolkit row to rasterize."
    ),
}


def _call_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    if isinstance(node.func, ast.Name):
        return node.func.id
    return None


def _is_ratio_arg(node: ast.AST) -> bool:
    text = ast.unparse(node).lower()
    return "dpr" in text or "pixelratio" in text or text == "ratio" or text.endswith("_ratio")


def _enclosing(tree: ast.Module, lineno: int) -> str:
    best: ast.AST | None = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.lineno <= lineno <= (node.end_lineno or node.lineno):
                if best is None or node.lineno > best.lineno:  # type: ignore[attr-defined]
                    best = node
    return getattr(best, "name", "<module>")


def _hits(tree: ast.Module) -> list[tuple[int, str]]:
    """``(lineno, shape)`` for every icon raster without an explicit ratio."""
    out: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _call_name(node)
        if name == "normalized_icon_pixmap":
            if not any(keyword.arg == "dpr" for keyword in node.keywords):
                out.append((node.lineno, "normalized_icon_pixmap() without dpr="))
        elif name == "pixmap" and node.args:
            if len(node.args) == 1 or not any(_is_ratio_arg(arg) for arg in node.args):
                out.append((node.lineno, "QIcon.pixmap(...) without a ratio"))
    return out


def scan() -> list[tuple[str, str, int, str]]:
    found: list[tuple[str, str, int, str]] = []
    for path in sorted(SRC.rglob("*.py")):
        rel = "src/" + path.relative_to(SRC).as_posix()
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:  # pragma: no cover - a broken file fails elsewhere
            continue
        for lineno, shape in _hits(tree):
            found.append((rel, _enclosing(tree, lineno), lineno, shape))
    return found


def test_no_icon_is_rasterized_at_the_application_ratio() -> None:
    unallowed = [
        item
        for item in scan()
        if (item[0], item[1]) not in ALLOWLIST
    ]
    assert not unallowed, (
        "icon rasterized without the paint device's ratio (it will be resampled "
        "on a fractional-scaling screen):\n  "
        + "\n  ".join(f"{path}:{line} {shape} in {func}()" for path, func, line, shape in unallowed)
    )


def test_allowlist_is_shrink_only() -> None:
    live = {(item[0], item[1]) for item in scan()}
    stale = sorted(key for key in ALLOWLIST if key not in live)
    assert not stale, (
        "allowlist entries no longer match a live site (fix landed or code "
        f"moved) — delete them: {stale}"
    )


_BAD = '''
def _draw(self, icon, painter):
    self.label.setPixmap(icon.pixmap(16, 16))
    pm = icon.pixmap(QSize(22, 22))
    return normalized_icon_pixmap(icon, 22)
'''

_GOOD = '''
def _draw(self, icon, painter, widget):
    a = normalized_icon_pixmap(icon, 22, dpr=painter_dpr(painter))
    b = normalized_icon_pixmap(icon, 22, dpr=widget_dpr(widget))
    ratio = widget_dpr(widget)
    c = icon.pixmap(QSize(22, 22), ratio)
    return a or b or c
'''


def test_detector_fires_on_the_pre_fix_shape_and_is_silent_on_the_fix() -> None:
    bad = _hits(ast.parse(_BAD))
    good = _hits(ast.parse(_GOOD))
    assert len(bad) == 3, bad
    assert good == [], good


@pytest.mark.parametrize("shape", ["pixmap(16, 16)", "pixmap(QSize(16, 16))"])
def test_both_bare_pixmap_forms_are_flagged(shape: str) -> None:
    tree = ast.parse(f"def f(icon):\n    return icon.{shape}\n")
    assert len(_hits(tree)) == 1
