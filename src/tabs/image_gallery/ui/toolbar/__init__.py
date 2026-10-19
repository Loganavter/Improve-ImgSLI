"""Gallery toolbar — painter-pipeline only, no QSS.

Provides ``GalleryToolbar`` with surface Button + CustomLineEdit (+ optional
ScrollableComboBox). Signals: ``openClicked`` and ``filterChanged(str)``,
plus ``sortChanged(str)`` and ``viewToggled(bool)``.
Audit-Meta: pattern=compound-widget size=exempt reason="toolbar + view-switch sharing one paint/theme lifecycle — split tracked post light-theme epic"
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QWidget

from sli_ui_toolkit.managers import scaled_px
from sli_ui_toolkit.widgets import Button, ComboBox, CustomLineEdit, Label, LoadingSpinner, SimpleOptionsFlyout

from tabs.image_gallery.icons import Icon as GalleryIcon

# Package split (plan-gallery-split-2026-10-17, Part C6): theme helpers
# (theme.py), segmented-switch containers (containers.py) and the sort-picker
# wiring (sort_picker.py) live in submodules; re-export them so
# ``tabs.image_gallery.ui.toolbar`` keeps its full surface for importers.
from . import sort_picker
from .containers import (  # noqa: F401
    GalleryToolbarDomainSwitchContainer,
    GalleryToolbarViewSwitchContainer,
)
from .theme import (  # noqa: F401
    _apply_view_fill_chip,
    _is_dark_theme,
    _resolve_toolbar_accent_fill,
)

#: Sort option i18n keys, 1:1 with ``GalleryToolbar._sort_items`` indices.
#: ``_sort_items`` holds the EN canonical machine labels (the ``sortChanged``
#: signal payload that ``widget.py:_on_sort_changed`` matches substrings on);
#: these keys feed ONLY the displayed button/row label — index mapping is 1:1.
SORT_OPTION_KEYS = (
    "image_gallery.sort_rank",
    "image_gallery.sort_name",
    "image_gallery.sort_date",
    "image_gallery.sort_quality",
)
SORT_OPTION_DEFAULTS = ("Rank", "Name", "Date", "AI quality")


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
    domainChanged = Signal(str)

    #: Sort option gated to the AI judgment domain (orders by an AI score).
    _AI_SORT_LABEL = "Sort: AI quality"

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

        pick_text = _tr("image_gallery.toolbar.open_folder", "Open Folder…")
        # real_design.md:2.1 — 132×34 иконка внутри, без truncation (unified EN)
        self._pick_button = Button(
            icon="folder_open",
            text=pick_text,
            variant="surface",
            # Design px: Button(size=...) scales internally exactly once — a
            # scaled_px() here double-scales (factor^2 drift) at factor > 1.0.
            size=(132, 34),
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

        placeholder = _tr("image_gallery.toolbar.filter_placeholder", "Filter by tag / description…")
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
            text=f"{self._sort_display(0)} ▾",
            variant="surface",
            width_texts=[f"{self._sort_display(i)} ▾" for i in range(len(self._sort_items))],
            size=(0, 34),
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

        # Domain switch — segmented Algorithms|AI (plan-gallery-two-domain-axes
        # W2). Placed right after Sort; the scanner + view-switch keep their
        # positions (view-switch stays last/rightmost).
        self._judgment_domain = "algorithms"
        self._domain_switch_container = GalleryToolbarDomainSwitchContainer(self)
        self._domain_switch_container.setObjectName("gallery_toolbar_domain_switch_container")
        try:
            self._domain_switch_container.setFixedSize(scaled_px(106), scaled_px(32))
        except Exception:
            pass
        # Container paints its own background in paintEvent (explicit fill).
        ds_lay = QHBoxLayout(self._domain_switch_container)
        ds_lay.setContentsMargins(scaled_px(2), scaled_px(2), scaled_px(2), scaled_px(2))
        ds_lay.setSpacing(scaled_px(2))
        # Icon-only segments (view-switch pattern): a chip = algorithms, a
        # sparkle = AI. Text labels would clip in the 34px toolbar row.
        self._domain_switch = Button(
            icon=(GalleryIcon.ALGORITHMS_INACTIVE, GalleryIcon.ALGORITHMS),
            variant="ghost",
            toggle=True,
            size=(48, 28),  # design px — Button scales internally (no scaled_px)
            parent=self._domain_switch_container,
        )
        self._domain_switch.setObjectName("gallery_toolbar_domain_switch")
        try:
            self._domain_switch.setToolTip(_tr("image_gallery.domain.algorithms", "Algorithms"))
        except Exception:
            pass
        self._domain_switch_ai = Button(
            icon=(GalleryIcon.AI_INACTIVE, GalleryIcon.AI),
            variant="ghost",
            toggle=True,
            size=(48, 28),  # design px — Button scales internally (no scaled_px)
            parent=self._domain_switch_container,
        )
        self._domain_switch_ai.setObjectName("gallery_toolbar_domain_switch_ai")
        try:
            self._domain_switch_ai.setToolTip(_tr("image_gallery.domain.ai", "AI"))
        except Exception:
            pass

        def _apply_domain(domain: str) -> None:
            dom = str(domain or "").strip().lower()
            if dom not in ("algorithms", "ai"):
                dom = "algorithms"
            # Already in desired domain — revert the auto-toggle flip that
            # Button did on click, no emit.
            if getattr(self, "_judgment_domain", "algorithms") == dom:
                try:
                    self._domain_switch.blockSignals(True)
                    self._domain_switch_ai.blockSignals(True)
                    self._domain_switch.setChecked(dom == "algorithms")
                    self._domain_switch_ai.setChecked(dom == "ai")
                    if dom == "algorithms":
                        _apply_view_fill_chip(self._domain_switch, self._domain_switch_ai)
                    else:
                        _apply_view_fill_chip(self._domain_switch_ai, self._domain_switch)
                finally:
                    try:
                        self._domain_switch.blockSignals(False)
                        self._domain_switch_ai.blockSignals(False)
                    except Exception:
                        pass
                return
            try:
                self._domain_switch.blockSignals(True)
                self._domain_switch_ai.blockSignals(True)
                self._domain_switch.setChecked(dom == "algorithms")
                self._domain_switch_ai.setChecked(dom == "ai")
                try:
                    if dom == "algorithms":
                        _apply_view_fill_chip(self._domain_switch, self._domain_switch_ai)
                    else:
                        _apply_view_fill_chip(self._domain_switch_ai, self._domain_switch)
                except Exception:
                    pass
            finally:
                try:
                    self._domain_switch.blockSignals(False)
                    self._domain_switch_ai.blockSignals(False)
                except Exception:
                    pass
            self._judgment_domain = dom
            try:
                self.domainChanged.emit(dom)
            except Exception:
                pass

        # Initial: algorithms active, AI inactive (no emit).
        try:
            _apply_domain("algorithms")
        except Exception:
            try:
                self._domain_switch.setChecked(True)
                self._domain_switch_ai.setChecked(False)
            except Exception:
                pass
        try:
            self._domain_switch.clicked.connect(lambda: _apply_domain("algorithms"))
            self._domain_switch_ai.clicked.connect(lambda: _apply_domain("ai"))
        except Exception:
            pass
        ds_lay.addWidget(self._domain_switch)
        ds_lay.addWidget(self._domain_switch_ai)
        # Expose helper for tests/programmatic switch.
        self._apply_domain = _apply_domain  # type: ignore[attr-defined]
        layout.addWidget(self._domain_switch_container)

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
            size=(48, 28),  # design px — Button scales internally (no scaled_px)
            parent=self._view_switch_container,
        )
        self._view_switch.setObjectName("gallery_toolbar_view_switch")
        self._view_switch_list = Button(
            icon=(GalleryIcon.VIEW_LIST, GalleryIcon.VIEW_LIST_ACTIVE),
            variant="ghost",
            toggle=True,
            size=(48, 28),  # design px — Button scales internally (no scaled_px)
            parent=self._view_switch_container,
        )
        self._view_switch_list.setObjectName("gallery_toolbar_view_switch_list")
        try:
            self._view_switch.setToolTip(_tr("image_gallery.view_grid", "Grid"))
        except Exception:
            pass
        try:
            self._view_switch_list.setToolTip(_tr("image_gallery.view_list", "List"))
        except Exception:
            pass
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
            apply_domain = getattr(self, "_apply_domain", None)
            if callable(apply_domain):
                apply_domain(str(getattr(self, "_judgment_domain", "algorithms")))
        except Exception:
            pass
        try:
            self._view_switch_container.update()
        except Exception:
            pass
        try:
            self._domain_switch_container.update()
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

    def _tr_text(self, key: str, default: str) -> str:
        """Translate *key* via the injected translator (fail-open to *default*)."""
        tr = getattr(self, "_tr", None)
        if tr is None:
            return default
        try:
            return tr(key, default)
        except Exception:
            return default

    def _sort_display(self, index: int) -> str:
        """Localized option label for *index* (no "Sort:" prefix).

        Indices map 1:1 to ``_sort_items`` (EN canonical machine labels, kept
        as the ``sortChanged`` payload); this only feeds display surfaces
        (button text / width hints / flyout rows), never the emitted value.
        """
        try:
            i = int(index)
        except Exception:
            i = 0
        if not (0 <= i < len(SORT_OPTION_KEYS)):
            i = 0
        return self._tr_text(SORT_OPTION_KEYS[i], SORT_OPTION_DEFAULTS[i])

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

    @property
    def domain_switch(self) -> Button:
        return self._domain_switch

    @property
    def domain_switch_ai(self) -> Button:
        return self._domain_switch_ai

    @property
    def judgment_domain(self) -> str:
        return str(getattr(self, "_judgment_domain", "algorithms"))

    def set_judgment_domain(self, domain: str) -> None:
        """Select the judgment domain programmatically (emits domainChanged on change)."""
        try:
            self._apply_domain(str(domain))  # type: ignore[attr-defined]
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
                self._sort_combo.setText(f"{self._sort_display(index)} ▾")
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
    # Bodies live in ``sort_picker.py`` (package split, plan-gallery-split-
    # 2026-10-17 Part C6); thin delegators keep the method names/signatures.

    def _sort_flyout_ensure(self) -> SimpleOptionsFlyout | None:
        return sort_picker.sort_flyout_ensure(self)

    def _sort_options_for_domain(self) -> list[str]:
        return sort_picker.sort_options_for_domain(self)

    def _on_sort_clicked(self) -> None:
        sort_picker.on_sort_clicked(self)

    def _on_sort_chosen(self, index: int) -> None:
        sort_picker.on_sort_chosen(self, index)

    def retranslate(self, translate: Callable[[str, str], str] | None = None) -> None:
        """Update translatable texts in place.

        Also the toolkit protocol hook (``retranslate(lang)`` via
        ``install_translator``): a non-callable (language string) is ignored and
        the live ``_tr`` re-applies — never overwrite the callable with a str.
        """
        if callable(translate):
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
            self._pick_button.setText(_tr("image_gallery.toolbar.open_folder", "Open Folder…"))
        except Exception:
            pass
        try:
            self._filter_edit.setPlaceholderText(
                _tr("image_gallery.toolbar.filter_placeholder", "Filter by tag / description…")
            )
        except Exception:
            pass
        try:
            self._view_switch.setToolTip(_tr("image_gallery.view_grid", "Grid"))
            self._view_switch_list.setToolTip(_tr("image_gallery.view_list", "List"))
        except Exception:
            pass
        try:
            self._sort_combo.setText(f"{self._sort_display(int(self._sort_index))} ▾")
            set_widths = getattr(self._sort_combo, "set_width_texts", None)
            if callable(set_widths):
                set_widths([f"{self._sort_display(i)} ▾" for i in range(len(self._sort_items))])
        except Exception:
            pass
        try:
            # Icon-only segments: the visible label is the icon; the localized
            # string belongs in the tooltip (setting text clips in the 34px row
            # and put words next to the icons).
            self._domain_switch.setToolTip(
                _tr("image_gallery.domain.algorithms", "Algorithms")
            )
            self._domain_switch_ai.setToolTip(_tr("image_gallery.domain.ai", "AI"))
        except Exception:
            pass
