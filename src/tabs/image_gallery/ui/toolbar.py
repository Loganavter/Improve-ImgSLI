"""Gallery toolbar — painter-pipeline only, no QSS.

Provides ``GalleryToolbar`` with surface Button + CustomLineEdit (+ optional
ScrollableComboBox). Signals: ``openClicked`` and ``filterChanged(str)``,
plus ``sortChanged(str)`` and ``viewToggled(bool)``.
Audit-Meta: pattern=compound-widget size=exempt reason="toolbar + view-switch sharing one paint/theme lifecycle — split tracked post light-theme epic"
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QHBoxLayout, QWidget

from sli_ui_toolkit.managers import scaled_px
from sli_ui_toolkit.widgets import Button, ComboBox, CustomLineEdit, Label, LoadingSpinner, SimpleOptionsFlyout

from tabs.image_gallery.icons import Icon as GalleryIcon


def _is_dark_theme() -> bool:
    try:
        from sli_ui_toolkit.managers import ThemeManager

        inst = ThemeManager.get_instance()
        try:
            return bool(inst.is_dark())
        except Exception:
            pass
        try:
            return str(inst.get_current_theme()).lower() != "light"
        except Exception:
            pass
    except Exception:
        pass
    return True


def _resolve_toolbar_accent_fill(alpha: int = 51) -> QColor:
    """S2 mockup x1130 y74: active view segment is a fill-chip (blue 0.2), not a border."""
    try:
        from sli_ui_toolkit.managers import ThemeManager
        from ui.theming import try_resolve_theme_color
        for token in ("gallery.accent.bar", "accent"):
            c = try_resolve_theme_color(ThemeManager.get_instance(), token)
            if c is not None:
                col = QColor(c) if isinstance(c, str) else QColor(c)
                try: col.setAlpha(int(alpha))
                except Exception: pass
                return col
    except Exception: pass
    # NOTE: was (0,150,255) at alpha (dark-only rgba) — now accent light/dark chain.
    col = QColor("#0078D4" if not _is_dark_theme() else "#0096FF")
    try:
        col.setAlpha(int(alpha))
    except Exception:
        pass
    return col


def _apply_view_fill_chip(active_btn, inactive_btn) -> None:
    """Active segment = accent fill-chip; inactive = transparent (no border)."""
    try:
        active_btn.set_override_bg_color(_resolve_toolbar_accent_fill())
    except Exception:
        pass
    try:
        inactive_btn.set_override_bg_color(None)
    except Exception:
        pass
    try:
        active_btn.setBorderColor(QColor(0, 0, 0, 0))
        inactive_btn.setBorderColor(QColor(0, 0, 0, 0))
    except Exception:
        pass


class GalleryToolbarViewSwitchContainer(QWidget):
    """Segmented view-switch background (106×32, r8, painter-painted, no QSS)."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        try:
            from sli_ui_toolkit.managers import ThemeManager

            ThemeManager.get_instance().theme_changed.connect(self._on_theme_changed)
        except Exception:
            pass

    def _on_theme_changed(self) -> None:
        try:
            self.update()
        except Exception:
            pass

    def on_theme_changed(self) -> None:
        self._on_theme_changed()

    def paintEvent(self, event) -> None:  # noqa: N802
        try:
            from PySide6.QtCore import QRectF
            from PySide6.QtGui import QColor, QPainter

            from sli_ui_toolkit.managers import ThemeManager
            from ui.theming import try_resolve_theme_color

            p = QPainter(self)
            p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            try:
                col = try_resolve_theme_color(ThemeManager.get_instance(), "gallery.stats.background")
                bg = QColor(col) if isinstance(col, str) else col
                if bg is None:
                    # NOTE: was #333333 (dark-only) — now stats-background light/dark chain.
                    bg = QColor("#8a8a8a" if not _is_dark_theme() else "#3c3c3c")
            except Exception:
                # NOTE: was #333333 (dark-only) — now stats-background light/dark chain.
                bg = QColor("#8a8a8a" if not _is_dark_theme() else "#3c3c3c")
            try:
                border = try_resolve_theme_color(ThemeManager.get_instance(), "dialog.border")
                border_col = QColor(border) if isinstance(border, str) else border
                if border_col is None:
                    # NOTE: was #4a4a4a (dark-only) — now dialog-border light/dark chain.
                    border_col = QColor("#c0c0c0" if not _is_dark_theme() else "#555555")
            except Exception:
                # NOTE: was #4a4a4a (dark-only) — now dialog-border light/dark chain.
                border_col = QColor("#c0c0c0" if not _is_dark_theme() else "#555555")
            p.setPen(border_col)
            p.setBrush(bg)
            p.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 8, 8)
            p.end()
        except Exception:
            pass
        try:
            super().paintEvent(event)
        except Exception:
            pass


class GalleryToolbar(QWidget):
    """Toolbar row for the gallery: Open Folder + filter + Sort + view switch (svg v2).

    Thin owner: state lives on the parent controller; this widget only emits
    signals. No QSS styling — visuals via Button/CustomLineEdit painter
    pipeline. Matches ui-mockup-v2-triage.svg toolbar y72 h34.
    """

    openClicked = Signal()
    filterChanged = Signal(str)
    sortChanged = Signal(str)
    viewToggled = Signal(bool)

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        translate: Callable[[str, str], str] | None = None,
        with_mode_combo: bool = False,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("GalleryToolbar")
        self._tr = translate

        def _tr(key: str, default: str) -> str:
            if translate is None:
                return default
            try:
                return translate(key, default)
            except Exception:
                return default

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(scaled_px(20))

        pick_text = "Open Folder…"
        # real_design.md:2.1 — 132×34 иконка внутри, без truncation (unified EN)
        self._pick_button = Button(
            icon="folder_open",
            text=pick_text,
            variant="surface",
            size=(scaled_px(132), scaled_px(34)),
            parent=self,
        )
        self._pick_button.setObjectName("gallery_toolbar_pick")
        # Allow expansion for long locale strings (ru "Выбрать папку…")
        try:
            from PySide6.QtWidgets import QSizePolicy as _QSP2

            self._pick_button.setSizePolicy(_QSP2.Policy.Minimum, _QSP2.Policy.Fixed)
            self._pick_button.setMinimumWidth(scaled_px(132))
            self._pick_button.setMaximumWidth(scaled_px(220))
            self._pick_button.setFixedHeight(scaled_px(34))
        except Exception:
            pass
        self._pick_button.clicked.connect(self.openClicked.emit)
        layout.addWidget(self._pick_button)

        placeholder = "Filter by tag / description…"
        self._filter_edit = CustomLineEdit(self)
        self._filter_edit.setObjectName("gallery_toolbar_filter")
        self._filter_edit.setAcceptDrops(False)
        self._filter_edit.setPlaceholderText(placeholder)
        self._filter_edit.setClearButtonEnabled(True)
        self._filter_edit.textChanged.connect(self.filterChanged.emit)
        try:
            self._filter_edit.setFixedWidth(scaled_px(280))
        except Exception:
            pass
        # Toolbar row is 34px — match the buttons (CustomLineEdit defaults
        # to HEIGHT=32; instance override survives on_scale_changed).
        try:
            self._filter_edit.HEIGHT = 34  # type: ignore[attr-defined]
            self._filter_edit.setFixedHeight(scaled_px(34))
        except Exception:
            pass
        layout.addWidget(self._filter_edit)

        # Sort picker — surface button + SimpleOptionsFlyout (mode_picker.py
        # precedent: button, populate(labels, current), show_below, item_chosen).
        self._sort_items = ["Sort: Rank", "Sort: Name", "Sort: Date", "Sort: AI quality"]
        self._sort_index = 0
        self._sort_flyout: SimpleOptionsFlyout | None = None
        self._sort_combo = Button(
            text="Sort: Rank ▾",
            variant="surface",
            width_texts=[f"{text} ▾" for text in self._sort_items],
            size=(0, scaled_px(34)),
            corner_radius=6,
            parent=self,
        )
        self._sort_combo.setObjectName("gallery_toolbar_sort")
        # Same drop-thief rationale as filter edit above.
        try:
            self._sort_combo.setAcceptDrops(False)
        except Exception:
            pass
        # Height fixed to the 34px row (Open Folder + filter); width comes
        # from the width_texts hints (widest option), not a hardcoded 140.
        try:
            self._sort_combo.setFixedHeight(scaled_px(34))
        except Exception:
            pass
        try:
            self._sort_combo.clicked.connect(self._on_sort_clicked)
        except Exception:
            pass
        layout.addWidget(self._sort_combo)

        # Scanning near Sort (S1)
        try:
            layout.setSpacing(scaled_px(20))
        except Exception:
            pass
        layout.addSpacing(scaled_px(4))

        # Scanning indicator — LoadingSpinner + Label "Scanning n/N" (S1) stays near Sort
        self._spinner = LoadingSpinner(self)
        self._spinner.setObjectName("gallery_toolbar_spinner")
        try:
            self._spinner.setFixedSize(scaled_px(16), scaled_px(16))
        except Exception:
            pass
        try:
            self._spinner.hide()
        except Exception:
            pass
        layout.addWidget(self._spinner)

        self._scanning_label = Label("", pixel_size=11, parent=self)
        self._scanning_label.setObjectName("gallery_toolbar_scanning")
        try:
            self._scanning_label.hide()
        except Exception:
            pass
        layout.addWidget(self._scanning_label)

        # Stretch pushes view-switcher to the right edge
        layout.addStretch(1)

        # View switch — segmented 106×32 bg.band (real_design.md:49) — rounded r8 via paintEvent, no QSS
        self._view_switch_container = GalleryToolbarViewSwitchContainer(self)
        self._view_switch_container.setObjectName("gallery_toolbar_view_switch_container")
        try:
            self._view_switch_container.setFixedSize(scaled_px(106), scaled_px(32))
        except Exception:
            pass
        # Container paints its own background in paintEvent (explicit fill).
        vs_lay = QHBoxLayout(self._view_switch_container)
        vs_lay.setContentsMargins(scaled_px(2), scaled_px(2), scaled_px(2), scaled_px(2))
        vs_lay.setSpacing(scaled_px(2))
        # Segmented switcher 106×32 — two exclusive segments grid/list, SVG x1130 y74 r8 highlight 44×16 blue 0.2 on active side.
        # Proper API: icon=(unchecked, checked) per BUTTON_API.md — no QPainter tint hack.
        self._view_switch = Button(
            icon=(GalleryIcon.VIEW_GRID_INACTIVE, GalleryIcon.VIEW_GRID),
            variant="ghost",
            toggle=True,
            size=(scaled_px(48), scaled_px(28)),
            parent=self._view_switch_container,
        )
        self._view_switch.setObjectName("gallery_toolbar_view_switch")
        self._view_switch_list = Button(
            icon=(GalleryIcon.VIEW_LIST, GalleryIcon.VIEW_LIST_ACTIVE),
            variant="ghost",
            toggle=True,
            size=(scaled_px(48), scaled_px(28)),
            parent=self._view_switch_container,
        )
        self._view_switch_list.setObjectName("gallery_toolbar_view_switch_list")
        # Exclusive helper — active has border, inactive has none; icon color via tuple, emits viewToggled(bool) is_list
        self._is_list = False  # current view: False grid, True list
        def _apply_view(is_list: bool) -> None:
            is_list = bool(is_list)
            # Already in desired view — revert the auto-toggle flip that Button did on click, no emit
            if getattr(self, "_is_list", False) == is_list:
                try:
                    self._view_switch.blockSignals(True)
                    self._view_switch_list.blockSignals(True)
                    self._view_switch.setChecked(not is_list)
                    self._view_switch_list.setChecked(is_list)
                    # S2 mockup: active = fill-chip, not border.
                    if not is_list:
                        _apply_view_fill_chip(self._view_switch, self._view_switch_list)
                    else:
                        _apply_view_fill_chip(self._view_switch_list, self._view_switch)
                finally:
                    try:
                        self._view_switch.blockSignals(False)
                        self._view_switch_list.blockSignals(False)
                    except Exception:
                        pass
                return
            try:
                self._view_switch.blockSignals(True)
                self._view_switch_list.blockSignals(True)
                self._view_switch.setChecked(not is_list)
                self._view_switch_list.setChecked(is_list)
                # Active: fill-chip, inactive: transparent — icon color via tuple (no setForegroundColor hack)
                try:
                    if not is_list:
                        _apply_view_fill_chip(self._view_switch, self._view_switch_list)
                    else:
                        _apply_view_fill_chip(self._view_switch_list, self._view_switch)
                except Exception:
                    pass
            finally:
                try:
                    self._view_switch.blockSignals(False)
                    self._view_switch_list.blockSignals(False)
                except Exception:
                    pass
            self._is_list = is_list
            try:
                self.viewToggled.emit(is_list)
            except Exception:
                pass

        # Initial: grid active (False), list inactive
        try:
            _apply_view(False)
        except Exception:
            try:
                self._view_switch.setChecked(True)
                self._view_switch_list.setChecked(False)
            except Exception:
                pass
        try:
            self._view_switch.clicked.connect(lambda: _apply_view(False))
            self._view_switch_list.clicked.connect(lambda: _apply_view(True))
        except Exception:
            pass
        vs_lay.addWidget(self._view_switch)
        vs_lay.addWidget(self._view_switch_list)
        # Expose helper for tests/programmatic switch
        self._apply_view = _apply_view  # type: ignore[attr-defined]
        layout.addWidget(self._view_switch_container)

        self._mode_combo: ComboBox | None = None
        if with_mode_combo:
            self._mode_combo = ComboBox(self)
            self._mode_combo.setObjectName("gallery_toolbar_mode_combo")
            # Same drop-thief rationale as sort combo / filter edit above.
            try:
                self._mode_combo.setAcceptDrops(False)
            except Exception:
                pass
            for label in ("All", "Fidelity", "Camera", "Batch"):
                self._mode_combo.addItem(label)
            if self._mode_combo.count() > 0:
                self._mode_combo.setCurrentIndex(0)
            layout.addWidget(self._mode_combo)

        # Fixed height like svg toolbar 34px
        try:
            self.setFixedHeight(scaled_px(34))
            from PySide6.QtWidgets import QSizePolicy as _QSP

            self.setSizePolicy(_QSP.Policy.Expanding, _QSP.Policy.Fixed)
        except Exception:
            pass

        # Theme fan-out: tokens are re-read live, so refresh chips + indicator.
        try:
            from sli_ui_toolkit.managers import ThemeManager

            ThemeManager.get_instance().theme_changed.connect(self._on_theme_changed)
        except Exception:
            pass

    def _on_theme_changed(self) -> None:
        """Re-resolve token colors and repaint (no palette, no QSS)."""
        try:
            apply_view = getattr(self, "_apply_view", None)
            if callable(apply_view):
                apply_view(bool(getattr(self, "_is_list", False)))
        except Exception:
            pass
        try:
            self._view_switch_container.update()
        except Exception:
            pass
        try:
            self.update()
        except Exception:
            pass

    def on_theme_changed(self) -> None:
        self._on_theme_changed()

    # -- public accessors ------------------------------------------------

    @property
    def pick_button(self) -> Button:
        return self._pick_button

    @property
    def filter_edit(self) -> CustomLineEdit:
        return self._filter_edit

    @property
    def sort_combo(self) -> Button:
        return self._sort_combo

    @property
    def sort_index(self) -> int:
        return int(self._sort_index)

    def sort_text(self) -> str:
        try:
            return str(self._sort_items[int(self._sort_index)])
        except Exception:
            return "Sort: Rank"

    def set_view_list(self, is_list: bool) -> None:
        """Select grid/list view programmatically (emits viewToggled)."""
        try:
            self._apply_view(bool(is_list))  # type: ignore[attr-defined]
        except Exception:
            pass

    def set_sort_index(self, index: int) -> None:
        """Select a sort option by index (emits sortChanged on change)."""
        try:
            index = int(index)
        except Exception:
            return
        if 0 <= index < len(self._sort_items) and index != self._sort_index:
            self._sort_index = index
            try:
                self._sort_combo.setText(f"{self._sort_items[index]} ▾")
            except Exception:
                pass
            try:
                self.sortChanged.emit(self._sort_items[index])
            except Exception:
                pass

    @property
    def view_switch(self) -> Button:
        return self._view_switch

    @property
    def view_switch_list(self) -> Button:
        return self._view_switch_list

    @property
    def spinner(self) -> LoadingSpinner:
        return self._spinner

    @property
    def scanning_label(self) -> Label:
        return self._scanning_label

    def set_scanning(self, n: int, total: int) -> None:
        """Show S1 scanning state: spinner + Label n/N."""
        try:
            n_i = int(n)
            t_i = int(total)
        except Exception:
            n_i = 0
            t_i = 0
        text = f"{n_i}/{t_i}" if t_i > 0 else f"{n_i}"
        # Localize if translator available
        try:
            if self._tr is not None:
                tr_text = self._tr("image_gallery.scanning", text)
                # If translation returns key, keep our n/N
                if tr_text != "image_gallery.scanning":
                    text = tr_text.replace("{n}", str(n_i)).replace("{total}", str(t_i)) if "{n}" in tr_text else text
        except Exception:
            pass
        try:
            self._scanning_label.setText(text)
            self._scanning_label.show()
        except Exception:
            pass
        try:
            self._spinner.show()
            self._spinner.start()
        except Exception:
            pass

    def set_triage_done(self) -> None:
        """S2: hide scanning (triage indicator removed)."""
        try:
            self._spinner.stop()
        except Exception:
            pass
        try:
            self._spinner.hide()
        except Exception:
            pass
        try:
            self._scanning_label.hide()
            self._scanning_label.setText("")
        except Exception:
            pass

    # -- sort picker (Button + SimpleOptionsFlyout) ------------------------

    def _sort_flyout_ensure(self) -> SimpleOptionsFlyout | None:
        parent = None
        try:
            parent = self.window()
        except Exception:
            parent = None
        if parent is None:
            try:
                parent = self
            except Exception:
                return None
        flyout = getattr(self, "_sort_flyout", None)
        if flyout is None:
            try:
                flyout = SimpleOptionsFlyout(parent_widget=parent)
            except Exception:
                return None
            try:
                flyout.item_chosen.connect(self._on_sort_chosen)
            except Exception:
                pass
            self._sort_flyout = flyout
        return flyout

    def _on_sort_clicked(self) -> None:
        """Open the sort flyout under the button (toggles on re-click)."""
        try:
            flyout = self._sort_flyout_ensure()
            if flyout is None:
                return
            # Manual same-anchor toggle: a visible flyout closes on re-click
            # (deterministic here; show_below toggles same-anchor too).
            try:
                if flyout.isVisible():
                    flyout.hide()
                    return
            except Exception:
                pass
            # Match the button metrics (transient_interpolation.py precedent:
            # set_row_height takes design px, button height is 34 design).
            try:
                flyout.set_row_height(34)
            except Exception:
                pass
            flyout.populate(list(self._sort_items), int(self._sort_index))
            # Content width: uniform rows on the widest label
            # ("Sort: Name"), tight card. The button carries " ▾" the rows
            # don't, so anchor-matching leaves trailing slack in every row.
            flyout.show_below(self._sort_combo, width_mode="content")
        except Exception:
            pass

    def _on_sort_chosen(self, index: int) -> None:
        self.set_sort_index(index)

    def retranslate(self, translate: Callable[[str, str], str] | None = None) -> None:
        """Update translatable texts in place."""
        if translate is not None:
            self._tr = translate
        tr = self._tr

        def _tr(key: str, default: str) -> str:
            if tr is None:
                return default
            try:
                return tr(key, default)
            except Exception:
                return default

        try:
            self._pick_button.setText("Open Folder…")
        except Exception:
            pass
        try:
            self._filter_edit.setPlaceholderText("Filter by tag / description…")
        except Exception:
            pass
