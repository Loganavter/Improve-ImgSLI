"""Reusable Qt layout sizing helpers for content-driven dialog geometry.

Typical usage:

1. **Primitives** — ``widget_width_hint``, ``measure_scroll_pages_stack`` after
   ``ensurePolished`` to read intrinsic content size.
2. **Per-dialog recipe** — a module-local function that combines primitives
   with shell-specific margins and clamps (see ``plugins/settings/layout_geometry``
   and ``video_editor/layout_geometry``).
3. **Apply** — ``apply_dialog_geometry`` with ``GeometryApplyPolicy`` to set
   minimum size and optionally resize hidden dialogs without disturbing visible
   ones.
4. **Lifecycle** — call the recipe after build, and ``defer_dialog_geometry`` on
   language / theme / font changes.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import QEvent, QSettings, QSize, Qt, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QLayout,
    QScrollArea,
    QStackedWidget,
    QWidget,
)

_REMEMBERED_SIZE_SETTINGS_GROUP = "dialog_geometry"


def _remembered_size_settings_key(remember_key: str) -> str:
    return f"{_REMEMBERED_SIZE_SETTINGS_GROUP}/{remember_key}/size"


def _load_remembered_size(remember_key: str) -> tuple[int, int] | None:
    raw = QSettings().value(_remembered_size_settings_key(remember_key), None)
    if not raw:
        return None
    try:
        width_str, height_str = str(raw).split("x")
        return max(1, int(width_str)), max(1, int(height_str))
    except (TypeError, ValueError):
        return None


def _save_remembered_size(remember_key: str, size: QSize) -> None:
    QSettings().setValue(
        _remembered_size_settings_key(remember_key),
        f"{size.width()}x{size.height()}",
    )


def _install_remembered_size_save_hook(dialog: QWidget, remember_key: str) -> None:
    """Save the dialog's size to ``QSettings`` once, the first time this runs.

    Idempotent per ``remember_key`` — ``apply_dialog_geometry`` re-runs on every
    theme/font change, and connecting ``finished`` again each time would save
    (and fire on close) multiple times.
    """
    installed_key = getattr(dialog, "_remembered_size_key", None)
    if installed_key == remember_key:
        return
    dialog._remembered_size_key = remember_key

    finished_signal = getattr(dialog, "finished", None)
    if finished_signal is None:
        return

    def _on_finished(*_args) -> None:
        try:
            if dialog.isMaximized() or dialog.isFullScreen():
                return
            _save_remembered_size(remember_key, dialog.size())
        except RuntimeError:
            # Underlying C++ object already torn down.
            pass

    finished_signal.connect(_on_finished)


@dataclass(frozen=True)
class HorizontalPaneMinimum:
    """Minimum horizontal space for a two-pane row (left | right)."""

    left_min: int
    spacing: int
    right_min: int
    outer_margins: int = 0

    def total_width(self) -> int:
        return self.outer_margins + self.left_min + self.spacing + self.right_min


@dataclass(frozen=True)
class GeometryApplyPolicy:
    """Controls how computed geometry is applied to a dialog."""

    resize_when_hidden: bool = True
    update_minimum: bool = True
    minimum_floor: tuple[int, int] = (300, 200)
    width_bounds: tuple[int, int] | None = None
    center_on_parent: bool = True
    # When True, ``setMinimumSize`` uses the computed size (clamped to floor)
    # so the user cannot shrink below content. Use for non-scroll dialogs
    # (export). Scrollable shells (settings) keep this False.
    lock_minimum_to_computed: bool = False
    # When True, always ``resize`` to the computed size even if the dialog is
    # already visible. Needed when CSD ``adjustSize`` overgrew the shell from
    # a pixmap sizeHint and a later geometry pass would otherwise only raise
    # the minimum without shrinking back.
    force_resize: bool = False
    # When set, the dialog's size (not position — it always centers on its
    # parent, see ``center_on_parent``) is persisted to QSettings under this
    # key on close and restored (clamped to the computed minimum) on next
    # open, instead of always reverting to the freshly computed content size.
    # Leave unset for dialogs that must not remember a size — e.g. fixed-size
    # alerts (``AppMessageDialog``).
    remember_key: str | None = None


def clamp(value: int, *, minimum: int, maximum: int) -> int:
    return max(minimum, min(value, maximum))


def estimate_prelayout_width(
    widget: QWidget,
    *,
    horizontal_chrome: int = 0,
    floor: int = 0,
) -> int:
    """Best-guess content width for ``widget`` before its first layout pass.

    Some widgets need a real width estimate *before* they have ever been
    shown — e.g. to pick a grid column count synchronously at construction
    time, so the first paint doesn't need a second pass once the real size
    is known. At that point ``widget.width()`` is **not** 0 — Qt reports its
    classic constructor placeholder (100) — so a plain ``width() > 0`` check
    cannot tell "never laid out" apart from "genuinely 100px wide". The
    reliable signal is ``Qt.WidgetAttribute.WA_Resized``: Qt sets it the
    moment a widget is given a real size, either explicitly
    (``resize()``/``setGeometry()``) or by an activated layout — never for
    the untouched constructor default. Confirmed empirically: a freshly
    parented, not-yet-shown widget reports ``width()==100`` with
    ``WA_Resized`` unset; after the ancestor chain is shown and laid out,
    ``WA_Resized`` flips and ``width()`` reflects the true size.

    If the app already restores the main window's geometry before building
    workspace content (the common startup order — see
    ``ui/main_window/lifecycle.py``'s ``LoadWindowStateStep`` running before
    ``BootstrapContentStep``), the top-level window already has
    ``WA_Resized`` set and a real width at this point even though ``widget``
    itself has never been laid out (``setGeometry()`` applies immediately,
    regardless of visibility). ``widget.window().width()`` is then a much
    better estimate than any static floor — pass ``horizontal_chrome`` for
    whatever fixed width sits between the window and ``widget`` (sidebars,
    permanent margins; 0 when the widget's ancestor chain has no such
    chrome).

    One more wrinkle, confirmed from a real run: when the window is
    restored **maximized**, ``GeometryManager`` first ``setGeometry()``s it
    to the persisted *normal* (un-maximized) size — which sets
    ``WA_Resized`` and a real but not-final width — and only then requests
    ``setWindowState(Maximized)``. The platform applies that maximize
    asynchronously (a window-manager round trip), and can even deliver it in
    more than one step (the restore-size geometry briefly for real, *then*
    the final maximized geometry) — so both ``widget.width()`` and
    ``widget.window().width()`` can report a real, ``WA_Resized``-flagged,
    but still not-final size for one or more frames. ``isMaximized()`` /
    ``isFullScreen()`` do not have this staggered-delivery problem — Qt
    flips them synchronously on ``setWindowState()``, before the platform
    geometry catches up — so that check runs *first* and unconditionally
    wins over any width already recorded on the widget or window: while the
    window is (going to be) maximized/fullscreen, the screen's available
    width is always the right answer, no matter which transitional frame
    this call happens to land on.

    Falls back to ``floor`` when nothing here has a usable size yet (e.g. in
    tests that construct the widget without a real top-level window and
    never call ``resize()``/``show()``).
    """
    window = widget.window()
    if window is not None and (window.isMaximized() or window.isFullScreen()):
        screen = window.screen() if hasattr(window, "screen") else None
        if screen is None:
            screen = QApplication.primaryScreen()
        if screen is not None:
            screen_width = int(screen.availableGeometry().width())
            estimated = screen_width - int(horizontal_chrome)
            if estimated > 0:
                return estimated
    if widget.testAttribute(Qt.WidgetAttribute.WA_Resized):
        width = int(widget.width())
        if width > 0:
            return width
    if window is not None and window.testAttribute(Qt.WidgetAttribute.WA_Resized):
        estimated = int(window.width()) - int(horizontal_chrome)
        if estimated > 0:
            return estimated
    return max(0, int(floor))


def widget_width_hint(widget: QWidget | None, *, default: int = 0) -> int:
    if widget is None:
        return default
    widget.ensurePolished()
    widget.adjustSize()
    return max(default, widget.sizeHint().width())


def widget_height_hint(widget: QWidget | None, *, default: int = 0) -> int:
    if widget is None:
        return default
    widget.ensurePolished()
    widget.adjustSize()
    return max(default, widget.sizeHint().height())


def max_widget_width_hint(
    widgets: Iterable[QWidget | None],
    *,
    default: int = 0,
) -> int:
    width = default
    for widget in widgets:
        width = max(width, widget_width_hint(widget))
    return width


def max_widget_height_hint(
    widgets: Iterable[QWidget | None],
    *,
    default: int = 0,
) -> int:
    height = default
    for widget in widgets:
        height = max(height, widget_height_hint(widget))
    return height


def tab_widget_intrinsic_width(
    tabs: QWidget | None,
    *,
    page_padding: int = 0,
    default: int = 0,
) -> int:
    """Intrinsic width for ``QTabWidget`` or duck-typed hosts (``TopTabHost``).

    Intentionally does **not** call ``adjustSize()`` on live pages — that shrinks
    them to ``sizeHint`` and fights parent layouts (fields stay narrow inside a
    wider pane).
    """
    if tabs is None:
        return default

    tabs.ensurePolished()
    width = 0
    tab_bar = tabs.tabBar() if hasattr(tabs, "tabBar") else None
    if tab_bar is not None:
        tab_bar.ensurePolished()
        width = max(width, tab_bar.sizeHint().width())

    count = int(tabs.count()) if hasattr(tabs, "count") else 0
    for index in range(count):
        page = tabs.widget(index) if hasattr(tabs, "widget") else None
        if page is None:
            continue
        page.ensurePolished()
        width = max(width, page.sizeHint().width() + page_padding)
        scroll_area = page.findChild(QScrollArea)
        if scroll_area is not None:
            content = scroll_area.widget()
            if content is not None:
                content.ensurePolished()
                width = max(width, content.sizeHint().width() + page_padding)
    return max(default, width)


def measure_scroll_pages_stack(
    pages_stack: QStackedWidget | None,
    *,
    group_widget_cls: type | None = None,
) -> tuple[int, int]:
    """Return max (width, height) across scrollable pages in a stacked widget."""
    if pages_stack is None:
        return (0, 0)

    max_content_width = 0
    max_content_height = 0
    for index in range(pages_stack.count()):
        page_wrapper = pages_stack.widget(index)
        if page_wrapper is None:
            continue
        scroll_area = page_wrapper.findChild(QScrollArea)
        if scroll_area is None:
            continue
        content_widget = scroll_area.widget()
        if content_widget is None:
            continue
        content_widget.ensurePolished()
        content_widget.adjustSize()

        if group_widget_cls is not None:
            groups = content_widget.findChildren(group_widget_cls)
            if groups:
                for group in groups:
                    max_content_width = max(
                        max_content_width, widget_width_hint(group)
                    )
            else:
                max_content_width = max(
                    max_content_width, widget_width_hint(content_widget)
                )
        else:
            max_content_width = max(
                max_content_width, widget_width_hint(content_widget)
            )
        max_content_height = max(
            max_content_height, widget_height_hint(content_widget)
        )

    return max_content_width, max_content_height


def clamp_to_screen(
    width: int,
    height: int,
    *,
    margin: int = 100,
) -> tuple[int, int]:
    screen = QApplication.primaryScreen()
    if screen is None:
        return width, height
    available = screen.availableGeometry()
    max_height = max(1, available.height() - margin)
    return width, min(height, max_height)


def apply_dialog_geometry(
    dialog: QWidget,
    width: int,
    height: int,
    *,
    policy: GeometryApplyPolicy | None = None,
) -> None:
    apply_policy = policy or GeometryApplyPolicy()
    final_width = width
    final_height = height

    if apply_policy.width_bounds is not None:
        min_w, max_w = apply_policy.width_bounds
        final_width = clamp(final_width, minimum=min_w, maximum=max_w)

    floor_w, floor_h = apply_policy.minimum_floor
    min_w = max(final_width, floor_w) if apply_policy.lock_minimum_to_computed else floor_w
    min_h = max(final_height, floor_h) if apply_policy.lock_minimum_to_computed else floor_h

    if apply_policy.remember_key is not None:
        _install_remembered_size_save_hook(dialog, apply_policy.remember_key)
        remembered = _load_remembered_size(apply_policy.remember_key)
        if remembered is not None:
            remembered_width, remembered_height = remembered
            final_width = max(min_w, remembered_width)
            final_height = max(min_h, remembered_height)
            if apply_policy.width_bounds is not None:
                bound_min_w, bound_max_w = apply_policy.width_bounds
                final_width = clamp(final_width, minimum=bound_min_w, maximum=bound_max_w)

    if apply_policy.update_minimum:
        dialog.setMinimumSize(min_w, min_h)

    if not apply_policy.resize_when_hidden and not apply_policy.force_resize:
        dialog.updateGeometry()
        _sync_dialog_csd_chrome(dialog)
        return

    if apply_policy.force_resize or not dialog.isVisible():
        dialog.resize(final_width, final_height)
        if apply_policy.center_on_parent:
            parent = dialog.parent() if hasattr(dialog, "parent") else None
            if parent is not None:
                geo = dialog.geometry()
                geo.moveCenter(parent.geometry().center())
                dialog.move(geo.topLeft())
    elif dialog.width() < min_w or dialog.height() < min_h:
        # setMinimumSize alone can grow the shell without a clean Resize path
        # for CSD mask rebuild — force an explicit resize when undersized.
        dialog.resize(max(dialog.width(), min_w), max(dialog.height(), min_h))

    dialog.updateGeometry()
    _sync_dialog_csd_chrome(dialog)


def _sync_dialog_csd_chrome(dialog: QWidget) -> None:
    """Rebuild CSD rounded mask/background after programmatic geometry changes."""
    try:
        from sli_ui_toolkit.ui.windows.csd_helpers import sync_csd_chrome
    except Exception:
        return
    sync_csd_chrome(dialog)


def _widget_contributes_to_size(widget: QWidget) -> bool:
    """True when the widget should count toward content-driven geometry.

    Prefer ``isHidden()`` over ``isVisible()``: while a parent dialog is still
    hidden (pre-show sizing), children report ``isVisible() == False`` even when
    they are not explicitly hidden and must still be measured.
    """
    if hasattr(widget, "isHidden"):
        return not bool(widget.isHidden())
    if hasattr(widget, "isVisible"):
        return bool(widget.isVisible())
    return True


def max_visible_widget_width_hint(
    widgets: Iterable[QWidget | None],
    *,
    default: int = 0,
) -> int:
    width = default
    for widget in widgets:
        if widget is None or not _widget_contributes_to_size(widget):
            continue
        width = max(width, widget_width_hint(widget))
    return width


def max_visible_widget_height_hint(
    widgets: Iterable[QWidget | None],
    *,
    default: int = 0,
) -> int:
    height = default
    for widget in widgets:
        if widget is None or not _widget_contributes_to_size(widget):
            continue
        height = max(height, widget_height_hint(widget))
    return height


def sum_visible_widget_height_hint(
    widgets: Iterable[QWidget | None],
    *,
    spacing: int = 0,
    default: int = 0,
) -> int:
    """Stacked height of non-hidden widgets plus ``spacing`` between them."""
    heights = [
        widget_height_hint(widget)
        for widget in widgets
        if widget is not None and _widget_contributes_to_size(widget)
    ]
    if not heights:
        return default
    gaps = max(0, len(heights) - 1) * max(0, int(spacing))
    return sum(heights) + gaps + default


def compute_scroll_footer_size(
    scroll_content: QWidget | None,
    footer: QWidget | None,
    *,
    outer_margins: int,
    spacing: int,
    extra_width_widgets: Iterable[QWidget | None] = (),
) -> tuple[int, int]:
    content_width = max(
        widget_width_hint(scroll_content),
        max_visible_widget_width_hint(extra_width_widgets),
    )
    content_height = widget_height_hint(scroll_content)
    footer_width = widget_width_hint(footer)
    footer_height = widget_height_hint(footer)
    total_width = max(content_width, footer_width) + outer_margins
    total_height = content_height + spacing + footer_height + outer_margins
    return total_width, total_height


def measure_layout_minimum_with_preferred_canvas(
    layout: QLayout | None,
    canvas: QWidget | None,
    *,
    min_width_floor: int = 250,
    min_height_floor: int = 300,
    padding: int = 10,
) -> tuple[int, int]:
    from PySide6.QtWidgets import QSizePolicy

    if layout is None or canvas is None:
        return min_width_floor + padding, min_height_floor + padding

    original_policy = canvas.sizePolicy()
    temp_policy = QSizePolicy(
        QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred
    )
    temp_policy.setHeightForWidth(original_policy.hasHeightForWidth())
    temp_policy.setWidthForHeight(original_policy.hasWidthForHeight())
    temp_policy.setVerticalPolicy(
        QSizePolicy.Policy.Preferred
        if original_policy.verticalPolicy() != QSizePolicy.Policy.Ignored
        else QSizePolicy.Policy.Ignored
    )
    temp_policy.setHorizontalPolicy(
        QSizePolicy.Policy.Preferred
        if original_policy.horizontalPolicy() != QSizePolicy.Policy.Ignored
        else QSizePolicy.Policy.Ignored
    )

    try:
        canvas.setSizePolicy(temp_policy)
        canvas.updateGeometry()
        layout.invalidate()
        layout.activate()
        layout_hint_size = layout.sizeHint()
        return (
            max(min_width_floor, layout_hint_size.width()) + padding,
            max(min_height_floor, layout_hint_size.height()) + padding,
        )
    finally:
        if canvas.sizePolicy() != original_policy:
            canvas.setSizePolicy(original_policy)
            canvas.updateGeometry()
            layout.invalidate()
            layout.activate()


def install_dialog_geometry_lifecycle(
    dialog: Any,
    apply_geometry: Callable[[], None],
    *,
    theme_manager: Any | None = None,
) -> None:
    """Defer geometry after font/theme changes.

    Prefer :class:`shared_toolkit.ui.themed_dialog.ThemedDialog` for app
    dialogs — it already defers geometry from :meth:`on_theme_changed`. Pass
    ``theme_manager`` here only for dialogs that do not inherit ThemedDialog
    (e.g. toolkit ``MarkdownHelpDialog`` subclasses). When passed, the
    connection is dropped on ``dialog.destroyed`` so deleteLater'd windows
    cannot schedule geometry on a dead C++ object during later theme flips.
    """
    dialog._apply_dialog_geometry = apply_geometry
    defer_dialog_geometry(dialog, apply_geometry)
    if theme_manager is None:
        return

    def _on_theme_changed(*_args) -> None:
        defer_dialog_geometry(dialog, apply_geometry)

    theme_manager.theme_changed.connect(_on_theme_changed)

    def _disconnect(*_args) -> None:
        try:
            theme_manager.theme_changed.disconnect(_on_theme_changed)
        except (RuntimeError, TypeError):
            pass

    destroyed = getattr(dialog, "destroyed", None)
    if destroyed is not None:
        destroyed.connect(_disconnect)


def handle_application_font_change(dialog: Any, event: QEvent) -> bool:
    if event.type() != QEvent.Type.ApplicationFontChange:
        return False
    apply_geometry = getattr(dialog, "_apply_dialog_geometry", None)
    if callable(apply_geometry):
        defer_dialog_geometry(dialog, apply_geometry)
    return True


def defer_dialog_geometry(
    dialog: Any,
    callback: Callable[[], None],
) -> None:
    def _run() -> None:
        try:
            from shiboken6 import isValid

            if not isValid(dialog):
                return
        except ImportError:
            pass
        callback()

    QTimer.singleShot(0, _run)
