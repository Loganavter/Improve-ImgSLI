"""Gallery toolbar — painter-pipeline only, no QSS.

Provides ``GalleryToolbar`` with surface Button + CustomLineEdit (+ optional
ScrollableComboBox). Signals: ``openClicked`` and ``filterChanged(str)``,
plus ``sortChanged(str)`` and ``viewToggled(bool)``.
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QHBoxLayout, QWidget

from sli_ui_toolkit.managers import scaled_px
from sli_ui_toolkit.widgets import Button, CustomLineEdit, Label, LoadingSpinner, ScrollableComboBox

from tabs.image_gallery.icons import Icon as GalleryIcon


def _resolve_toolbar_triage_color() -> QColor:
    try:
        from sli_ui_toolkit.managers import ThemeManager
        from ui.theming import try_resolve_theme_color
        c = try_resolve_theme_color(ThemeManager.get_instance(), "gallery.status.ok")
        if c is not None:
            return QColor(c) if isinstance(c, str) else c
    except Exception:
        pass
    return QColor("#3fbf5f")

def _resolve_toolbar_accent_border(alpha: int = 153) -> QColor:
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
    return QColor(0, 150, 255, int(alpha))


class GalleryToolbarViewSwitchContainer(QWidget):
    """Segmented view-switch background (106×32, gallery.stats.background, r8).

    Plain QWidget with a dedicated type so UI Inspector's Code tab can resolve
    ``getsourcefile(type(widget))`` to ``toolbar.py`` instead of ``PySide6.QtWidgets.QWidget``.
    See ``sli-ui-toolkit/src/sli_ui_toolkit/ui/inspector/code/factory.py:81``.
    """

    def paintEvent(self, event) -> None:  # noqa: N802
        try:
            from PySide6.QtCore import QRectF
            from PySide6.QtGui import QColor, QPainter

            from sli_ui_toolkit.managers import ThemeManager
            from ui.theming import try_resolve_theme_color

            p = QPainter(self)
            p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            # Outer 106×32 r8 fill #333 + stroke #4a4a4a per svg x1130 y74
            try:
                col = try_resolve_theme_color(ThemeManager.get_instance(), "gallery.stats.background")
                bg = QColor(col) if isinstance(col, str) else col
                if bg is None:
                    bg = QColor("#333333")
            except Exception:
                bg = QColor("#333333")
            try:
                border = try_resolve_theme_color(ThemeManager.get_instance(), "dialog.border")
                border_col = QColor(border) if isinstance(border, str) else border
                if border_col is None:
                    border_col = QColor("#4a4a4a")
            except Exception:
                border_col = QColor("#4a4a4a")
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
    signals. No ``setStyleSheet`` — visuals via Button/CustomLineEdit painter
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
        self._translate = translate

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
        # The filter field is not a drop target: a default QLineEdit accepts
        # drags, which would steal the drag target from the gallery drop
        # routing (widget/grid/empty-state acceptDrops) whenever the cursor
        # is over the toolbar — same thief as the image_compare caption
        # edits (see tabs/image_compare/ui/primitives.py).
        self._filter_edit.setAcceptDrops(False)
        self._filter_edit.setPlaceholderText(placeholder)
        self._filter_edit.setClearButtonEnabled(True)
        self._filter_edit.textChanged.connect(self.filterChanged.emit)
        try:
            self._filter_edit.setFixedWidth(scaled_px(280))
        except Exception:
            pass
        layout.addWidget(self._filter_edit)

        # Sort combo — 140×33 bg.band custom dropdown
        self._sort_combo = ScrollableComboBox(self)
        self._sort_combo.setObjectName("gallery_toolbar_sort")
        try:
            self._sort_combo.setFixedWidth(scaled_px(140))
        except Exception:
            pass
        for label in ("Sort: Rank", "Sort: Name", "Sort: Date"):
            self._sort_combo.addItem(label)
        self._sort_combo.setCurrentIndex(0)
        try:
            self._sort_combo.currentTextChanged.connect(self.sortChanged.emit)  # type: ignore[attr-defined]
        except Exception:
            try:
                self._sort_combo.currentIndexChanged.connect(lambda _i: self.sortChanged.emit(self._sort_combo.currentText()))  # type: ignore[attr-defined]
            except Exception:
                pass
        layout.addWidget(self._sort_combo)

        # Scanning near Sort (S1), triage centered-right (S2) — SVG x660 green ✓
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

        # Stretch pushes triage indicator to center/right (SVG: x660, green #3fbf5f, 12px)
        layout.addStretch(1)

        # Triage indicator — centered/right, green check via gallery.status.ok token
        self._triage_indicator = Label(
            "✓ triage complete", pixel_size=12, color=_resolve_toolbar_triage_color(), parent=self
        )
        self._triage_indicator.setObjectName("gallery_triage_indicator")
        try:
            self._triage_indicator.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        except Exception:
            pass
        try:
            self._triage_indicator.hide()
        except Exception:
            pass
        layout.addWidget(self._triage_indicator)
        try:
            layout.setAlignment(self._triage_indicator, Qt.AlignmentFlag.AlignVCenter)
        except Exception:
            pass

        # Small stretch before view-switcher keeps triage not jammed to edge
        layout.addStretch(1)

        # View switch — segmented 106×32 bg.band (real_design.md:49) — rounded r8 via paintEvent, no QSS
        self._view_switch_container = GalleryToolbarViewSwitchContainer(self)
        self._view_switch_container.setObjectName("gallery_toolbar_view_switch_container")
        try:
            self._view_switch_container.setFixedSize(scaled_px(106), scaled_px(32))
        except Exception:
            pass
        try:
            self._view_switch_container.setAutoFillBackground(False)
        except Exception:
            pass
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
                    if not is_list:
                        self._view_switch.setBorderColor(_resolve_toolbar_accent_border(153))
                        self._view_switch_list.setBorderColor(QColor(0, 0, 0, 0))
                    else:
                        self._view_switch.setBorderColor(QColor(0, 0, 0, 0))
                        self._view_switch_list.setBorderColor(_resolve_toolbar_accent_border(153))
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
                # Active: border, inactive: no border — icon color via tuple (no setForegroundColor hack)
                try:
                    if not is_list:
                        self._view_switch.setBorderColor(_resolve_toolbar_accent_border(153))
                        self._view_switch_list.setBorderColor(QColor(0, 0, 0, 0))
                    else:
                        self._view_switch.setBorderColor(QColor(0, 0, 0, 0))
                        self._view_switch_list.setBorderColor(_resolve_toolbar_accent_border(153))
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

        self._mode_combo: ScrollableComboBox | None = None
        if with_mode_combo:
            self._mode_combo = ScrollableComboBox(self)
            self._mode_combo.setObjectName("gallery_toolbar_mode_combo")
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

    # -- public accessors ------------------------------------------------

    @property
    def pick_button(self) -> Button:
        return self._pick_button

    @property
    def filter_edit(self) -> CustomLineEdit:
        return self._filter_edit

    @property
    def sort_combo(self) -> ScrollableComboBox:
        return self._sort_combo

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

    @property
    def triage_indicator(self) -> Label:
        return self._triage_indicator

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
            if self._translate is not None:
                tr_text = self._translate("image_gallery.scanning", text)
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
        try:
            self._triage_indicator.hide()
        except Exception:
            pass

    def set_triage_done(self) -> None:
        """S2: hide scanning, show ✓ triage complete."""
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
        try:
            self._triage_indicator.show()
        except Exception:
            pass

    def retranslate(self, translate: Callable[[str, str], str] | None = None) -> None:
        """Update translatable texts in place."""
        if translate is not None:
            self._translate = translate
        tr = self._translate

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
