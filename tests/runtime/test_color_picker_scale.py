"""ColorPickerDialog: content-covering minimum + live UI-scale re-derivation.

L5 regression (owner report 2026-10-19, with screenshot): after a UI-scale
change the picker was destroyed — the value field collapsed to 0 px (its
digits sat under the ``HEX`` format button), the RGBA fields overlapped each
other and the OK/Cancel bar overlapped the recents strip. The dialog kept a
fixed ``260x300`` minimum (``GeometryApplyPolicy.minimum_floor``) that is
*below* its laid-out content, so a remembered small size crushed every row,
and the chrome px were baked at import time, so a later scale change could
never re-derive them.

Three dogmas, all pinned against the REAL dialog widget:

1. ``minimumSize()`` covers the laid-out content (``minimumSizeHint()``) — a
   remembered/restored small size cannot crush the rows.
2. the value field keeps a positive minimum width: the toolkit
   ``CustomLineEdit``'s own ``minimumSizeHint().width()`` is 0, so a row that
   merely ``addStretch``-es the rest collapses it.
3. every chrome px (margins/spacing/fixed sizes/value-field minimum) is
   resolved through ``scaled_px`` at USE time and re-derived on a live
   ``UiScale`` change, with the QWindow minimum re-pinned.

Constants below are the *expected* design-space values re-derived by the test
itself (``scaled_px(design)``), not read back from the module under test.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QPoint, QRect, QSettings
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

from sli_ui_toolkit.managers import UiScale, scaled_px
from tests.helpers.drain_until_stable import drain_until_stable
from ui.widgets.color import ColorPickerDialog, RecentColorsStore

# Design-space (unscaled) chrome the test re-derives for itself.
_ROOT_MARGIN_H = 16
_ROOT_MARGIN_TOP = 14
_ROOT_MARGIN_BOTTOM = 14
_ROOT_SPACING = 12
_FIELDS_SPACING = 6
_FORMAT_BTN = (46, 26)
_ACTION_BTN = (72, 30)
_VALUE_FIELD_MIN_W = 96

# The sibling controls the report says overlapped (plus the R/G/B/A labels,
# added from ``_field_labels`` in ``_mapped_rects``).
_SIBLINGS = (
    "_preview",
    "_hex_edit",
    "_format_btn",
    "_r_spin",
    "_g_spin",
    "_b_spin",
    "_a_spin",
    "_cancel_btn",
    "_ok_btn",
    "_recents_row",
)


@pytest.fixture
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(autouse=True)
def _factor_one():
    """UiScale is a process-wide singleton; leave the factor at 1.0."""
    UiScale.get_instance().set_factor(1.0)
    yield
    UiScale.get_instance().set_factor(1.0)


@pytest.fixture
def store(tmp_path):
    return RecentColorsStore(
        QSettings(os.path.join(str(tmp_path), "cfg.ini"), QSettings.Format.IniFormat)
    )


@pytest.fixture
def remembered_small(monkeypatch):
    """A too-small remembered dialog size (the owner's was 420x300).

    Injected through the real ``_load_remembered_size`` seam instead of the
    app's QSettings so the test never writes the user's config; the point is
    that a restored size *clamped to the content minimum* can no longer crush
    the rows.
    """
    monkeypatch.setattr(
        "shared_toolkit.ui.layout_sizing._load_remembered_size",
        lambda _key: (240, 260),
    )


def _dialog(store) -> ColorPickerDialog:
    store.add("#FF8800")
    store.add("#2288FF80")
    return ColorPickerDialog(QColor(255, 136, 0, 200), show_alpha=True, recents_store=store)


def _mapped_rects(dialog) -> dict[str, QRect]:
    def _map(widget) -> QRect:
        top_left = widget.mapTo(dialog, QPoint(0, 0))
        return QRect(top_left.x(), top_left.y(), widget.width(), widget.height())

    rects = {name: _map(getattr(dialog, name)) for name in _SIBLINGS}
    for index, label in enumerate(dialog._field_labels):
        rects[f"label{index}"] = _map(label)
    return rects


def _overlaps(dialog) -> list[str]:
    rects = _mapped_rects(dialog)
    names = list(rects)
    found: list[str] = []
    for index, first in enumerate(names):
        for second in names[index + 1 :]:
            inter = rects[first].intersected(rects[second])
            if inter.width() > 0 and inter.height() > 0:
                found.append(f"{first} X {second} ({inter.width()}x{inter.height()})")
    return found


def _settle(qapp, dialog):
    drain_until_stable(
        qapp,
        lambda: (
            dialog.width(),
            dialog.height(),
            dialog.minimumSize().width(),
            dialog.minimumSize().height(),
            dialog._hex_edit.width(),
        ),
        timeout_ms=2000,
        poll_ms=10,
        stable_frames=2,
    )


def test_minimum_covers_content_and_rows_do_not_overlap(qapp, store, remembered_small):
    """A restored small size must be clamped to the content minimum, and the
    declared minimum must cover the content (no row overlap at that size)."""
    dialog = _dialog(store)
    try:
        dialog.show()
        _settle(qapp, dialog)

        minimum = dialog.minimumSize()
        hint = dialog.minimumSizeHint()
        assert minimum.width() >= hint.width(), (
            f"declared minimum {minimum.width()}x{minimum.height()} is below the "
            f"laid-out content minimum {hint.width()}x{hint.height()} — a "
            f"restored/crushed window can overlap the rows"
        )
        assert minimum.height() >= hint.height(), (
            f"declared minimum {minimum.width()}x{minimum.height()} is below the "
            f"laid-out content minimum {hint.width()}x{hint.height()}"
        )
        # The dialog itself is at least its own content minimum (remembered
        # 240x260 was clamped up, not honoured).
        assert dialog.width() >= hint.width()
        assert dialog.height() >= hint.height()

        # The value field must not collapse to 0 px (the HEX-digits symptom).
        assert dialog._hex_edit.minimumWidth() > 0, "value field may collapse to 0 px"
        assert dialog._hex_edit.width() > 0, "value field laid out at 0 px"

        # And at the declared minimum the sibling controls still do not overlap.
        dialog.resize(minimum)
        _settle(qapp, dialog)
        assert _overlaps(dialog) == []
    finally:
        dialog.deleteLater()


def test_live_scale_change_re_derives_chrome_and_minimum(qapp, store, remembered_small):
    """``UiScale.set_factor`` + one bus turn must re-derive chrome, minimum and
    the QWindow minimum in place, with no overlaps at the new factor."""
    dialog = _dialog(store)
    try:
        dialog.show()
        _settle(qapp, dialog)

        minimum_at_1 = dialog.minimumSize()
        margins_at_1 = dialog.layout().contentsMargins()
        assert (
            margins_at_1.left(),
            margins_at_1.top(),
            margins_at_1.right(),
            margins_at_1.bottom(),
        ) == (
            scaled_px(_ROOT_MARGIN_H),
            scaled_px(_ROOT_MARGIN_TOP),
            scaled_px(_ROOT_MARGIN_H),
            scaled_px(_ROOT_MARGIN_BOTTOM),
        )
        assert dialog._hex_edit.minimumWidth() == scaled_px(_VALUE_FIELD_MIN_W)
        assert dialog._format_btn.size().toTuple() == (
            scaled_px(_FORMAT_BTN[0]),
            scaled_px(_FORMAT_BTN[1]),
        )

        # Live factor change — the chrome re-derives through the unified
        # metrics channel (connect_ui_metrics): the flush lands on a coalesced
        # zero-timer, not synchronously inside set_factor, so drain it.
        UiScale.get_instance().set_factor(1.5)
        _settle(qapp, dialog)

        margins = dialog.layout().contentsMargins()
        assert (
            margins.left(),
            margins.top(),
            margins.right(),
            margins.bottom(),
        ) == (
            scaled_px(_ROOT_MARGIN_H),
            scaled_px(_ROOT_MARGIN_TOP),
            scaled_px(_ROOT_MARGIN_H),
            scaled_px(_ROOT_MARGIN_BOTTOM),
        ), "root margins did not re-derive at the new factor"
        assert dialog.layout().spacing() == scaled_px(_ROOT_SPACING)
        assert dialog._fields_row.spacing() == scaled_px(_FIELDS_SPACING)
        assert dialog._format_btn.size().toTuple() == (
            scaled_px(_FORMAT_BTN[0]),
            scaled_px(_FORMAT_BTN[1]),
        )
        assert dialog._cancel_btn.minimumSize().toTuple() == (
            scaled_px(_ACTION_BTN[0]),
            scaled_px(_ACTION_BTN[1]),
        )
        assert dialog._ok_btn.minimumSize().toTuple() == (
            scaled_px(_ACTION_BTN[0]),
            scaled_px(_ACTION_BTN[1]),
        )
        assert dialog._hex_edit.minimumWidth() == scaled_px(_VALUE_FIELD_MIN_W)
        assert dialog._hue_slider.minimumHeight() == scaled_px(140)
        assert dialog._alpha_slider.minimumHeight() == scaled_px(140)

        minimum_at_1_5 = dialog.minimumSize()
        hint = dialog.minimumSizeHint()
        assert minimum_at_1_5.width() >= hint.width()
        assert minimum_at_1_5.height() >= hint.height()
        # Content grew with the factor (chrome exactly, whole dialog at least
        # the scaled chrome delta — the SV square's own minimum is fixed design
        # px, so the total is not a flat 1.5x).
        assert minimum_at_1_5.width() > minimum_at_1.width()
        assert minimum_at_1_5.height() > minimum_at_1.height()
        assert minimum_at_1_5.width() >= int(1.25 * minimum_at_1.width())

        handle = dialog.windowHandle()
        assert handle is not None, "shown dialog must have a QWindow"
        assert handle.minimumSize().width() >= minimum_at_1_5.width()
        assert handle.minimumSize().height() >= minimum_at_1_5.height()

        assert _overlaps(dialog) == []
        assert dialog._hex_edit.width() > 0

        # And back: restoring the factor restores the 1.0 minimum.
        UiScale.get_instance().set_factor(1.0)
        _settle(qapp, dialog)
        assert dialog.minimumSize() == minimum_at_1
        assert _overlaps(dialog) == []
    finally:
        dialog.deleteLater()
