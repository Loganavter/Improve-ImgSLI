"""Bundled CJK fallback: the product font chain must include Noto Sans SC.

Source Sans 3 has no Han glyphs, so ``FontManager`` appends the bundled Noto
Sans SC (SIL OFL 1.1) as the last family in every mode. Without it a zh UI
resolves Han text to whatever the host ships (or tofu on a bare machine), and
the help-figure captures stop being reproducible — the same failure the
toolkit's ``UiFont`` cleared-families bug caused (fixed in the toolkit).
"""

from __future__ import annotations

from PySide6.QtGui import QTextLayout

from shared_toolkit.ui.managers.font_manager import FontManager


def _glyph_run_families(font, text: str = "设置图像") -> tuple[str, ...]:
    layout = QTextLayout(text, font)
    layout.beginLayout()
    line = layout.createLine()
    layout.endLayout()
    return tuple(run.rawFont().familyName() for run in line.glyphRuns())


def test_builtin_mode_appends_the_bundled_cjk_family(qapp):
    manager = FontManager.get_instance()
    manager.set_font(mode="builtin")

    families = tuple(qapp.font().families())
    assert families[:2] == ("Source Sans 3", "Noto Sans SC")
    assert "Noto Sans SC" in _glyph_run_families(qapp.font())
    assert manager._ensure_cjk_loaded() == "Noto Sans SC"


def test_system_default_mode_keeps_the_cjk_fallback(qapp):
    manager = FontManager.get_instance()
    manager.set_font(mode="system_default")

    families = tuple(qapp.font().families())
    assert len(families) >= 2
    assert families[-1] == "Noto Sans SC"
    assert "Noto Sans SC" in _glyph_run_families(qapp.font())
