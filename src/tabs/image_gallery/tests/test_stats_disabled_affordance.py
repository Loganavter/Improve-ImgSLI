"""Disabled stats-strip action buttons must read as disabled.

Falsification (pre-fix): a ``variant="ghost"`` Button with a host-set
foreground/border renders identically enabled and disabled — the ghost
resolver ignores DISABLED and the text/border overrides have no disabled
branch — so "Compare finalists"/"Keep best" looked lit while dead. The host
therefore has to swap the tokens on the enabled↔disabled boundary, mirroring
``StatsStrip.set_rejected_count``.
"""

from __future__ import annotations

from tabs.image_gallery.ui.stats_strip import (
    StatsStrip,
    _flyout_border_color,
    _header_text_color,
    _stats_text_color,
    _thin_border_color,
)


def _dimmed_fg():
    return _header_text_color()


def _dimmed_border():
    return _flyout_border_color()


def _bright_fg():
    return _stats_text_color()


def _bright_border():
    return _thin_border_color()


def test_new_compare_button_starts_dimmed(qtbot) -> None:
    strip = StatsStrip()
    qtbot.addWidget(strip)
    btn = strip._compare_btn
    assert not btn.isEnabled()
    assert btn.getForegroundColor() == _dimmed_fg()
    assert btn.borderColor() == _dimmed_border()


def test_new_keep_button_starts_dimmed(qtbot) -> None:
    strip = StatsStrip()
    qtbot.addWidget(strip)
    btn = strip._keep_btn
    assert not btn.isEnabled()
    assert btn.getForegroundColor() == _dimmed_fg()
    assert btn.borderColor() == _dimmed_border()


def test_compare_disabled_affordance_differs_then_restores(qtbot) -> None:
    strip = StatsStrip()
    qtbot.addWidget(strip)

    strip.set_action_states(keep_best=False, compare_finalists=True)
    enabled_fg = strip._compare_btn.getForegroundColor()
    enabled_border = strip._compare_btn.borderColor()
    assert strip._compare_btn.isEnabled()
    assert enabled_fg == _bright_fg()
    assert enabled_border == _bright_border()

    strip.set_action_states(keep_best=False, compare_finalists=False)
    assert not strip._compare_btn.isEnabled()
    assert strip._compare_btn.getForegroundColor() == _dimmed_fg()
    assert strip._compare_btn.borderColor() == _dimmed_border()
    # The dimmed look is actually different from the enabled look (the bug:
    # they were rendered identically).
    assert strip._compare_btn.getForegroundColor() != enabled_fg
    assert strip._compare_btn.borderColor() != enabled_border

    strip.set_action_states(keep_best=False, compare_finalists=True)
    assert strip._compare_btn.isEnabled()
    assert strip._compare_btn.getForegroundColor() == enabled_fg
    assert strip._compare_btn.borderColor() == enabled_border


def test_keep_disabled_affordance_differs_then_restores(qtbot) -> None:
    strip = StatsStrip()
    qtbot.addWidget(strip)

    strip.set_action_states(keep_best=True, compare_finalists=False)
    enabled_fg = strip._keep_btn.getForegroundColor()
    enabled_border = strip._keep_btn.borderColor()
    assert strip._keep_btn.isEnabled()

    strip.set_action_states(keep_best=False, compare_finalists=False)
    assert not strip._keep_btn.isEnabled()
    assert strip._keep_btn.getForegroundColor() == _dimmed_fg()
    assert strip._keep_btn.borderColor() == _dimmed_border()
    assert strip._keep_btn.getForegroundColor() != enabled_fg
    assert strip._keep_btn.borderColor() != enabled_border

    strip.set_action_states(keep_best=True, compare_finalists=False)
    assert strip._keep_btn.isEnabled()
    assert strip._keep_btn.getForegroundColor() == enabled_fg
    assert strip._keep_btn.borderColor() == enabled_border


def test_theme_flip_keeps_disabled_button_dimmed(qtbot) -> None:
    """A theme flip must not re-brighten an already-disabled action button."""
    strip = StatsStrip()
    qtbot.addWidget(strip)
    strip.set_action_states(keep_best=False, compare_finalists=False)
    strip._on_gallery_theme_changed()
    assert not strip._compare_btn.isEnabled()
    assert strip._compare_btn.getForegroundColor() == _dimmed_fg()
    assert strip._compare_btn.borderColor() == _dimmed_border()
    assert not strip._keep_btn.isEnabled()
    assert strip._keep_btn.getForegroundColor() == _dimmed_fg()
    assert strip._keep_btn.borderColor() == _dimmed_border()
