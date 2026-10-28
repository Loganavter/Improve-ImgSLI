"""Primitive widget factory for the image_compare tab."""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QSizePolicy, QWidget
from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.widgets import (
    Button,
    CustomLineEdit,
    DEFER_CLICK_AWAIT_RIPPLE,
    InstancesCounterButton,
    ScrollableComboBox,
    Text,
)
from ui.widgets.scroll_value_button import ScrollValueButton
from ui.widgets.slider_hint import ValueSlider

from sli_ui_toolkit.i18n import tr
from tabs.image_compare.canvas.widget import CanvasWidget
from tabs.image_compare.ui.magnifier_color_controls import ColorSettingsButton
from tabs.image_compare.icons import Icon
from tabs.host_helpers import ModePicker
from ui.theming import resolve_theme_color
from core.log_names import APP_LOGGER_NAME
from core.startup_trace import startup_mark

logger = logging.getLogger(APP_LOGGER_NAME)

# InfoHUD's own labels (resolution_label1/2, file_name_label1/2) get a
# larger size than the "group-title" variant's shared default (13px) --
# other "group-title" labels (magnifier/capture-size settings rows etc.)
# are NOT touched, since that variant is a shared toolkit preset used well
# beyond the HUD.
_INFO_HUD_LABEL_PIXEL_SIZE = 16


# -- mode variants: built on first use ---------------------------------------
# Six controls exist only in the ``beginner``/``expert``/``advanced`` toolbar
# layouts, and no layout mode is applied while the page is being built — the
# first ``ImageCompareLayoutManager.apply_mode`` comes later (layout-mode
# change, settings apply, onboarding) or not at all. Building them in
# ``build()`` therefore spent ~8 ms of the ~30 ms ``tab.page.primitives`` slice
# (offscreen, warm: six ``Button.__init__``) on widgets that the mode path hid
# on its first pass. They are built on first attribute access instead.
#
# Consumers are unchanged: the getters are properties installed once on the
# target's class, so ``ui.btn_orientation_simple`` and ``hasattr(ui, ...)``
# probes on it keep working with no call-site edit. Before the page is built a
# getter raises ``AttributeError`` — the same answer the never-assigned
# attribute gave, so a pre-build probe cannot create an orphan widget.
#
# One variant still cannot stay lazy past ``assemble()``:
# ``btn_magnifier_color_settings_beginner`` is materialised by
# ``MagnifierSettingsHoverController._wire`` (it links that button's
# color-options flyout while the page is assembled). Deferring it means moving
# that link to the controller's first ``_show`` — outside this file.
_MODE_VARIANT_STORE = "_ic_mode_variants"
_MODE_VARIANT_PARENT = "_ic_mode_variants_parent"


def _build_btn_orientation_simple(target: Any, parent: QWidget) -> None:
    target.btn_orientation_simple = Button(
        icon=(Icon.VERTICAL_SPLIT, Icon.HORIZONTAL_SPLIT),
        toggle=True,
        parent=parent,
    )


def _build_btn_divider_visible(target: Any, parent: QWidget) -> None:
    target.btn_divider_visible = Button(
        icon=(Icon.DIVIDER_VISIBLE, Icon.DIVIDER_HIDDEN),
        toggle=True,
        parent=parent,
    )


def _build_btn_magnifier_orientation_simple(target: Any, parent: QWidget) -> None:
    target.btn_magnifier_orientation_simple = Button(
        icon=(Icon.VERTICAL_SPLIT, Icon.HORIZONTAL_SPLIT),
        toggle=True,
        parent=parent,
    )


def _build_btn_magnifier_divider_visible(target: Any, parent: QWidget) -> None:
    target.btn_magnifier_divider_visible = Button(
        icon=(Icon.DIVIDER_VISIBLE, Icon.DIVIDER_HIDDEN),
        toggle=True,
        parent=parent,
    )


def _build_btn_magnifier_color_settings_beginner(
    target: Any, parent: QWidget
) -> None:
    target.btn_magnifier_color_settings_beginner = ColorSettingsButton(
        parent=parent, current_language="en"
    )


def _build_btn_magnifier_guides_simple(target: Any, parent: QWidget) -> None:
    target.btn_magnifier_guides_simple = Button(
        Icon.MAGNIFIER_GUIDES, toggle=True, parent=parent
    )


_MODE_VARIANT_BUILDERS = {
    "btn_orientation_simple": _build_btn_orientation_simple,
    "btn_divider_visible": _build_btn_divider_visible,
    "btn_magnifier_orientation_simple": _build_btn_magnifier_orientation_simple,
    "btn_magnifier_divider_visible": _build_btn_magnifier_divider_visible,
    "btn_magnifier_color_settings_beginner": (
        _build_btn_magnifier_color_settings_beginner
    ),
    "btn_magnifier_guides_simple": _build_btn_magnifier_guides_simple,
}


def _make_mode_variant_property(name: str) -> property:
    def _getter(self):
        store = self.__dict__.get(_MODE_VARIANT_STORE) or {}
        widget = store.get(name)
        if widget is not None:
            return widget
        parent = self.__dict__.get(_MODE_VARIANT_PARENT)
        if parent is None:
            raise AttributeError(name)
        _MODE_VARIANT_BUILDERS[name](self, parent)
        return self.__dict__[_MODE_VARIANT_STORE][name]

    def _setter(self, widget) -> None:
        self.__dict__.setdefault(_MODE_VARIANT_STORE, {})[name] = widget

    return property(_getter, _setter)


def _install_mode_variant_accessors(cls: type) -> None:
    """Install the six lazy getters on ``cls`` (once per class, idempotent).

    The factory instance is transient and the target is a plain widget, so the
    class is the only place an accessor can live that every consumer already
    goes through. Re-running is a no-op: the properties are identical, and a
    second session's widget resolves them against its own store.
    """
    if "_ic_mode_variant_accessors_installed" in vars(cls):
        return
    for name in _MODE_VARIANT_BUILDERS:
        setattr(cls, name, _make_mode_variant_property(name))
    setattr(cls, "_ic_mode_variant_accessors_installed", True)


class ImageComparePrimitivesFactory:
    """Creates image_compare's primitive widgets and attaches them to the tab widget.

    ``target`` is the tab-owned ``ImageCompareWidget`` — the widgets this
    factory builds are its attributes, not the host's. ``host`` is only used
    for the handful of host-side helpers (e.g. current language) these
    widgets need at construction time.
    """

    def __init__(self, target: Any, host: Any) -> None:
        self.target = target
        self.host = host

    def build(self, parent: QWidget) -> object:
        """Create every primitive widget the image_compare page needs.

        With ``IMGSLI_STARTUP_TRACE=1`` each construction slice closes with a
        ``tab.page.primitives.<slice>`` mark, so the cost this factory spends
        can be ranked instead of guessed (see ``ImageCompareWidget.assemble``
        for the enclosing ``tab.page.primitives`` span). Zero cost when the
        trace is off — the marks are the same ``startup_mark`` helper the
        ``tab.page.*`` chain uses.
        """
        target = self.target
        if target is None:
            raise RuntimeError("ImageComparePrimitivesFactory requires a target widget")
        if getattr(target, "_image_compare_primitives_built", False):
            return target

        # The mode variants are created on first attribute access; the parent
        # is recorded here because this factory does not outlive the build.
        # A non-widget target (test doubles) has no class to install getters
        # on, and a parentless build has nothing to parent them to, so both
        # fall back to building them now.
        if isinstance(target, QWidget) and parent is not None:
            _install_mode_variant_accessors(type(target))
            target.__dict__[_MODE_VARIANT_PARENT] = parent
        else:
            for builder in _MODE_VARIANT_BUILDERS.values():
                builder(target, parent)

        self._create_static_widgets(parent)
        startup_mark("tab.page.primitives.static_widgets")
        self._create_selection_controls(parent)
        startup_mark("tab.page.primitives.selection_controls")
        self._create_view_controls(parent)
        startup_mark("tab.page.primitives.view_controls")
        self._create_video_controls(parent)
        startup_mark("tab.page.primitives.video_controls")
        self._create_slider_controls(parent)
        startup_mark("tab.page.primitives.slider_controls")
        self._create_text_and_status_widgets(parent)
        startup_mark("tab.page.primitives.text_and_status_widgets")
        self._configure_image_label()
        self._init_warning_label()
        target._image_compare_primitives_built = True
        return target

    def _create_static_widgets(self, parent: QWidget) -> None:
        target = self.target
        target.resolution_label1 = Text(
            "--x--",
            mode="plain",
            variant="group-title",
            pixel_size=_INFO_HUD_LABEL_PIXEL_SIZE,
            alignment=Qt.AlignmentFlag.AlignCenter,
        )
        target.resolution_label2 = Text(
            "--x--",
            mode="plain",
            variant="group-title",
            pixel_size=_INFO_HUD_LABEL_PIXEL_SIZE,
            alignment=Qt.AlignmentFlag.AlignCenter,
        )
        target.magnifier_settings_panel = QWidget(parent)
        target.image_label = CanvasWidget(parent)
        target.length_warning_label = Text(parent=parent, mode="plain")

    def _create_selection_controls(self, parent: QWidget) -> None:
        target = self.target
        language = self.host._current_language()
        target.btn_image1 = Button(
            Icon.PHOTO,
            text=tr("image_compare.button.add_images_1", language),
            variant="surface",
            parent=parent,
            # Opens the native QFileDialog (modal, blocks the event loop
            # immediately) -- without this the click ripple never gets to
            # finish animating.
            defer_click=DEFER_CLICK_AWAIT_RIPPLE,
        )
        target.btn_image2 = Button(
            Icon.PHOTO,
            text=tr("image_compare.button.add_images_2", language),
            variant="surface",
            parent=parent,
            defer_click=DEFER_CLICK_AWAIT_RIPPLE,
        )
        target.btn_swap = Button(
            Icon.SYNC,
            long_press=True,
            variant="surface",
            background_color=QColor(
                resolve_theme_color(ThemeManager.get_instance(), "accent")
            ),
            parent=parent,
        )
        target.btn_clear_list1 = Button(
            Icon.DELETE,
            long_press=True,
            variant="surface",
            background_color=QColor("#D93025"),
            parent=parent,
        )
        target.btn_clear_list2 = Button(
            Icon.DELETE,
            long_press=True,
            variant="surface",
            background_color=QColor("#D93025"),
            parent=parent,
        )
        accent_color = QColor(
            resolve_theme_color(ThemeManager.get_instance(), "accent")
        )
        target.help_button = Button(
            Icon.HELP,
            variant="surface",
            background_color=accent_color,
            parent=parent,
        )
        target.btn_settings = Button(
            Icon.SETTINGS,
            variant="surface",
            background_color=accent_color,
            parent=parent,
        )
        target.btn_settings.hide()
        target.help_button.hide()
        target.btn_text_settings = Button(
            Icon.TEXT_MANIPULATOR,
            variant="surface",
            background_color=accent_color,
            parent=parent,
        )
        target.btn_quick_save = Button(
            Icon.QUICK_SAVE,
            variant="surface",
            background_color=accent_color,
            parent=parent,
            # quick_save() starts the export, so the ripple still has to
            # settle first (the button must not look pressed after the click).
            defer_click=DEFER_CLICK_AWAIT_RIPPLE,
        )
        target.btn_magnifier_orientation = ScrollValueButton(
            icon=(Icon.VERTICAL_SPLIT, Icon.HORIZONTAL_SPLIT),
            toggle=True,
            show_underline=True,
            min_value=0,
            max_value=10,
            zero_icon=Icon.DIVIDER_HIDDEN,
            parent=parent,
        )
        target.btn_save = Button(
            Icon.SAVE,
            text=tr("image_compare.button.save_result", language),
            variant="surface",
            parent=parent,
            # save_result() now opens a NON-modal ExportDialog and continues in
            # its `finished` handler, so the ripple still has to settle first
            # (the button must not look pressed after the click).
            defer_click=DEFER_CLICK_AWAIT_RIPPLE,
        )

        target.label_rating1 = Text("–", parent, mode="plain", variant="group-title", elide=False)
        target.label_rating2 = Text("–", parent, mode="plain", variant="group-title", elide=False)
        target.combo_image1 = ScrollableComboBox(parent)
        target.combo_image2 = ScrollableComboBox(parent)
        target.combo_interpolation = ScrollableComboBox(parent)
        target.combo_interpolation.setAutoWidthEnabled(True)

    def _create_view_controls(self, parent: QWidget) -> None:
        target = self.target
        target.btn_orientation = ScrollValueButton(
            icon=(Icon.VERTICAL_SPLIT, Icon.HORIZONTAL_SPLIT),
            toggle=True,
            show_underline=True,
            min_value=0,
            max_value=10,
            zero_icon=Icon.DIVIDER_HIDDEN,
            parent=parent,
        )
        target.btn_magnifier = Button(Icon.MAGNIFIER, toggle=True, parent=parent)
        target.btn_magnifier_instances = InstancesCounterButton(parent=parent)
        target.btn_freeze = Button(Icon.FREEZE, toggle=True, parent=parent)
        target.btn_file_names = Button(Icon.TEXT_FILENAME, toggle=True, parent=parent)

        target.btn_diff_mode = Button(
            Icon.HIGHLIGHT_DIFFERENCES, parent=parent
        )
        target.btn_channel_mode = Button(Icon.PHOTO, parent=parent)
        target.btn_diff_mode_picker = ModePicker.attach(
            target.btn_diff_mode, id_prefix="diff_mode"
        )
        target.btn_channel_mode_picker = ModePicker.attach(
            target.btn_channel_mode, id_prefix="channel_mode"
        )

        target.btn_magnifier_color_settings = ColorSettingsButton(
            parent=parent, current_language="en"
        )
        target.btn_magnifier_guides = ScrollValueButton(
            icon=Icon.MAGNIFIER_GUIDES,
            toggle=True,
            show_underline=True,
            min_value=0,
            max_value=10,
            zero_icon=Icon.DIVIDER_HIDDEN,
            parent=parent,
        )

        target.btn_divider_color = Button(
            Icon.DIVIDER_COLOR, show_underline=True, parent=parent
        )
        target.btn_divider_width = ScrollValueButton(
            icon=Icon.DIVIDER_WIDTH,
            min_value=0,
            max_value=10,
            zero_icon=Icon.DIVIDER_HIDDEN,
            parent=parent,
        )

        # ``btn_orientation_simple``, ``btn_divider_visible``,
        # ``btn_magnifier_orientation_simple``,
        # ``btn_magnifier_divider_visible``,
        # ``btn_magnifier_color_settings_beginner`` and
        # ``btn_magnifier_guides_simple`` are mode variants — built on first
        # access, see ``_MODE_VARIANT_BUILDERS`` above.
        target.btn_magnifier_divider_width = ScrollValueButton(
            icon=Icon.DIVIDER_WIDTH,
            show_underline=True,
            min_value=1,
            max_value=10,
            parent=parent,
        )
        target.btn_magnifier_guides_width = ScrollValueButton(
            icon=Icon.DIVIDER_WIDTH,
            show_underline=True,
            min_value=1,
            max_value=10,
            parent=parent,
        )

    def _create_video_controls(self, parent: QWidget) -> None:
        target = self.target
        target.btn_record = Button(
            icon=(Icon.RECORD, Icon.STOP), toggle=True, parent=parent
        )
        target.btn_pause = Button(
            icon=(Icon.PAUSE, Icon.PLAY), toggle=True, parent=parent
        )
        target.btn_pause.setEnabled(False)
        target.btn_video_editor = Button(
            Icon.EXPORT_VIDEO,
            # Opening the dialog is heavy (snapshot load, layout) — finish
            # the ripple first so the press feedback doesn't stutter.
            defer_click=DEFER_CLICK_AWAIT_RIPPLE,
            parent=parent,
        )

    def _create_slider_controls(self, parent: QWidget) -> None:
        target = self.target
        # ValueSlider: toolkit slider + hover value flyout above the thumb
        # (was wired externally via SliderHintController in widget.py).
        target.slider_size = ValueSlider(Qt.Orientation.Horizontal, parent)
        target.slider_capture = ValueSlider(Qt.Orientation.Horizontal, parent)
        target.slider_speed = ValueSlider(Qt.Orientation.Horizontal, parent)

    def _create_text_and_status_widgets(self, parent: QWidget) -> None:
        target = self.target
        target.edit_name1 = CustomLineEdit(parent)
        target.edit_name2 = CustomLineEdit(parent)
        # QLineEdit accepts file drags by default (mime has text/plain), which
        # steals the drag target from the main-window routing chain: the
        # window gets DragLeave, the 80ms deferred-leave timer hides the DnD
        # zone and no routed DragEnter ever restores it (regression: the DnD
        # tiles vanish whenever the caption edit row is visible). The caption
        # fields are not drop targets.
        target.edit_name1.setAcceptDrops(False)
        target.edit_name2.setAcceptDrops(False)
        target.label_magnifier_size = Text(parent=parent, mode="plain", variant="group-title")
        target.label_capture_size = Text(parent=parent, mode="plain", variant="group-title")
        target.label_movement_speed = Text(parent=parent, mode="plain", variant="group-title")
        target.label_interpolation = Text(parent=parent, mode="plain", variant="group-title")

        target.file_name_label1 = Text(
            "--", parent, mode="plain", variant="group-title",
            pixel_size=_INFO_HUD_LABEL_PIXEL_SIZE,
        )
        target.file_name_label2 = Text(
            "--", parent, mode="plain", variant="group-title",
            pixel_size=_INFO_HUD_LABEL_PIXEL_SIZE,
        )
        target.label_edit_name1 = Text(parent=parent, mode="plain", variant="group-title")
        target.label_edit_name2 = Text(parent=parent, mode="plain", variant="group-title")

    def _configure_image_label(self) -> None:
        target = self.target
        target.image_label.setMinimumSize(200, 150)
        target.image_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        target.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        target.image_label.setMouseTracking(True)
        target.image_label.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        target.image_label.setAutoFillBackground(True)

    def _init_warning_label(self) -> None:
        target = self.target
        from PySide6.QtGui import QColor

        if hasattr(target.length_warning_label, "setBold"):
            target.length_warning_label.setBold(True)
        if hasattr(target.length_warning_label, "setTextColor"):
            target.length_warning_label.setTextColor(QColor("#FF4500"))
        target.length_warning_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        target.length_warning_label.setVisible(False)