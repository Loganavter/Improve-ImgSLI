"""UI-metrics runtime parity: registered surfaces re-derive on a metrics change.

Each surface below is a real app widget built offscreen whose derived
geometry is owned by a handler migrated to the unified channel
(``connect_ui_metrics``) in wave A1. The harness
(``tests/helpers/ui_metrics_parity.py``) changes the UI font, the interface
scale and the live language through the production levers and asserts the
geometry/labels actually re-derive under each axis the surface declares — the
behavioural half of the P0 gate (the AST contract in
``tests/contracts/test_ui_metrics_contracts.py`` is the shape half).

Registered set (the docstring is the index; ``register_surface`` is the only
entry point, so a surface cannot be added without an explicit decision on the
two plan axes ``scale`` and ``language``):

Host chrome
    ``csd_menu_strip``, ``help_back_bar``, ``dialog_action_bar``,
    ``context_menu_rows``, ``button_chip_sections``, ``toolkit_switch``,
    ``color_picker_dialog``.
Tab surfaces
    ``value_slider_row``, ``recent_shelf_panel``, ``session_picker_page``,
    ``ic_scaled_icon_label``, ``rating_item`` (list row), ``export_dialog``,
    ``image_properties_dialog``, ``gallery_ai_page`` (Image Gallery → AI
    settings page).

The four surfaces added by ``plan-live-appearance-fixes-2026-10-19``:

* ``rating_item`` — live ``scale`` (the row and its +/- buttons grow with the
  interface scale). ``language`` is exempt: row text is caller-supplied and
  the row carries no translated chrome; rows are rebuilt per flyout open.
* ``export_dialog`` / ``image_properties_dialog`` / ``gallery_ai_page`` — both
  plan axes are driven through the **rebuild** mode: these surfaces are
  constructed per open (modal dialogs) or per settings-dialog construction
  (the AI page), so the truthful assertion is "a fresh instance built under
  the new metrics carries the new geometry/labels". A live per-instance
  subscription does not exist for them, and asserting one would test a
  lifecycle the app does not have.

Pixel gate (the LIVE false green this file also closes)
-------------------------------------------------------
Geometry parity is not appearance: nine geometry tests passed while the
owner's chrome was visibly broken (``plan-live-appearance-fixes-2026-10-19``
§47-50). ``PIXEL_SURFACES`` therefore rasterises the real widget offscreen and
asserts on the ink (``tests/helpers/ui_metrics_parity.py`` pixel mode):

* ``test_ink_rows_scale_with_the_interface_scale`` — the label's ink-row
  height grows by ~the scale factor (2x here), so a baked/fixed pixel font is
  named ``UNSCALED`` and a factor² height ``DOUBLE-SCALED``; the ink bounding
  box must also stay strictly inside its row box (``CLIPPED`` otherwise);
* ``test_glyph_bitmap_differs_across_language`` — a known label's rendered
  glyph bitmap has a non-zero en/ru pixel diff (a swapped label is named
  ``IDENTICAL glyph bitmap``; a held pixmap is not content).

Registered pixel surfaces (the ones the blind-test inventory
``audit-blind-test-inventory-2026-10-20`` found missing from the pixel half):

    ``tab_strip`` (live scale), ``export_dialog``, ``image_properties_dialog``,
    ``settings_dialog`` — the three dialogs are per-open, so both axes rebuild
    a fresh instance under the lever.

``tab_strip``'s language axis is exempt: the tab title is host-supplied and
localised by ``ui/main_window/ui.py`` before ``setTabText``; the strip owns no
translated chrome, so the dialogs carry the translated-glyph check.

Known gaps recorded here (production-side, outside this gate's scope; none is
left as a silent skip):

* ``image_properties_dialog``: the dialog's root chrome (margins/spacing)
  re-derives on the scale axis, but its content-driven size constants
  (``IMAGE_PROPERTIES_MIN_WIDTH``/``_HEIGHT`` in
  ``plugins/image_properties/layout_geometry.py``) are plain ints and do not
  follow the scale. The probe asserts the owned chrome; the unscaled size
  constants remain open debt.
* ``gallery_ai_page``: the page's labels and its fixed 150px label column are
  resolved from the build language/scale; ``SettingsDialog.update_language``
  retranslates built-in chrome + the keyboard page but does not rebuild
  tab-owned settings sections. The language axis therefore asserts the
  rebuild path (the app opens settings with the current language), not a live
  retranslation the product does not implement.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import QPoint, QRect
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QWidget

from tests.helpers.ui_metrics_parity import (
    REBUILD,
    MetricsSurface,
    PixelProbe,
    PixelSurface,
    assert_glyph_bitmap_differs_across_language,
    assert_ink_fits_its_row,
    assert_ink_rows_scale_with_interface_scale,
    assert_reflows_on_metrics_change,
    capture_ink,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]

#: Language is a build-time input for these surfaces: their copy is resolved
#: when the host constructs/rebuilds them, not through a live child binding.
_LANG_BUILD_TIME_CHROME = (
    "copy is resolved from the active language when the host builds/rebuilds "
    "the surface (dialog open, CSD menu rebuild); the probe owns geometry, so "
    "the live language entry alone cannot move it"
)

#: Geometry-only probes: the offscreen builder supplies literal labels; live
#: widget retranslation is covered by the i18n suites, not this metrics probe.
_LANG_GEOMETRY_ONLY = (
    "geometry-only probe (literal labels in the builder); the widget's live "
    "retranslation is covered by the i18n suites, so emit_language_changed "
    "cannot move its sizeHint"
)


def _tr(key: str, default: str = "", *args, **kwargs) -> str:
    return default or key


@pytest.fixture(scope="module", autouse=True)
def _register_i18n_roots():
    """Make the plugin/tab language packs resolvable for the rebuild axes.

    ``resources/i18n`` is registered by ``resources.translations`` at import;
    the per-plugin/tab packs are normally added by discovery, which a narrow
    offscreen builder does not run.
    """
    from resources.translations import add_i18n_root

    for relative in (
        "src/plugins/export/resources/i18n",
        "src/plugins/image_properties/resources/i18n",
        "src/tabs/image_gallery/resources/i18n",
    ):
        path = _REPO_ROOT / relative
        if path.is_dir():
            add_i18n_root(path)


def _isolate_remembered_geometry(monkeypatch) -> None:
    """Drop remembered dialog sizes so the probe measures computed geometry.

    ``apply_dialog_geometry`` restores a remembered size from QSettings; a
    developer machine with the app's real settings would otherwise pin the
    dialog to an old size and hide the metrics change.
    """
    monkeypatch.setattr(
        "shared_toolkit.ui.layout_sizing._load_remembered_size",
        lambda _key: None,
    )


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


def _build_toolkit_switch(qapp, monkeypatch):
    """Toolkit Switch (the owner's "Рисовать фон" control): design-px geometry.

    Registered as a RATIO surface — the switch's chrome is design px resolved
    through scaled_px(), so its size hint must grow by the scale factor.
    """
    from sli_ui_toolkit.widgets import Switch

    switch = Switch()

    def probe():
        hint = switch.sizeHint()
        return (hint.width(), hint.height())

    return switch, probe


def _build_color_picker_dialog(qapp, monkeypatch):
    """Colour-picker dialog: the declared minimum must COVER the content and scale.

    Registered as a RATIO surface. Origin: the owner's screenshot (fields and
    buttons overlapping) which the L5 wave traced to a declared minimum below
    the laid-out content; the fix locks the minimum to the computed content and
    re-derives it on the metrics bus, so both must grow by the factor here.
    """
    from PySide6.QtGui import QColor

    from ui.widgets.color.picker_dialog import ColorPickerDialog

    dialog = ColorPickerDialog(QColor(255, 136, 0, 170), show_alpha=True)

    def probe():
        hint = dialog.minimumSizeHint()
        return (hint.width(), hint.height(), dialog.minimumWidth(), dialog.minimumHeight())

    return dialog, probe


def _build_rating_item(qapp, monkeypatch):
    """RatingListItem: row height + +/- button boxes are live scale-derived.

    The list row is rebuilt per flyout open (production comment on
    ``_row_layout``), but it is alive while the flyout is open, and its
    ``Button`` parts re-apply their design size on a live ``UiScale`` change.
    The probe pins exactly that owned geometry: the row height and the two
    gesture buttons. Row margins/label width are build-time ``scaled_px`` and
    are refreshed by the per-open rebuild, not by a live subscription.
    """
    from ui.widgets.rating_item import RatingListItem

    row = RatingListItem(
        index=0,
        text="A fairly long image name.png",
        full_path="/tmp/a.png",
        rating=3,
        get_rating=lambda: 3,
        increment_rating=lambda *_: None,
        decrement_rating=lambda *_: None,
        list_num=1,
    )

    def probe():
        return (row.height(), row.btn_minus.width(), row.btn_plus.height())

    return row, probe


def _build_export_dialog(qapp, monkeypatch):
    """ExportDialog: content-driven geometry re-resolved at build/apply time.

    ``plugins/export/layout_geometry`` used module-level ``scaled_px`` bakes;
    it now resolves every design px at call time. The probe reads the applied
    minimum plus the preview/form floors — the values
    ``apply_export_dialog_geometry`` owns — after a rebuild under the lever.
    Height is intentionally excluded from the ratio probe: the offscreen
    screen's height clamp (`clamp_to_screen`) dominates it, while width is
    factor-proportional end to end.
    """
    _isolate_remembered_geometry(monkeypatch)
    from domain.types import Color
    from plugins.export.dialog import ExportDialog
    from plugins.export.models import ExportDialogState
    from resources.translations import get_current_language

    state = ExportDialogState(
        current_language=get_current_language() or "en",
        output_dir="/tmp",
        favorite_dir=None,
        last_format="PNG",
        quality=95,
        png_compress_level=9,
        fill_background=True,
        background_color=Color(255, 255, 255, 255),
        comment_text="",
        comment_keep_default=False,
        resolution_scale=1.0,
    )
    dialog = ExportDialog(dialog_state=state, suggested_filename="out")

    def probe():
        return (
            dialog.minimumWidth(),
            dialog.export_preview_frame.minimumWidth(),
            dialog.export_form_frame.minimumWidth(),
            dialog.output_section.dir_label.text(),
            dialog.fmt_label.text(),
            getattr(dialog.btn_ok, "_text", ""),
        )

    return dialog, probe


def _build_image_properties_dialog(qapp, monkeypatch):
    """ImagePropertiesDialog: root chrome re-resolved at build (design px).

    The dialog's own migrated geometry is its root margins/spacing
    (``_connect_design_metrics``). The content-driven size constants are
    plain ints (see the module docstring's known-gap note), so this probe
    asserts the chrome the dialog owns rather than pretending the constants
    follow the scale.
    """
    _isolate_remembered_geometry(monkeypatch)
    monkeypatch.setattr(
        "shared_toolkit.ui.decorate_dialog.decorate_dialog", lambda *a, **k: None
    )
    from plugins.image_properties.dialog import ImagePropertiesDialog
    from plugins.image_properties.service import (
        ImageProperties,
        ImagePropertyRow,
        ImagePropertySection,
    )
    from resources.translations import get_current_language

    properties = ImageProperties(
        title="Properties",
        sections=(
            ImagePropertySection(
                "section",
                "Section",
                (
                    ImagePropertyRow("name", "Name", "image.png"),
                    ImagePropertyRow("size", "Size", "1920 x 1080 px"),
                ),
            ),
        ),
    )
    dialog = ImagePropertiesDialog(
        properties, current_language=get_current_language() or "en"
    )

    def probe():
        layout = dialog.layout()
        assert layout is not None
        margins = layout.contentsMargins()
        return (
            margins.left(),
            margins.top(),
            margins.right(),
            margins.bottom(),
            layout.spacing(),
            getattr(dialog.copy_all_button, "_text", ""),
            getattr(dialog.close_button, "_text", ""),
        )

    return dialog, probe


def _build_gallery_ai_page(qapp, monkeypatch):
    """Image Gallery → AI settings page: group metrics + translated labels.

    The page is built once per ``SettingsDialog`` construction from the
    dialog's language. The probe reads the group's own toolkit metrics
    (bottom inset, row spacing) plus the line-edit/combo heights and the
    labels — the title-clearance top inset is deliberately excluded because
    it is font-height-derived, not factor-proportional.
    """
    from core.store import Store
    from plugins.settings.dialog import SettingsDialog
    from resources.translations import get_current_language
    from sli_ui_toolkit.managers import UiScale
    from sli_ui_toolkit.widgets import CustomGroupWidget

    store = Store()
    dialog = SettingsDialog(
        current_language=get_current_language() or "en",
        current_theme=store.settings.theme,
        current_max_length=30,
        min_limit=1,
        max_limit=200,
        debug_mode_enabled=False,
        system_notifications_enabled=True,
        current_ui_scale_factor=UiScale.get_instance().factor(),
        active_tab="image_gallery",
    )
    page = dialog.page_gallery_ai
    group = page.findChild(CustomGroupWidget)
    assert group is not None, "AI settings group missing"

    def probe():
        layout = group.layout()
        assert layout is not None
        margins = layout.contentsMargins()
        return (
            margins.bottom(),
            layout.spacing(),
            dialog.gallery_ai_base_url.height(),
            dialog.gallery_ai_effort.height(),
            dialog.gallery_ai_enabled.text(),
            dialog.gallery_ai_base_url_label.text(),
            dialog.gallery_ai_model_label.text(),
        )

    return dialog, probe


# ---------------------------------------------------------------------------
# Registry — the ONE entry point. Every surface must make an explicit decision
# on each plan axis (asserted or exempted with a reason); see
# ``MetricsSurface.__post_init__``.
# ---------------------------------------------------------------------------

SURFACES: dict[str, MetricsSurface] = {}


def register_surface(surface: MetricsSurface) -> MetricsSurface:
    """Register a parity surface (the only supported entry point).

    Refuses duplicates and (through ``MetricsSurface.__post_init__``) a
    surface that leaves a plan axis unaccounted — a new dialog cannot ship
    ungated and cannot silently skip ``scale``/``language``.
    """
    if surface.name in SURFACES:
        raise ValueError(f"duplicate metrics surface {surface.name!r}")
    SURFACES[surface.name] = surface
    return surface


# Host chrome — font AND scale derived.
register_surface(
    MetricsSurface(
        "csd_menu_strip",
        _build_csd_menu_strip,
        frozenset({"font", "scale"}),
        exemptions={"language": _LANG_BUILD_TIME_CHROME},
    )
)
register_surface(
    MetricsSurface(
        "help_back_bar",
        _build_help_back_bar,
        frozenset({"font", "scale"}),
        exemptions={"language": _LANG_BUILD_TIME_CHROME},
    )
)
register_surface(
    MetricsSurface(
        "dialog_action_bar",
        _build_dialog_action_bar,
        frozenset({"scale"}),
        exemptions={"language": _LANG_GEOMETRY_ONLY},
    )
)
# Tab surfaces.
register_surface(
    MetricsSurface(
        "value_slider_row",
        _build_value_slider_row,
        frozenset({"font", "scale"}),
        exemptions={"language": _LANG_BUILD_TIME_CHROME},
    )
)
register_surface(
    MetricsSurface(
        "recent_shelf_panel",
        _build_recent_shelf_panel,
        frozenset({"scale"}),
        exemptions={"language": _LANG_GEOMETRY_ONLY},
    )
)
register_surface(
    MetricsSurface(
        "session_picker_page",
        _build_session_picker_page,
        frozenset({"scale"}),
        exemptions={"language": _LANG_GEOMETRY_ONLY},
    )
)
register_surface(
    MetricsSurface(
        "ic_scaled_icon_label",
        _build_ic_scaled_icon_label,
        frozenset({"scale"}),
        exemptions={"language": _LANG_GEOMETRY_ONLY},
    )
)
# Toolkit chrome the owner reported broken on a LIVE scale change — these
# are RATIO surfaces (all probe values are factor-proportional design px),
# so the harness also catches DOUBLE scaling, not just staleness.
register_surface(
    MetricsSurface(
        "context_menu_rows",
        _build_context_menu_rows,
        frozenset({"scale"}),
        expect_ratio=True,
        exemptions={"language": _LANG_GEOMETRY_ONLY},
    )
)
register_surface(
    MetricsSurface(
        "button_chip_sections",
        _build_button_chip,
        frozenset({"scale"}),
        expect_ratio=True,
        exemptions={"language": _LANG_GEOMETRY_ONLY},
    )
)
register_surface(
    MetricsSurface(
        "toolkit_switch",
        _build_toolkit_switch,
        frozenset({"scale"}),
        expect_ratio=True,
        exemptions={"language": _LANG_GEOMETRY_ONLY},
    )
)
register_surface(
    MetricsSurface(
        "color_picker_dialog",
        _build_color_picker_dialog,
        frozenset({"scale"}),
        expect_ratio=True,
        exemptions={"language": _LANG_GEOMETRY_ONLY},
    )
)
# plan-live-appearance-fixes-2026-10-19 additions.
register_surface(
    MetricsSurface(
        "rating_item",
        _build_rating_item,
        frozenset({"scale"}),
        expect_ratio=True,
        exemptions={
            "language": (
                "row text (filename/rating digit) is caller-supplied and the "
                "row has no translated chrome; rows are rebuilt per flyout "
                "open with the caller's current language strings"
            )
        },
    )
)
register_surface(
    MetricsSurface(
        "export_dialog",
        _build_export_dialog,
        frozenset({"scale", "language"}),
        expect_ratio=True,
        axis_modes={"scale": REBUILD, "language": REBUILD},
    )
)
register_surface(
    MetricsSurface(
        "image_properties_dialog",
        _build_image_properties_dialog,
        frozenset({"scale", "language"}),
        expect_ratio=True,
        axis_modes={"scale": REBUILD, "language": REBUILD},
    )
)
register_surface(
    MetricsSurface(
        "gallery_ai_page",
        _build_gallery_ai_page,
        frozenset({"scale", "language"}),
        expect_ratio=True,
        axis_modes={"scale": REBUILD, "language": REBUILD},
    )
)


@pytest.mark.parametrize("name", sorted(SURFACES))
def test_surface_reflows_on_metrics_change(qapp, monkeypatch, name):
    assert_reflows_on_metrics_change(SURFACES[name], qapp=qapp, monkeypatch=monkeypatch)


def test_the_plan_surfaces_are_registered():
    """The four surfaces named by plan-live-appearance-fixes-2026-10-19."""
    assert {
        "rating_item",
        "export_dialog",
        "image_properties_dialog",
        "gallery_ai_page",
    } <= set(SURFACES)


def test_a_surface_cannot_ship_without_a_language_decision():
    """An unaccounted plan axis is a registration error, not a silent skip."""
    with pytest.raises(ValueError, match="plan axis"):
        MetricsSurface(
            "synthetic_ungated",
            lambda qapp, monkeypatch: (QWidget(), lambda: (1,)),
            frozenset({"scale"}),
        )


def test_register_surface_rejects_duplicates():
    surface = MetricsSurface(
        "synthetic_duplicate",
        lambda qapp, monkeypatch: (QWidget(), lambda: (1,)),
        frozenset({"scale"}),
        exemptions={"language": "synthetic"},
    )
    register_surface(surface)
    try:
        with pytest.raises(ValueError, match="duplicate"):
            register_surface(surface)
    finally:
        SURFACES.pop(surface.name, None)


# ---------------------------------------------------------------------------
# Harness falsification — a gate nobody has seen fail is not a gate. Every
# disease must be caught, and the failure must NAME which one it is.
# ---------------------------------------------------------------------------


def _constant_surface() -> MetricsSurface:
    """A surface that never re-derives (the class bug) — must be STALE."""
    from PySide6.QtWidgets import QWidget

    def build(qapp, monkeypatch):
        widget = QWidget()

        def probe():
            return (10,)  # frozen: exactly what a baked design px looks like

        return widget, probe

    return MetricsSurface(
        "synthetic_stale",
        build,
        frozenset({"scale"}),
        expect_ratio=True,
        exemptions={"language": "synthetic"},
    )


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
        "synthetic_double",
        build,
        frozenset({"scale"}),
        expect_ratio=True,
        exemptions={"language": "synthetic"},
    )


def _rebuild_stale_surface() -> MetricsSurface:
    """A rebuild-mode surface whose build ignores the lever — still STALE."""
    from PySide6.QtWidgets import QWidget

    def build(qapp, monkeypatch):
        widget = QWidget()
        return widget, lambda: (10,)  # never reads the new factor

    return MetricsSurface(
        "synthetic_rebuild_stale",
        build,
        frozenset({"scale"}),
        expect_ratio=True,
        axis_modes={"scale": REBUILD},
        exemptions={"language": "synthetic"},
    )


def _language_stale_surface() -> MetricsSurface:
    """A surface whose copy never retranslates — the language disease."""
    from PySide6.QtWidgets import QVBoxLayout, QWidget

    def build(qapp, monkeypatch):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        label = QLabel("Fixed untranslated label")
        layout.addWidget(label)
        return widget, lambda: (label.text(),)

    return MetricsSurface(
        "synthetic_language_stale",
        build,
        frozenset({"language"}),
        exemptions={"scale": "synthetic"},
    )


def test_gate_catches_a_stale_surface(qapp):
    with pytest.raises(AssertionError) as exc:
        assert_reflows_on_metrics_change(_constant_surface(), qapp=qapp)
    assert "STALE" in str(exc.value), str(exc.value)


def test_gate_catches_a_double_scaled_surface(qapp):
    with pytest.raises(AssertionError) as exc:
        assert_reflows_on_metrics_change(_double_scaled_surface(), qapp=qapp)
    assert "DOUBLE-SCALED" in str(exc.value), str(exc.value)


def test_gate_catches_a_stale_rebuilt_surface(qapp):
    """The rebuild mode shares the ratio disease detector — no weaker pass."""
    with pytest.raises(AssertionError) as exc:
        assert_reflows_on_metrics_change(_rebuild_stale_surface(), qapp=qapp)
    assert "STALE" in str(exc.value), str(exc.value)


def test_gate_catches_a_surface_that_ignores_the_language_axis(qapp):
    with pytest.raises(AssertionError) as exc:
        assert_reflows_on_metrics_change(_language_stale_surface(), qapp=qapp)
    assert "language change" in str(exc.value), str(exc.value)


# ---------------------------------------------------------------------------
# Pixel gate — the LIVE false green this half closes. Geometry that re-derives
# is not appearance: the ink has to scale with the interface scale, stay inside
# its row, and a known label's glyph bitmap has to change across en/ru.
#
# Registered surfaces are the ones the blind-test inventory found missing from
# the pixel gate (the owner's visibly broken chrome passed nine geometry
# tests): the workspace tab strip and the export / image-properties / settings
# dialogs.
# ---------------------------------------------------------------------------

PIXEL_SURFACES: dict[str, PixelSurface] = {}


def register_pixel_surface(surface: PixelSurface) -> PixelSurface:
    """Register a pixel surface (the only supported entry point)."""
    if surface.name in PIXEL_SURFACES:
        raise ValueError(f"duplicate pixel surface {surface.name!r}")
    PIXEL_SURFACES[surface.name] = surface
    return surface


def _mapped_rect(widget: QWidget, ancestor: QWidget) -> QRect:
    """``widget``'s geometry in ``ancestor`` coordinates (grab coordinates)."""
    return QRect(widget.mapTo(ancestor, QPoint(0, 0)), widget.size())


def _label_widget_probe(widget: QWidget, dialog: QWidget, *, inner: int = 4) -> PixelProbe:
    """Probe for a toolkit label widget painted inside ``dialog``.

    ``label_region`` is the widget's inner box (border excluded) so the ink
    measured is the label content, not the frame; ``row_region`` is the whole
    widget box the content must stay inside.
    """
    return PixelProbe(
        image=lambda: dialog.grab().toImage(),
        label_region=lambda: _mapped_rect(widget, dialog).adjusted(inner, inner, -inner, -inner),
        row_region=lambda: _mapped_rect(widget, dialog),
        label_text=lambda: getattr(widget, "_text", "") or getattr(widget, "text", lambda: "")(),
    )


def _build_tab_strip_pixels(qapp, monkeypatch):
    """WorkspaceTabStrip: the tab label's glyph ink inside the tab row.

    The tab strip is long-lived chrome, so its pixel probe drives the LIVE
    path (scale lever on the built strip) — the same subscription the owner
    sees when changing the interface scale in Settings. The tab title itself
    is host-supplied, so the language axis is exempt here.
    """
    from PySide6.QtWidgets import QTabBar

    from ui.icon_manager import AppIcon
    from ui.widgets.workspace_tab_strip import WorkspaceTabStrip

    strip = WorkspaceTabStrip(add_icon=AppIcon.ADD, close_icon=AppIcon.CLOSE)
    strip.addTab("Image Compare")
    strip.addTab("Image Gallery")
    strip.resize(900, strip.sizeHint().height())
    strip.show()
    qapp.processEvents()

    def _tab_bar_offset() -> QPoint:
        return strip.tab_bar.mapTo(strip, QPoint(0, 0))

    def row_region() -> QRect:
        return strip.tabRect(0).translated(_tab_bar_offset())

    def label_region() -> QRect:
        tab = row_region()
        slot = strip.tab_bar.tabButton(0, QTabBar.ButtonPosition.RightSide)
        right = (
            slot.geometry().left() + _tab_bar_offset().x()
            if slot is not None
            else tab.right()
        )
        return QRect(
            tab.left() + 8,
            tab.top() + int(tab.height() * 0.28),
            max(1, right - tab.left() - 12),
            max(1, int(tab.height() * 0.67)),
        )

    probe = PixelProbe(
        image=lambda: strip.grab().toImage(),
        label_region=label_region,
        row_region=row_region,
        label_text=lambda: strip.tabText(0),
    )
    return strip, probe


def _build_export_dialog_pixels(qapp, monkeypatch):
    """ExportDialog: the Cancel button's glyph ink (a translated label)."""
    _isolate_remembered_geometry(monkeypatch)
    from domain.types import Color
    from plugins.export.dialog import ExportDialog
    from plugins.export.models import ExportDialogState
    from resources.translations import get_current_language

    state = ExportDialogState(
        current_language=get_current_language() or "en",
        output_dir="/tmp",
        favorite_dir=None,
        last_format="PNG",
        quality=95,
        png_compress_level=9,
        fill_background=True,
        background_color=Color(255, 255, 255, 255),
        comment_text="",
        comment_keep_default=False,
        resolution_scale=1.0,
    )
    dialog = ExportDialog(dialog_state=state, suggested_filename="out")
    dialog.show()
    qapp.processEvents()
    return dialog, _label_widget_probe(dialog.btn_cancel, dialog)


def _build_image_properties_dialog_pixels(qapp, monkeypatch):
    """ImagePropertiesDialog: the "Copy all" button's glyph ink."""
    _isolate_remembered_geometry(monkeypatch)
    monkeypatch.setattr(
        "shared_toolkit.ui.decorate_dialog.decorate_dialog", lambda *a, **k: None
    )
    from plugins.image_properties.dialog import ImagePropertiesDialog
    from plugins.image_properties.service import (
        ImageProperties,
        ImagePropertyRow,
        ImagePropertySection,
    )
    from resources.translations import get_current_language

    properties = ImageProperties(
        title="Properties",
        sections=(
            ImagePropertySection(
                "section",
                "Section",
                (ImagePropertyRow("name", "Name", "image.png"),),
            ),
        ),
    )
    dialog = ImagePropertiesDialog(
        properties, current_language=get_current_language() or "en"
    )
    dialog.show()
    qapp.processEvents()
    return dialog, _label_widget_probe(dialog.copy_all_button, dialog)


def _build_settings_dialog_pixels(qapp, monkeypatch):
    """SettingsDialog: the Cancel button's glyph ink (translated chrome)."""
    _isolate_remembered_geometry(monkeypatch)
    from core.store import Store
    from plugins.settings.dialog import SettingsDialog
    from resources.translations import get_current_language
    from sli_ui_toolkit.managers import UiScale

    store = Store()
    dialog = SettingsDialog(
        current_language=get_current_language() or "en",
        current_theme=store.settings.theme,
        current_max_length=30,
        min_limit=1,
        max_limit=200,
        debug_mode_enabled=False,
        system_notifications_enabled=True,
        current_ui_scale_factor=UiScale.get_instance().factor(),
        active_tab="image_gallery",
    )
    dialog.show()
    qapp.processEvents()
    return dialog, _label_widget_probe(dialog.cancel_button, dialog)


#: The tab strip paints a title the HOST localised (``ui/main_window/ui.py``
#: ``_localized_session_title`` → ``tab.localized_display_name``); the strip
#: owns no translated chrome, so emitting the live language entry without a
#: host rebuild cannot change its pixels. The three dialogs carry the
#: translated-glyph check.
_TAB_STRIP_LANGUAGE_EXEMPTION = (
    "tab titles are host-supplied session labels (translated by "
    "ui/main_window/ui.py before setTabText); the strip paints the string it "
    "is given and has no translated chrome of its own"
)

register_pixel_surface(
    PixelSurface(
        "tab_strip",
        _build_tab_strip_pixels,
        axes=frozenset({"scale"}),
        exemptions={"language": _TAB_STRIP_LANGUAGE_EXEMPTION},
    )
)
register_pixel_surface(
    PixelSurface(
        "export_dialog",
        _build_export_dialog_pixels,
        modes={"scale": REBUILD, "language": REBUILD},
    )
)
register_pixel_surface(
    PixelSurface(
        "image_properties_dialog",
        _build_image_properties_dialog_pixels,
        modes={"scale": REBUILD, "language": REBUILD},
    )
)
register_pixel_surface(
    PixelSurface(
        "settings_dialog",
        _build_settings_dialog_pixels,
        modes={"scale": REBUILD, "language": REBUILD},
    )
)


@pytest.fixture(scope="module", autouse=True)
def _pixel_theme(qapp):
    """Paint the pixel surfaces under the app's real light palette.

    An unthemed toolkit widget paints a flat (often black) face offscreen, so
    the ink rasteriser would see background-only. Register the app palettes and
    select light for the module, restoring the previous theme afterwards.
    """
    from core.theme import DARK_THEME_PALETTE, LIGHT_THEME_PALETTE
    from sli_ui_toolkit.theme import ThemeManager

    manager = ThemeManager.get_instance()
    original = manager.get_current_theme()
    manager.register_palettes(LIGHT_THEME_PALETTE, DARK_THEME_PALETTE)
    manager.set_theme("light", qapp, await_ripples=False)
    qapp.processEvents()
    yield
    if original:
        manager.set_theme(original, qapp, await_ripples=False)
        qapp.processEvents()


@pytest.mark.parametrize("name", sorted(PIXEL_SURFACES))
def test_ink_rows_scale_with_the_interface_scale(qapp, monkeypatch, name):
    """The label's ink-row height must grow by ~the scale factor (2x here)."""
    assert_ink_rows_scale_with_interface_scale(
        PIXEL_SURFACES[name], qapp=qapp, monkeypatch=monkeypatch, factor=2.0
    )


@pytest.mark.parametrize(
    "name", sorted(n for n, s in PIXEL_SURFACES.items() if "language" in s.axes)
)
def test_glyph_bitmap_differs_across_language(qapp, monkeypatch, name):
    """A known label's glyph bitmap must have a non-zero en/ru pixel diff."""
    assert_glyph_bitmap_differs_across_language(
        PIXEL_SURFACES[name], qapp=qapp, monkeypatch=monkeypatch
    )


def test_the_pixel_gate_registers_the_plan_surfaces():
    """The surfaces the blind-test inventory found missing from the pixel gate."""
    assert {
        "tab_strip",
        "export_dialog",
        "image_properties_dialog",
        "settings_dialog",
    } <= set(PIXEL_SURFACES)


def test_a_pixel_surface_cannot_ship_without_a_language_decision():
    with pytest.raises(ValueError, match="plan axis"):
        PixelSurface(
            "synthetic_pixel_ungated",
            lambda qapp, monkeypatch: (QWidget(), _label_widget_probe(QWidget(), QWidget())),
            axes=frozenset({"scale"}),
        )


# ---------------------------------------------------------------------------
# Pixel-gate falsification — the LIVE false green must be caught by name:
# a fixed-px row (UNSCALED), a squeezed label (CLIPPED) and a label whose text
# changed while its bitmap did not (IDENTICAL glyph bitmap).
# ---------------------------------------------------------------------------


def _fixed_label_surface(
    *,
    text: str = "Ink row",
    pixel_size: int = 12,
    size: tuple[int, int] = (180, 34),
    centered: bool = False,
    reported_text=None,
) -> PixelSurface:
    """A label with a fixed pixel font/size — the baked-design-px disease."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QFont
    from PySide6.QtWidgets import QLabel

    def build(qapp, monkeypatch):
        label = QLabel(text)
        font = QFont(label.font())
        font.setPixelSize(pixel_size)
        label.setFont(font)
        if centered:
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setFixedSize(*size)
        label.show()
        qapp.processEvents()
        probe = PixelProbe(
            image=lambda: label.grab().toImage(),
            label_region=lambda: label.rect(),
            row_region=lambda: label.rect(),
            label_text=lambda: reported_text() if reported_text else label.text(),
        )
        return label, probe

    return PixelSurface(
        "synthetic_pixel",
        build,
        axes=frozenset({"scale", "language"}),
    )


def test_pixel_gate_catches_an_unscaled_row(qapp):
    surface = _fixed_label_surface(centered=True)
    with pytest.raises(AssertionError) as exc:
        assert_ink_rows_scale_with_interface_scale(surface, qapp=qapp, factor=2.0)
    assert "UNSCALED" in str(exc.value), str(exc.value)


def test_pixel_gate_catches_a_clipped_label(qapp):
    surface = _fixed_label_surface(text="A label wider than its row", size=(40, 22))
    with pytest.raises(AssertionError) as exc:
        assert_ink_fits_its_row(capture_ink(surface, qapp=qapp))
    assert "CLIPPED" in str(exc.value), str(exc.value)


def test_pixel_gate_catches_an_identical_glyph_bitmap(qapp):
    """The swapped-label disease: the text claims ru, the bitmap never moved."""
    from resources.translations import get_current_language

    surface = _fixed_label_surface(
        text="Frozen",
        reported_text=lambda: "Frozen" if (get_current_language() or "en") == "en" else "Заморожено",
    )
    with pytest.raises(AssertionError) as exc:
        assert_glyph_bitmap_differs_across_language(surface, qapp=qapp)
    assert "IDENTICAL glyph bitmap" in str(exc.value), str(exc.value)

