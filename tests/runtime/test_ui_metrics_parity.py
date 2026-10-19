"""UI-metrics runtime parity: registered surfaces re-derive on a metrics change.

Each surface below is a real app widget built offscreen whose derived
geometry is owned by a handler migrated to the unified channel
(``connect_ui_metrics``) in wave A1. The harness
(``tests/helpers/ui_metrics_parity.py``) changes the UI font and the scale
through the toolkit singletons and asserts the geometry actually re-derives
under each axis the surface declares — the behavioural half of the P0 gate
(the AST contract in ``tests/contracts/test_ui_metrics_contracts.py`` is the
shape half).
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QDialog, QHBoxLayout

from tests.helpers.ui_metrics_parity import (
    MetricsSurface,
    assert_reflows_on_metrics_change,
)


def _tr(key: str, default: str = "", *args, **kwargs) -> str:
    return default or key


# ---------------------------------------------------------------------------
# Surface builders — each returns (widget, probe); the probe snapshots the
# derived geometry the surface's OWN metrics handler owns.
# ---------------------------------------------------------------------------


def _build_csd_menu_strip(qapp, monkeypatch):
    """CsdMenuStrip: trigger widths measured from the scaled UI font."""
    from ui.main_window.csd_menu_strip import (
        CsdMenuSpec,
        ContextMenuAction,
        CsdMenuStrip,
    )

    strip = CsdMenuStrip(
        [
            CsdMenuSpec(
                label="File",
                entries=[ContextMenuAction("open", "Open", shortcut="Ctrl+O")],
                on_triggered=lambda *_: None,
            ),
            CsdMenuSpec(
                label="Help",
                entries=[ContextMenuAction("about", "About")],
                on_triggered=lambda *_: None,
            ),
        ]
    )

    def probe():
        return (strip.height(), *(b.width() for b in strip._buttons))

    return strip, probe


def _build_help_back_bar(qapp, monkeypatch):
    """HelpBackBar: crumb fixed widths measured from the scaled UI font."""
    from plugins.help.back_bar import HelpBackBar

    bar = HelpBackBar()
    bar.set_breadcrumb((("a", "Overview"), ("b", "Details")))

    def probe():
        out = []
        for i in range(bar._crumbs_layout.count()):
            w = bar._crumbs_layout.itemAt(i).widget()
            if w is not None:
                out.append((w.width(), w.height()))
        return tuple(out)

    return bar, probe


def _build_dialog_action_bar(qapp, monkeypatch):
    """DialogActionBar: height pin derived from button minimums + sizeHint."""
    from ui.widgets.form_controls import DialogActionBar

    bar = DialogActionBar("OK", "Cancel")

    def probe():
        return (bar.minimumHeight(), bar.maximumHeight())

    return bar, probe


def _build_value_slider_row(qapp, monkeypatch):
    """ValueSliderRow: pad width derived from the label's font metrics."""
    from ui.widgets.slider_hint import ValueSlider, ValueSliderRow

    slider = ValueSlider()
    slider.setRange(1, 100)
    slider.setValue(50)
    dialog = QDialog()
    layout = QHBoxLayout(dialog)
    row = ValueSliderRow(slider)
    layout.addWidget(row, 1)
    dialog.show()

    def probe():
        return (row._right_pad.width(), row._slider.height())

    return dialog, probe


def _build_recent_shelf_panel(qapp, monkeypatch):
    """RecentProjectsPanel: shelf margins/spacing are design-px captured ints."""
    from services.io.recent_projects import SORT_NAME, VIEW_LIST
    from tabs.session_picker.recent.panel import RecentProjectsPanel

    monkeypatch.setattr(
        "tabs.session_picker.recent.panel.get_recent_view_mode",
        lambda **kwargs: VIEW_LIST,
    )
    monkeypatch.setattr(
        "tabs.session_picker.recent.panel.get_recent_sort_mode",
        lambda **kwargs: SORT_NAME,
    )
    monkeypatch.setattr(
        "tabs.session_picker.recent.panel.list_recent_projects",
        lambda **kwargs: [],
    )
    panel = RecentProjectsPanel(translate=_tr)
    panel.refresh()

    def probe():
        layout = panel.layout()
        assert layout is not None
        margins = layout.contentsMargins()
        return (
            margins.left(),
            margins.top(),
            margins.right(),
            margins.bottom(),
            layout.spacing(),
        )

    return panel, probe


class _PickerSession:
    def __init__(self) -> None:
        self.id = "picker-session"


class _Context:
    """Minimal SessionPickerWidget context (mirrors the keyboard tests)."""

    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self._session = _PickerSession()

    def _tr(self, key: str, default: str = "") -> str:
        return default or key

    def call_service(self, name: str, *args, **kwargs):
        self.calls.append((name, args, kwargs))
        if name == "list_session_blueprints":
            return ()
        return None

    def get_active_session(self):
        return self._session


def _build_session_picker_page(qapp, monkeypatch):
    """SessionPickerPage: min size + content margins/cards spacing are px ints."""
    from tabs.session_picker.widget import SessionPickerWidget

    monkeypatch.setattr(
        "tabs.session_picker.recent.panel.list_recent_projects",
        lambda **kwargs: [],
    )
    widget = SessionPickerWidget(context=_Context())

    def probe():
        content = widget._page_content
        layout = content.layout() if content is not None else None
        margins = layout.contentsMargins() if layout is not None else None
        return (
            widget.minimumWidth(),
            widget.minimumHeight(),
            widget._cards_layout.spacing(),
            margins.left() if margins is not None else -1,
            layout.spacing() if layout is not None else -1,
        )

    return widget, probe


def _build_ic_scaled_icon_label(qapp, monkeypatch):
    """ScaledIconLabel (image_compare layout site): fixed px captured ints."""
    from tabs.image_compare.icons import Icon
    from tabs.image_compare.ui.layout import ScaledIconLabel

    label = ScaledIconLabel(Icon.MAGNIFIER_SIZE, 18)

    def probe():
        return (label.width(), label.height())

    return label, probe


def _build_context_menu_rows(qapp, monkeypatch):
    """Toolkit ContextMenu: row heights/paddings/gutters are scaled design px.

    Registered as a RATIO surface: the whole menu (row heights + width from the
    scaled paddings/gutters) must grow by the scale factor — the owner's
    "flyout/menu row pitch does not follow the scale" report, closed in the
    toolkit (rows.py/content.py) and pinned here so it cannot regress.
    """
    from PySide6.QtWidgets import QWidget as _QWidget

    from sli_ui_toolkit.widgets import ContextMenu, ContextMenuAction

    parent = _QWidget()
    parent.resize(640, 480)
    menu = ContextMenu(
        parent,
        entries=(
            ContextMenuAction("rename", "Rename entry"),
            ContextMenuAction("delete", "Delete entry", shortcut="Ctrl+D"),
        ),
    )

    def probe():
        hint = menu.sizeHint()
        return (hint.width(), hint.height())

    return menu, probe


def _build_button_chip(qapp, monkeypatch):
    """Toolkit Button chip: content insets + icon/text gap are scaled design px.

    Registered as a RATIO surface — this is the owner's "the separate sections
    in the Button API keep design px" report (a card chip: icon + text), closed
    by resolving the padding/gap at use time in the toolkit.
    """
    from sli_ui_toolkit.widgets import Button

    chip = Button(text="Chip label")

    def probe():
        hint = chip.sizeHint()
        return (hint.width(), hint.height())

    return chip, probe


SURFACES: dict[str, MetricsSurface] = {
    # Host chrome — font AND scale derived.
    "csd_menu_strip": MetricsSurface(
        "csd_menu_strip", _build_csd_menu_strip, frozenset({"font", "scale"})
    ),
    "help_back_bar": MetricsSurface(
        "help_back_bar", _build_help_back_bar, frozenset({"font", "scale"})
    ),
    "dialog_action_bar": MetricsSurface(
        "dialog_action_bar", _build_dialog_action_bar, frozenset({"scale"})
    ),
    # Tab surfaces.
    "value_slider_row": MetricsSurface(
        "value_slider_row", _build_value_slider_row, frozenset({"font", "scale"})
    ),
    "recent_shelf_panel": MetricsSurface(
        "recent_shelf_panel", _build_recent_shelf_panel, frozenset({"scale"})
    ),
    "session_picker_page": MetricsSurface(
        "session_picker_page", _build_session_picker_page, frozenset({"scale"})
    ),
    "ic_scaled_icon_label": MetricsSurface(
        "ic_scaled_icon_label", _build_ic_scaled_icon_label, frozenset({"scale"})
    ),
    # Toolkit chrome the owner reported broken on a LIVE scale change — these
    # are RATIO surfaces (all probe values are factor-proportional design px),
    # so the harness also catches DOUBLE scaling, not just staleness.
    "context_menu_rows": MetricsSurface(
        "context_menu_rows",
        _build_context_menu_rows,
        frozenset({"scale"}),
        expect_ratio=True,
    ),
    "button_chip_sections": MetricsSurface(
        "button_chip_sections",
        _build_button_chip,
        frozenset({"scale"}),
        expect_ratio=True,
    ),
}


@pytest.mark.parametrize("name", sorted(SURFACES))
def test_surface_reflows_on_metrics_change(qapp, monkeypatch, name):
    assert_reflows_on_metrics_change(SURFACES[name], qapp=qapp, monkeypatch=monkeypatch)


# ---------------------------------------------------------------------------
# Harness falsification — a gate nobody has seen fail is not a gate. Both
# diseases must be caught, and the failure must NAME which one it is.
# ---------------------------------------------------------------------------


def _constant_surface() -> MetricsSurface:
    """A surface that never re-derives (the class bug) — must be STALE."""
    from PySide6.QtWidgets import QWidget

    def build(qapp, monkeypatch):
        widget = QWidget()

        def probe():
            return (10,)  # frozen: exactly what a baked design px looks like

        return widget, probe

    return MetricsSurface("synthetic_stale", build, frozenset({"scale"}), expect_ratio=True)


def _double_scaled_surface() -> MetricsSurface:
    """A surface that scales twice (a scale-resolved value re-entered) — must be DOUBLE."""
    from PySide6.QtWidgets import QWidget

    from sli_ui_toolkit.managers import UiScale
    from sli_ui_toolkit.ui.managers.ui_metrics import AXIS_SCALE, connect_ui_metrics

    def build(qapp, monkeypatch):
        widget = QWidget()
        state = {"v": 100.0}

        def on_metrics(*_args):
            state["v"] = 100.0 * (UiScale.get_instance().factor() ** 2)

        connect_ui_metrics(widget, on_metrics, axes=frozenset({AXIS_SCALE}))
        return widget, lambda: (state["v"],)

    return MetricsSurface(
        "synthetic_double", build, frozenset({"scale"}), expect_ratio=True
    )


def test_gate_catches_a_stale_surface(qapp):
    with pytest.raises(AssertionError) as exc:
        assert_reflows_on_metrics_change(_constant_surface(), qapp=qapp)
    assert "STALE" in str(exc.value), str(exc.value)


def test_gate_catches_a_double_scaled_surface(qapp):
    with pytest.raises(AssertionError) as exc:
        assert_reflows_on_metrics_change(_double_scaled_surface(), qapp=qapp)
    assert "DOUBLE-SCALED" in str(exc.value), str(exc.value)
