"""Raw-chrome-px drain (plan-live-appearance-fixes-2026-10-19): per-site scale.

Companion to the AST ratchet ``tests/contracts/test_no_raw_chrome_px.py``.
The ratchet says *which* sites bypass the ``scaled_px`` boundary; this file
says *what the bypass does to the live geometry*: build the real widget
offscreen at factor 1.0 and 1.5 and require the design px to resolve through
``scaled_px`` exactly once (``design * factor``), not stay at ``design``
(STALE) and not run to ``design * factor**2`` (DOUBLE).

Sites covered here (the allowlist entries outside ``src/tabs/image_compare``):
``plugins/help/back_bar``, ``plugins/image_properties/dialog``,
``plugins/settings/pages/keyboard``, ``plugins/onboarding/{overlay,pages}``,
``plugins/export/layout_geometry``,
``shared_toolkit/ui/text_input_dialog``,
``tabs/session_picker/recent/header_bar``, ``devtools/ui_inspector/app_window``
and the dead ``ui/widgets/zoom_indicator``. The gallery page root (a tab
internal) is covered from its own suite:
``src/tabs/image_gallery/tests/test_gallery_widget_root_scale.py``.

Two classes are NOT "fixed" and are pinned as intentional:

* ``QIcon.pixmap(QSize(64, 64))`` in the two gallery icon resolvers — a raster
  *resolution* request for a vector source that is later painted scaled down,
  not chrome geometry (a bigger raster can only help quality);
* ``MultiCompareWidget.setMinimumSize(400, 300)`` — a canvas image-space floor
  (UI-scale plan non-goal, same exemption class as
  ``image_compare/ui/primitives.py``).

Where a widget's own scaling pass overwrites the flagged literal (the
onboarding plugin computes ``window-fit x UiScale`` itself), the probe
neutralises that pass so the *site under test* is measured, not the pass.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QVBoxLayout, QWidget

from sli_ui_toolkit.managers import UiScale, scaled_px

_SRC = Path(__file__).resolve().parent.parent.parent / "src"


def _drain_metrics_channel() -> None:
    """Run real event-loop turns until the coalesced metrics zero-timer has fired.

    A factor change queues the ``UiMetrics.changed`` emission on a zero-timer;
    if a test ends before it fires, it lands in the NEXT test's event loop and
    re-renders unrelated surfaces (observed: a queued emission kicked a
    quick-look tiled decode in a later gallery test). Drain at teardown.
    """
    from PySide6.QtCore import QEventLoop, QTimer
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        return
    for _ in range(6):
        loop = QEventLoop()
        QTimer.singleShot(2, loop.quit)
        loop.exec()
        app.processEvents()


@pytest.fixture(autouse=True)
def _restore_ui_scale():
    """``UiScale`` is a process-wide singleton — never leak a factor."""
    yield
    UiScale.get_instance().set_factor(1.0)
    _drain_metrics_channel()


def _set(factor: float) -> None:
    UiScale.get_instance().set_factor(factor)


def _margins(layout) -> tuple[int, int, int, int, int]:
    m = layout.contentsMargins()
    return (m.left(), m.top(), m.right(), m.bottom(), layout.spacing())


def _margins_at(factor: float, build) -> tuple[int, int, int, int, int]:
    _set(factor)
    widget, layout = build()
    try:
        return _margins(layout)
    finally:
        widget.deleteLater()


def _assert_scaled_at_1_5(observed, design, *, name: str) -> None:
    """``observed`` must equal ``design`` resolved through ``scaled_px`` once."""
    expected = tuple(scaled_px(v) for v in design)
    assert observed == expected, (
        f"{name}: at factor 1.5 got {observed}, expected {expected} "
        f"(design {design} x factor). A value equal to {design} is STALE "
        f"(frozen design px); design x factor**2 = "
        f"{tuple(int(v * 2.25) for v in design)} is DOUBLE-scaled."
    )


# ---------------------------------------------------------------------------
# Dialog / page chrome: margins + spacing resolved at build time.
# ---------------------------------------------------------------------------


def test_help_back_bar_margins_and_spacing_follow_the_scale(qapp) -> None:
    from plugins.help.back_bar import HelpBackBar

    def build():
        bar = HelpBackBar()
        return bar, bar._layout

    _assert_scaled_at_1_5(
        _margins_at(1.5, build), (8, 6, 8, 7, 6), name="help_back_bar"
    )


def test_image_properties_root_margins_and_spacing_follow_the_scale(qapp) -> None:
    """``decorate_dialog`` stacks the CSD title bar onto the layout top margin,
    so neutralise it here — this probe measures the dialog's OWN root design
    px (the flagged sites), not the toolkit decoration layer."""
    import shared_toolkit.ui.decorate_dialog as decorate

    def build():
        original = decorate.decorate_dialog
        decorate.decorate_dialog = lambda *a, **k: None
        try:
            from plugins.image_properties.dialog import ImagePropertiesDialog
            from plugins.image_properties.service import (
                ImageProperties,
                ImagePropertyRow,
                ImagePropertySection,
            )

            props = ImageProperties(
                title="P",
                sections=(
                    ImagePropertySection(
                        "s", "S", (ImagePropertyRow("r", "n", "v"),)
                    ),
                ),
            )
            dialog = ImagePropertiesDialog(props, current_language="en")
        finally:
            decorate.decorate_dialog = original
        return dialog, dialog.layout()

    _assert_scaled_at_1_5(
        _margins_at(1.5, build), (12, 12, 12, 12, 10), name="image_properties"
    )


def test_text_input_dialog_root_margins_and_spacing_follow_the_scale(
    qapp,
) -> None:
    import shared_toolkit.ui.decorate_dialog as decorate

    def build():
        original = decorate.decorate_dialog
        decorate.decorate_dialog = lambda *a, **k: None
        try:
            from shared_toolkit.ui.text_input_dialog import AppTextInputDialog

            dialog = AppTextInputDialog(title="t", prompt="p")
        finally:
            decorate.decorate_dialog = original
        return dialog, dialog.layout()

    _assert_scaled_at_1_5(
        _margins_at(1.5, build), (18, 14, 18, 16, 12), name="text_input_dialog"
    )


def _build_keyboard_page(factor: float):
    from core.store import Store
    from plugins.settings.dialog import SettingsDialog
    from plugins.settings.pages.keyboard import build

    _set(factor)
    store = Store()
    dialog = SettingsDialog(
        current_language="en",
        current_theme=store.settings.theme,
        current_max_length=30,
        min_limit=1,
        max_limit=200,
        debug_mode_enabled=False,
        system_notifications_enabled=True,
        current_ui_scale_factor=factor,
        active_tab="image_compare",
    )
    build(dialog, SimpleNamespace(keyboard_overrides={}))
    return dialog


def test_settings_keyboard_page_spacings_follow_the_scale(qapp) -> None:
    """``groups_layout`` (10), the group body layout (4) and each row (8) are
    design px set once at build; none of them re-derives today, so a raw
    literal stays at design px forever."""
    dialog = _build_keyboard_page(1.5)
    try:
        content = dialog.page_keyboard.content_layout
        groups_host = content.itemAt(1).widget()
        assert groups_host.layout().spacing() == scaled_px(10), (
            f"groups spacing {groups_host.layout().spacing()} != "
            f"{scaled_px(10)} (design 10)"
        )

        group = dialog._keyboard_owner_groups[0][0]
        body = [lay for lay in group.findChildren(QVBoxLayout)]
        # The keyboard ``group_layout`` is the one with zero side insets.
        zero_side = [
            lay
            for lay in body
            if lay.contentsMargins().left() == 0
            and lay.contentsMargins().right() == 0
        ]
        assert zero_side, "keyboard group body layout not found"
        assert zero_side[0].contentsMargins().top() == scaled_px(4), (
            f"group top margin {zero_side[0].contentsMargins().top()} != "
            f"{scaled_px(4)}"
        )
        assert zero_side[0].contentsMargins().bottom() == scaled_px(4)
        assert zero_side[0].spacing() == scaled_px(4), (
            f"group spacing {zero_side[0].spacing()} != {scaled_px(4)}"
        )

        row = dialog._keyboard_filter_rows[0][0]
        assert row.layout().spacing() == scaled_px(8), (
            f"row spacing {row.layout().spacing()} != {scaled_px(8)}"
        )
    finally:
        dialog.deleteLater()


# ---------------------------------------------------------------------------
# Overlay / header chrome.
# ---------------------------------------------------------------------------


def test_session_picker_header_bar_spacing_follows_the_scale(qapp) -> None:
    from tabs.session_picker.recent.header_bar import RecentHeaderBar

    def build():
        bar = RecentHeaderBar(translate=lambda key, default="": default or key)
        return bar, bar.layout()

    observed = _margins_at(1.5, build)
    assert observed[4] == scaled_px(8), (
        f"header bar spacing {observed[4]} != {scaled_px(8)} (design 8)"
    )


def test_session_picker_header_bar_re_resolves_on_a_live_scale_change(qapp) -> None:
    from tabs.session_picker.recent.header_bar import RecentHeaderBar

    bar = RecentHeaderBar(translate=lambda key, default="": default or key)
    try:
        assert bar.layout().spacing() == 8
        _set(1.5)
        after = _spin_until_changed(qapp, lambda: bar.layout().spacing())
        assert after == scaled_px(8), (
            f"header bar spacing did not re-resolve live: {after}"
        )
    finally:
        bar.deleteLater()


def test_ui_inspector_native_row_margins_and_spacing_follow_the_scale(
    qapp,
) -> None:
    from devtools.ui_inspector.app_window import AppInspectorWindow

    class _CapturingPane:
        """Stands in for a real inspector pane; captures the page the app
        window builds so the native diagnostics row is reachable."""

        def __init__(self) -> None:
            self.page: QWidget | None = None

        def add_section(self, _name):
            page = QWidget()
            page.content_layout = QVBoxLayout(page)
            self.page = page
            return page

    _set(1.5)
    window = AppInspectorWindow()
    try:
        pane = _CapturingPane()
        window._add_native_page(pane)
        assert pane.page is not None
        row = pane.page.content_layout.itemAt(0).widget()
        assert row is not None, "native diagnostics row not built"
        observed = _margins(row.layout())
    finally:
        window.deleteLater()

    _assert_scaled_at_1_5(
        observed, (8, 4, 8, 2, 6), name="ui_inspector native row"
    )


def _build_onboarding_overlay(factor: float, *, neutralize_scale_pass: bool):
    from core.store import Store
    from plugins.onboarding import overlay as overlay_module

    class _FakeSettingsManager:
        def is_first_run(self) -> bool:
            return True

        def set_first_run_completed(self) -> None:
            pass

        def _save_setting(self, _key, _value) -> None:
            pass

        def schedule_persist(self, _store) -> None:
            pass

    _set(factor)
    original = overlay_module.OnboardingOverlay._scale_all
    if neutralize_scale_pass:
        overlay_module.OnboardingOverlay._scale_all = lambda self: None
    try:
        overlay = overlay_module.OnboardingOverlay(_FakeSettingsManager(), Store())
    finally:
        overlay_module.OnboardingOverlay._scale_all = original
    return overlay


def test_onboarding_overlay_bottom_spacing_follows_the_scale(qapp) -> None:
    """The overlay runs its own ``window-fit x UiScale`` pass, so the flagged
    ``setSpacing(8)`` is the pre-pass default. Neutralise the pass to measure
    the site itself; the live value is already re-derived by that pass."""
    overlay = _build_onboarding_overlay(1.5, neutralize_scale_pass=True)
    try:
        observed = overlay.bottom_layout.spacing()
    finally:
        overlay.deleteLater()
    assert observed == scaled_px(8), (
        f"onboarding bottom spacing {observed} != {scaled_px(8)} (design 8)"
    )


def test_onboarding_slide_spacings_follow_the_scale(qapp) -> None:
    """Same shape as the overlay: ``scale_slide`` re-derives the slide chrome;
    the raw 30/35/8 are the pre-pass defaults under test."""
    from plugins.onboarding import pages as pages_module
    from plugins.onboarding.pages import build_modes, create_slide_for_mode

    overlay = _build_onboarding_overlay(1.5, neutralize_scale_pass=True)
    original = pages_module.scale_slide
    pages_module.scale_slide = lambda *a, **k: None
    try:
        mode = build_modes(overlay.store)[0]
        page = create_slide_for_mode(overlay, mode)
        root = page._onboarding_root_layout.spacing()
        demo = page._onboarding_demo_layout.spacing()
        captions = page._onboarding_caption_layouts
        cap = captions[0].spacing() if captions else None
    finally:
        pages_module.scale_slide = original
        overlay.deleteLater()

    assert root == scaled_px(30), f"slide root spacing {root} != {scaled_px(30)}"
    assert demo == scaled_px(35), f"slide demo spacing {demo} != {scaled_px(35)}"
    assert cap == scaled_px(8), f"slide caption spacing {cap} != {scaled_px(8)}"


# ---------------------------------------------------------------------------
# Live re-derive: a value resolved at build must also follow a live change.
# ---------------------------------------------------------------------------


def _spin_until_changed(qapp, probe, *, timeout_ms: int = 1000):
    """Run real event-loop turns until ``probe()`` moves.

    The metrics bus coalesces through a zero-timer, so a plain stability drain
    (``drain_until_stable``) can legitimately read the pre-change value and
    return: wait for the *change*, not for stability.
    """
    import time

    from PySide6.QtCore import QEventLoop, QTimer

    before = probe()
    deadline = time.monotonic() + timeout_ms / 1000.0
    while time.monotonic() <= deadline:
        loop = QEventLoop()
        QTimer.singleShot(2, loop.quit)
        loop.exec()
        qapp.processEvents()
        current = probe()
        if current != before:
            return current
    return probe()


def _assert_re_resolves(qapp, build, design, *, name: str) -> None:
    """Build at 1.0, move the factor to 1.5, wait for the change, require
    ``design * factor``."""
    _set(1.0)
    widget, probe = build()
    try:
        before = _margins(probe) if hasattr(probe, "contentsMargins") else probe()
        expected_before = tuple(design)
        assert before == expected_before, (
            f"{name}: at factor 1.0 got {before}, expected {expected_before}"
        )
        _set(1.5)

        def current():
            return _margins(probe) if hasattr(probe, "contentsMargins") else probe()

        after = _spin_until_changed(qapp, current)
        expected = tuple(scaled_px(v) for v in design)
        assert after == expected, (
            f"{name}: after a live 1.5 change got {after}, expected {expected} — "
            f"the design px did not re-derive (STALE) or re-derived twice (DOUBLE)"
        )
    finally:
        widget.deleteLater()


def test_help_back_bar_re_resolves_on_a_live_scale_change(qapp) -> None:
    from plugins.help.back_bar import HelpBackBar

    def build():
        bar = HelpBackBar()
        return bar, bar._layout

    _assert_re_resolves(
        qapp, build, (8, 6, 8, 7, 6), name="help_back_bar live"
    )


def test_text_input_dialog_re_resolves_on_a_live_scale_change(qapp) -> None:
    import shared_toolkit.ui.decorate_dialog as decorate

    def build():
        original = decorate.decorate_dialog
        decorate.decorate_dialog = lambda *a, **k: None
        try:
            from shared_toolkit.ui.text_input_dialog import AppTextInputDialog

            dialog = AppTextInputDialog(title="t", prompt="p")
        finally:
            decorate.decorate_dialog = original
        return dialog, dialog.layout()

    _assert_re_resolves(
        qapp, build, (18, 14, 18, 16, 12), name="text_input_dialog live"
    )


def test_image_properties_re_resolves_on_a_live_scale_change(qapp) -> None:
    import shared_toolkit.ui.decorate_dialog as decorate

    def build():
        original = decorate.decorate_dialog
        decorate.decorate_dialog = lambda *a, **k: None
        try:
            from plugins.image_properties.dialog import ImagePropertiesDialog
            from plugins.image_properties.service import (
                ImageProperties,
                ImagePropertyRow,
                ImagePropertySection,
            )

            props = ImageProperties(
                title="P",
                sections=(
                    ImagePropertySection(
                        "s", "S", (ImagePropertyRow("r", "n", "v"),)
                    ),
                ),
            )
            dialog = ImagePropertiesDialog(props, current_language="en")
        finally:
            decorate.decorate_dialog = original
        return dialog, dialog.layout()

    _assert_re_resolves(
        qapp, build, (12, 12, 12, 12, 10), name="image_properties live"
    )


def test_settings_keyboard_page_re_resolves_on_a_live_scale_change(qapp) -> None:
    dialog = _build_keyboard_page(1.0)
    try:
        content = dialog.page_keyboard.content_layout
        groups = content.itemAt(1).widget().layout()
        row = dialog._keyboard_filter_rows[0][0].layout()
        group_body = dialog._keyboard_group_layouts[0]

        def probe():
            return (
                groups.spacing(),
                row.spacing(),
                group_body.spacing(),
                group_body.contentsMargins().top(),
            )

        assert probe() == (10, 8, 4, 4), probe()
        _set(1.5)
        after = _spin_until_changed(qapp, probe)
        assert after == (scaled_px(10), scaled_px(8), scaled_px(4), scaled_px(4)), (
            f"keyboard page did not re-resolve on a live scale change: {after}"
        )
    finally:
        dialog.deleteLater()


# ---------------------------------------------------------------------------
# Export dialog geometry: import-time bakes must become call-time resolvers.
# ---------------------------------------------------------------------------


def _export_policy(geo):
    resolver = getattr(geo, "export_geometry_policy", None)
    return resolver() if callable(resolver) else geo.EXPORT_GEOMETRY_POLICY


def test_export_dialog_geometry_resolves_at_use_time(qapp) -> None:
    """The 12 ``EXPORT_*`` constants were module-level ``scaled_px(...)``
    bakes: frozen at the factor of the module's FIRST import, so every later
    live scale change left the export dialog at the old design size while
    the rest of the UI moved. Reload at 1.0 (freeze), then read at 1.5."""
    from plugins.export import layout_geometry as geo

    _set(1.0)
    importlib.reload(geo)
    _set(1.5)

    resolver = getattr(geo, "export_min_dialog_width", None)
    min_width = resolver() if callable(resolver) else geo.EXPORT_MIN_DIALOG_WIDTH
    assert min_width == scaled_px(640), (
        f"export min dialog width at factor 1.5 is {min_width}, expected "
        f"{scaled_px(640)} — an import-time bake stays at the first import's "
        f"factor"
    )

    resolver = getattr(geo, "export_preview_min_width", None)
    preview_width = (
        resolver() if callable(resolver) else geo.EXPORT_PREVIEW_MIN_WIDTH
    )
    assert preview_width == scaled_px(500), (
        f"export preview min width at factor 1.5 is {preview_width}, expected "
        f"{scaled_px(500)}"
    )

    policy = _export_policy(geo)
    assert policy.minimum_floor == (scaled_px(640), scaled_px(520)), (
        f"export policy minimum_floor at factor 1.5 is {policy.minimum_floor}, "
        f"expected {(scaled_px(640), scaled_px(520))}"
    )
    assert policy.width_bounds == (scaled_px(640), scaled_px(1400))


# ---------------------------------------------------------------------------
# Dead legacy widget: unimportable, so it gets a static measurement.
# ---------------------------------------------------------------------------


def test_legacy_zoom_indicator_has_no_raw_chrome_px() -> None:
    """``ui/widgets/zoom_indicator.py`` imports a module that does not exist
    (``ui.widgets.rounded_overlay``) and nothing references it — the geometry
    is unreachable, so the only honest measurement is the gate's own scanner
    over its source."""
    from tests.contracts._framework import rel
    from tests.contracts.test_no_raw_chrome_px import scan_source

    path = _SRC / "ui" / "widgets" / "zoom_indicator.py"
    findings = scan_source(path.read_text(encoding="utf-8"), rel(path))
    assert findings == [], (
        "dead but still-scanned chrome geometry bypasses scaled_px:\n"
        + "\n".join(f.render() for f in findings)
    )


# ---------------------------------------------------------------------------
# Intentional exemptions — pinned so a future "fix" cannot land silently.
# ---------------------------------------------------------------------------


def test_gallery_menu_icon_raster_requests_are_not_chrome_geometry() -> None:
    """``QIcon.pixmap(QSize(64, 64))`` asks for a 64px raster of a vector
    icon that is painted scaled down; it is a resolution request, not a
    layout size and must NOT follow the UI scale (a larger raster is only
    better quality)."""
    for relative in (
        "tabs/image_gallery/ui/card/context_menu/icons.py",
        "tabs/image_gallery/ui/quick_look/overlay_build/icons.py",
    ):
        text = (_SRC / relative).read_text(encoding="utf-8")
        assert "pixmap(QSize(64, 64))" in text, relative
        assert "scaled_px(64)" not in text, (
            f"{relative}: the raster request must stay design-independent"
        )


def test_multi_compare_minimum_is_a_canvas_image_space_floor() -> None:
    """``setMinimumSize(400, 300)`` floors the canvas grid before any chrome
    (UI-scale plan non-goal, same class as
    ``image_compare/ui/primitives.py``); scaling it would exceed small
    windows at factor > 1."""
    text = (_SRC / "tabs" / "multi_compare" / "widget.py").read_text(
        encoding="utf-8"
    )
    assert "setMinimumSize(400, 300)" in text
