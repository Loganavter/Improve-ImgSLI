"""``capture_surface`` owns the process frame it pins — and hands it back.

The capture MUST render with the product's canonical face (Source Sans 3 +
Noto Sans SC, 12 pt) at the canonical DPI: the Help figures are sha256
baselines, so a host font/DPI difference is a different product. What it must
not do is leave those pins applied to the process: the 12 pt face followed
every later widget, widened the toolkit's text-derived controls (gallery
toolbar pick button 132 -> 148 px) and failed the toolbar design-px pin
(measured 2026-10-22, ``tests/devtools/test_help_figures.py`` polluting
``src/tabs/image_gallery/tests/test_gallery_toolbar_ui_scale.py``).

These tests pin both halves: the canonical frame is still applied *inside* the
scope (so a future edit cannot silently drop or weaken it), and the app's own
font/environment are back *after* it (so it cannot leak again).

Falsification: on the pre-fix module ``restore_app_font`` does not exist and
``canonical_frame_scope`` leaves ``Source Sans 3`` / ``QT_SCALE_FACTOR=1``
behind — both assertions below fail.
"""

from __future__ import annotations

import os

from PySide6.QtGui import QFont

from devtools import capture_surface as cs


def _own_font(app) -> QFont:
    """A resolved copy — ``QFont()`` is unresolved and follows the app font."""
    return QFont(app.font())


def test_capture_scope_keeps_the_canonical_face(qapp):
    """Inside the scope the frame is the canonical one, CJK fallback included."""
    with cs.canonical_frame_scope(qapp) as scoped_app:
        assert scoped_app is qapp
        assert tuple(qapp.font().families()[:2]) == (
            cs.BUNDLED_FONT_FAMILY,
            cs.BUNDLED_CJK_FONT_FAMILY,
        )
        assert cs.BUNDLED_FONT_FAMILY == "Source Sans 3"
        assert qapp.font().pointSizeF() == 12.0
        # A real Han glyph run, not just the family list: a cleared fallback
        # chain would still pass a families() check on some hosts.
        assert cs.BUNDLED_CJK_FONT_FAMILY in cs._cjk_run_families(qapp.font())


def test_capture_scope_gives_the_app_font_back(qapp):
    """After the capture the app owns its font again, and keeps doing so."""
    for _ in range(2):  # second pass proves the anchor is re-taken cleanly
        before = _own_font(qapp)
        with cs.canonical_frame_scope(qapp):
            assert qapp.font().family() == cs.BUNDLED_FONT_FAMILY
        after = _own_font(qapp)
        assert after.families() == before.families(), (
            f"app font leaked: {after.families()!r} != {before.families()!r}"
        )
        assert after.pointSizeF() == before.pointSizeF(), (
            f"app point size leaked: {after.pointSizeF()} != {before.pointSizeF()}"
        )


def test_capture_scope_gives_the_scale_and_dpi_back(qapp, monkeypatch):
    """``QT_SCALE_FACTOR``/``QT_FONT_DPI`` are pinned inside, restored outside."""
    cs.restore_canonical_env()  # drop any anchor left by an earlier test
    monkeypatch.setenv("QT_SCALE_FACTOR", "2")
    monkeypatch.setenv("QT_FONT_DPI", "72")

    with cs.canonical_frame_scope(qapp):
        assert os.environ["QT_SCALE_FACTOR"] == "1"
        assert os.environ["QT_FONT_DPI"] == str(cs.CANONICAL_DPI)

    assert os.environ["QT_SCALE_FACTOR"] == "2"
    assert os.environ["QT_FONT_DPI"] == "72"


def test_restore_is_a_no_op_without_an_anchor(qapp, monkeypatch):
    """A plain test session pays nothing and no variable is invented."""
    cs.restore_app_font()
    cs.restore_canonical_env()
    monkeypatch.delenv("QT_SCALE_FACTOR", raising=False)
    monkeypatch.delenv("QT_FONT_DPI", raising=False)

    assert cs.restore_app_font() is False
    assert cs.restore_canonical_env() is False
    assert "QT_SCALE_FACTOR" not in os.environ
    assert "QT_FONT_DPI" not in os.environ
