"""Dialog geometry bridges must resolve design px per call, not at import.

The settings / help / image-properties ``layout_geometry`` modules authored
their size recipe and their ``GeometryApplyPolicy`` floor/bounds in design px
and consumed them **raw**. At interface scale 1.25/1.5 the dialogs' own rows
scale (they go through ``scaled_px``) while the window bracket stayed at design
px, so the shell no longer covered its content — the settings / help /
image-properties rows clipped or crushed (inventory rank 1-3,
``inv-px-scaling-inventory-2026-10-19``; plan
``plan-live-appearance-fixes-2026-10-19``). The fix is the working sibling
pattern of ``plugins/export/layout_geometry.py``: named design-space constants
resolved with ``scaled_px`` inside the builder that consumes them.

Falsification story: every ``_SCALE`` assertion below is RED against the
pre-fix modules — ``UiScale.set_factor(1.25)`` left ``minimum_floor`` at
``(300, 200)`` / ``(720, 480)`` / ``(480, 360)``, ``width_bounds`` at
``(800, 1200)`` / ``(720, 1200)`` / ``(480, 960)`` and the applied dialog
minimums at the same design numbers, so a raw constant "stays put" while the
expected value below is ``design * 1.25``. They pass only once the policy is
built per call from the live factor.

The dialogs are the real production classes (built offscreen, as the existing
plugins tests do) so the assertion covers the actual ``apply_*_dialog_geometry``
bridge into ``QWidget.setMinimumSize``, not just the resolver in isolation.
"""

from __future__ import annotations

import pytest

from sli_ui_toolkit.managers import UiScale, scaled_px

_SCALE = 1.25


def _set_factor(factor: float) -> None:
    """Move the process-wide UI scale factor.

    The geometry modules resolve design px by reading ``UiScale.factor()``
    synchronously inside their builders; no coalesced metrics-bus turn is
    involved, and every dialog below is CONSTRUCTED after this call, so there
    is no earlier live widget state waiting for a flush.
    """
    UiScale.get_instance().set_factor(factor)


@pytest.fixture(autouse=True)
def _restore_ui_scale():
    """``UiScale`` is a process-wide singleton — never leak a factor."""
    yield
    UiScale.get_instance().set_factor(1.0)


@pytest.fixture(autouse=True)
def _no_remembered_sizes(monkeypatch):
    """Measure computed geometry: a remembered size would mask the floor."""
    monkeypatch.setattr(
        "shared_toolkit.ui.layout_sizing._load_remembered_size",
        lambda _key: None,
    )


def _build_settings_dialog(factor: float):
    from core.store import Store
    from plugins.settings.dialog import SettingsDialog
    from plugins.settings.layout_geometry import apply_settings_dialog_geometry

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
    # The constructor applies geometry synchronously; re-apply so the measured
    # minimum is unambiguously the policy's (not a layout-default side effect).
    apply_settings_dialog_geometry(dialog)
    return dialog


def _build_help_dialog():
    from plugins.help.dialog import HelpDialog
    from plugins.help.layout_geometry import apply_help_dialog_geometry

    dialog = HelpDialog(current_language="en", app_name="Improve-ImgSLI")
    # Help defers its first geometry pass; apply explicitly to measure the
    # bridge now instead of after an event-loop turn.
    apply_help_dialog_geometry(dialog)
    return dialog


def _build_image_properties_dialog():
    from plugins.image_properties.dialog import ImagePropertiesDialog
    from plugins.image_properties.layout_geometry import (
        apply_image_properties_dialog_geometry,
    )
    from plugins.image_properties.service import (
        ImageProperties,
        ImagePropertyRow,
        ImagePropertySection,
    )

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
    dialog = ImagePropertiesDialog(properties, current_language="en")
    apply_image_properties_dialog_geometry(dialog)
    return dialog


# ---------------------------------------------------------------------------
# Settings — floor (300, 200), bounds (800, 1200) at factor 1.0.
# ---------------------------------------------------------------------------


def test_settings_dialog_geometry_brackets_its_scaled_content(qapp):
    from plugins.settings.layout_geometry import settings_geometry_policy

    baseline = _build_settings_dialog(1.0)
    try:
        policy = settings_geometry_policy()
        assert policy.minimum_floor == (300, 200)
        assert policy.width_bounds == (800, 1200)
        assert baseline.minimumWidth() == 300
        assert baseline.minimumHeight() == 200
    finally:
        baseline.deleteLater()

    _set_factor(_SCALE)
    scaled = _build_settings_dialog(_SCALE)
    try:
        policy = settings_geometry_policy()
        assert policy.minimum_floor == (scaled_px(300), scaled_px(200)), (
            "settings minimum floor stayed at design px after set_factor(1.25) "
            f"— got {policy.minimum_floor}, expected "
            f"{(scaled_px(300), scaled_px(200))}"
        )
        assert policy.width_bounds == (scaled_px(800), scaled_px(1200)), (
            f"settings width bounds stayed at design px — got "
            f"{policy.width_bounds}, expected "
            f"{(scaled_px(800), scaled_px(1200))}"
        )
        assert scaled.minimumWidth() == scaled_px(300)
        assert scaled.minimumHeight() == scaled_px(200)
    finally:
        scaled.deleteLater()


# ---------------------------------------------------------------------------
# Help — floor/bounds (720, 480) / (720, 1200) at factor 1.0.
# ---------------------------------------------------------------------------


def test_help_dialog_geometry_brackets_its_scaled_content(qapp):
    from plugins.help.layout_geometry import help_geometry_policy

    baseline = _build_help_dialog()
    try:
        policy = help_geometry_policy()
        assert policy.minimum_floor == (720, 480)
        assert policy.width_bounds == (720, 1200)
        assert baseline.minimumWidth() == 720
        assert baseline.minimumHeight() == 480
    finally:
        baseline.deleteLater()

    _set_factor(_SCALE)
    scaled = _build_help_dialog()
    try:
        policy = help_geometry_policy()
        assert policy.minimum_floor == (scaled_px(720), scaled_px(480)), (
            "help minimum floor stayed at design px after set_factor(1.25) — "
            f"got {policy.minimum_floor}, expected "
            f"{(scaled_px(720), scaled_px(480))}"
        )
        assert policy.width_bounds == (scaled_px(720), scaled_px(1200)), (
            f"help width bounds stayed at design px — got "
            f"{policy.width_bounds}, expected "
            f"{(scaled_px(720), scaled_px(1200))}"
        )
        assert scaled.minimumWidth() == scaled_px(720)
        assert scaled.minimumHeight() == scaled_px(480)
    finally:
        scaled.deleteLater()


# ---------------------------------------------------------------------------
# Image properties — floor/bounds (480, 360) / (480, 960) at factor 1.0.
# ---------------------------------------------------------------------------


def test_image_properties_dialog_geometry_brackets_its_scaled_content(qapp):
    from plugins.image_properties.layout_geometry import (
        image_properties_geometry_policy,
    )

    baseline = _build_image_properties_dialog()
    try:
        policy = image_properties_geometry_policy()
        assert policy.minimum_floor == (480, 360)
        assert policy.width_bounds == (480, 960)
        assert baseline.minimumWidth() == 480
        assert baseline.minimumHeight() == 360
    finally:
        baseline.deleteLater()

    _set_factor(_SCALE)
    scaled = _build_image_properties_dialog()
    try:
        policy = image_properties_geometry_policy()
        assert policy.minimum_floor == (scaled_px(480), scaled_px(360)), (
            "image properties minimum floor stayed at design px after "
            f"set_factor(1.25) — got {policy.minimum_floor}, expected "
            f"{(scaled_px(480), scaled_px(360))}"
        )
        assert policy.width_bounds == (scaled_px(480), scaled_px(960)), (
            f"image properties width bounds stayed at design px — got "
            f"{policy.width_bounds}, expected "
            f"{(scaled_px(480), scaled_px(960))}"
        )
        assert scaled.minimumWidth() == scaled_px(480)
        assert scaled.minimumHeight() == scaled_px(360)
    finally:
        scaled.deleteLater()
