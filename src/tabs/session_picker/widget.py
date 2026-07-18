"""Home-page style new-session picker."""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QLineF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QVBoxLayout, QWidget
from sli_ui_toolkit.i18n import translatable_callback
from sli_ui_toolkit.ui.widgets.buttons import ButtonRow
from sli_ui_toolkit.widgets import (
    Button,
    ButtonRegion,
    HorizontalSplit,
    Label,
    OverlayScrollArea,
    ThemedWidget,
)

from core.plugin_system.discovery_scan import iter_tab_entry_points
from core.session_blueprints import SessionBlueprint
from tabs.session_picker.geometry import (
    SESSION_PICKER_PAGE_MIN_HEIGHT,
    SESSION_PICKER_PAGE_MIN_WIDTH,
    SESSION_PICKER_WINDOW_MIN_HEIGHT,
    SESSION_PICKER_WINDOW_MIN_WIDTH,
)
from tabs.session_picker.icons import Icon as SessionPickerIcon, get_icon as get_session_picker_icon
from tabs.session_picker.recent.panel import RecentProjectsPanel
from ui.theming import resolve_theme_color

HIDDEN_SESSION_TYPES = frozenset({"session_picker"})


class _SeamlessHorizontalSplit(HorizontalSplit):
    def compute(self, rect: QRectF, regions: list[ButtonRegion]) -> list[QRectF]:
        rects = super().compute(rect, regions)
        for region_rect in rects[1:]:
            region_rect.setLeft(region_rect.left() - 1.0)
        return rects

    def dividers(self, rects: list[QRectF]) -> list[QLineF]:
        return []


class SessionPickerWidget(ThemedWidget, QWidget):
    def __init__(self, parent=None, *, context):
        super().__init__(parent)
        self._context = context
        self._cards_container: QWidget | None = None
        self._cards_layout: QVBoxLayout | None = None
        self._title_label: Label | None = None
        self._subtitle_label: Label | None = None
        self._recent_panel: RecentProjectsPanel | None = None
        self._page_scroll: OverlayScrollArea | None = None
        self._page_content: QWidget | None = None
        self._populated = False
        self._cards_by_type: dict[str, Button] = {}
        self.setObjectName("SessionPickerPage")
        self.setMinimumSize(
            SESSION_PICKER_PAGE_MIN_WIDTH,
            SESSION_PICKER_PAGE_MIN_HEIGHT,
        )
        # CSD translucent windows punch through clear children — keep this page
        # an opaque surface for the whole stack (scroll → content → recent).
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        self._build()

    def window_minimum_size(self) -> tuple[int, int]:
        """Main-window floor while this page is the active workspace content."""
        return (
            SESSION_PICKER_WINDOW_MIN_WIDTH,
            SESSION_PICKER_WINDOW_MIN_HEIGHT,
        )

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        bg = QColor(getattr(self, "_bg_color", QColor(255, 255, 255)))
        if not bg.isValid() or bg.alpha() == 0:
            bg = QColor(255, 255, 255)
        bg.setAlpha(255)
        painter.fillRect(self.rect(), bg)
        painter.end()

    def on_theme_changed(self) -> None:
        self._bg_color = QColor(resolve_theme_color(self._theme_manager, "Window"))
        if not self._bg_color.isValid():
            self._bg_color = QColor(255, 255, 255)
        self._bg_color.setAlpha(255)
        self._sync_opaque_page_fills()
        # Cards store eager QIcons from build time; re-resolve light/dark SVGs.
        # ThemedWidget calls this from __init__ before _populated exists.
        if getattr(self, "_populated", False):
            self.sync_icons()
        super().on_theme_changed()

    @staticmethod
    def _apply_opaque_fill(widget: QWidget | None, color: QColor) -> None:
        if widget is None:
            return
        fill = QColor(color)
        fill.setAlpha(255)
        widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        widget.setAutoFillBackground(True)
        palette = widget.palette()
        palette.setColor(widget.backgroundRole(), fill)
        widget.setPalette(palette)

    def _sync_opaque_page_fills(self) -> None:
        bg = QColor(getattr(self, "_bg_color", QColor(255, 255, 255)))
        bg.setAlpha(255)
        self._apply_opaque_fill(self, bg)
        scroll = getattr(self, "_page_scroll", None)
        if scroll is not None:
            self._apply_opaque_fill(scroll, bg)
            self._apply_opaque_fill(scroll.viewport(), bg)
        self._apply_opaque_fill(getattr(self, "_page_content", None), bg)
        self._apply_opaque_fill(getattr(self, "_cards_container", None), bg)

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = OverlayScrollArea(self)
        # Page fills the CSD content host; a 1-bit viewport mask here punches
        # black wedges into the bottom window corners when the recent shelf
        # grows and the scroll content reflows.
        scroll.set_corner_radius(0)
        outer.addWidget(scroll)
        self._page_scroll = scroll

        content = QWidget()
        scroll.setWidget(content)
        self._page_content = content

        layout = QVBoxLayout(content)
        layout.setContentsMargins(48, 40, 48, 40)
        layout.setSpacing(20)

        self._title_label = Label(
            self._context.tr("title", "Create a workspace"),
            pixel_size=26,
            bold=True,
        )
        layout.addWidget(self._title_label)
        self._subtitle_label = Label(
            self._context.tr("subtitle", "Pick a session type to begin"),
            pixel_size=14,
        )
        layout.addWidget(self._subtitle_label)

        self._cards_container = QWidget()
        self._cards_layout = QVBoxLayout(self._cards_container)
        self._cards_layout.setContentsMargins(0, 0, 0, 0)
        self._cards_layout.setSpacing(10)
        layout.addWidget(self._cards_container)

        self._recent_panel = RecentProjectsPanel(
            self,
            tr=self._context.tr,
            context=self._context,
        )
        layout.addWidget(self._recent_panel)
        layout.addStretch(1)
        self._sync_opaque_page_fills()
        translatable_callback(self, lambda _lang: self._retranslate())

    def set_open_project_handler(self, handler: Callable[[str], None] | None) -> None:
        if self._recent_panel is not None:
            self._recent_panel.set_open_project_handler(handler)

    def refresh_recent(self) -> None:
        if self._recent_panel is not None:
            self._recent_panel.refresh()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        # Create-cards first (changes page height). The recent shelf schedules
        # its own first layout on show (or soft-refreshes if already laid out).
        self.refresh()
        self._sync_opaque_page_fills()
        if self._recent_panel is not None:
            self._recent_panel.on_page_shown()

    def refresh(self) -> None:
        """Build create-cards once from a filesystem scan of tab packages.

        Deferred plugins (e.g. multi_compare) register SessionBlueprints after
        bootstrap, but card buttons must not flicker in later — package names
        under ``tabs/`` are known up front via ``iter_tab_entry_points``.
        """
        if self._populated or self._cards_layout is None:
            return
        blueprints = {
            bp.session_type: bp for bp in self._registered_blueprints()
        }
        for session_type in self._creatable_session_types():
            self._cards_layout.addWidget(
                self._build_card(session_type, blueprints.get(session_type))
            )
        self._populated = True

    def sync_icons(self) -> None:
        """Refresh card icons in place after deferred tabs register / theme change."""
        if not getattr(self, "_populated", False):
            return
        for session_type, card in self._cards_by_type.items():
            icon = self._icon_for_session_type(session_type)
            card.update_region("icon", icon=icon)

    def _retranslate(self) -> None:
        if self._title_label is not None:
            self._title_label.setText(self._context.tr("title", "Create a workspace"))
        if self._subtitle_label is not None:
            self._subtitle_label.setText(
                self._context.tr("subtitle", "Pick a session type to begin")
            )
        # Update create-cards in place. Destroy/rebuild collapses the page
        # layout under WA_OpaquePaintEvent and leaves a CSD see-through hole
        # where the recent shelf used to sit.
        if self._populated:
            self._retranslate_cards()
        self._sync_opaque_page_fills()
        self.update()
        if self._recent_panel is not None:
            # Panel has its own language callback; recover paints after our
            # sibling text updates in case layout still nudged the shelf.
            self._recent_panel.recover_opaque_surface()

    def card_for(self, session_type: str) -> Button | None:
        """Return the live create-card for ``session_type``, building cards if needed."""
        if not self._populated:
            self.refresh()
        return self._cards_by_type.get(session_type)

    def _retranslate_cards(self) -> None:
        blueprints = {
            bp.session_type: bp for bp in self._registered_blueprints()
        }
        for session_type, card in self._cards_by_type.items():
            title = self._label_for(session_type, blueprints.get(session_type))
            description = self._context.tr(
                f"descriptions.{session_type}",
                "",
            )
            rows = [
                ButtonRow(
                    text=title,
                    size=15,
                    weight="bold",
                    h_align=Qt.AlignmentFlag.AlignLeft,
                )
            ]
            if description:
                rows.append(
                    ButtonRow(
                        text=description,
                        size=12,
                        h_align=Qt.AlignmentFlag.AlignLeft,
                    )
                )
            card.update_region("text", rows=rows)

    def _clear_cards(self) -> None:
        if self._cards_layout is None:
            return
        self._cards_by_type.clear()
        while self._cards_layout.count():
            item = self._cards_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()

    def _icon_for_session_type(self, session_type: str):
        try:
            icon = self._context.call_service("get_tab_icon", session_type)
        except RuntimeError:
            icon = None
        if icon is not None and not icon.isNull():
            return icon
        return get_session_picker_icon(SessionPickerIcon.ADD)

    def _build_card(
        self, session_type: str, blueprint: SessionBlueprint | None
    ) -> Button:
        title = self._label_for(session_type, blueprint)
        description = self._context.tr(
            f"descriptions.{session_type}",
            "",
        )
        icon = self._icon_for_session_type(session_type)

        rows = [
            ButtonRow(
                text=title,
                size=15,
                weight="bold",
                h_align=Qt.AlignmentFlag.AlignLeft,
            )
        ]
        if description:
            rows.append(
                ButtonRow(
                    text=description,
                    size=12,
                    h_align=Qt.AlignmentFlag.AlignLeft,
                )
            )

        card = Button(
            regions=[
                ButtonRegion(
                    id="icon",
                    icon=icon,
                    icon_size_px=32,
                    weight=1.0,
                    group="card",
                    corner_radii=(10, 0, 0, 10),
                ),
                ButtonRegion(
                    id="text",
                    rows=rows,
                    weight=6.0,
                    group="card",
                    corner_radii=(0, 10, 10, 0),
                ),
            ],
            split=_SeamlessHorizontalSplit(),
            variant="default",
            size=(0, 76),
            corner_radius=10,
            parent=self._cards_container,
        )
        card.regionClicked.connect(lambda _id, st=session_type: self._create(st))
        self._cards_by_type[session_type] = card
        return card

    def _creatable_session_types(self) -> tuple[str, ...]:
        """Session types offered on the picker, without waiting for plugins.

        Package name under ``tabs/`` matches ``TabContract.session_type`` for
        every shipped tab. Blueprints registered outside that convention are
        appended so dynamic session plugins still appear.
        """
        seen: list[str] = []
        for entry in iter_tab_entry_points():
            name = entry.package_name
            if name in HIDDEN_SESSION_TYPES or name in seen:
                continue
            seen.append(name)
        for blueprint in self._registered_blueprints():
            name = blueprint.session_type
            if name in HIDDEN_SESSION_TYPES or name in seen:
                continue
            seen.append(name)
        return tuple(seen)

    def _registered_blueprints(self) -> list[SessionBlueprint]:
        try:
            blueprints = self._context.call_service("list_session_blueprints")
        except RuntimeError:
            return []
        return [
            bp
            for bp in blueprints
            if bp.session_type not in HIDDEN_SESSION_TYPES
        ]

    def _label_for(
        self, session_type: str, blueprint: SessionBlueprint | None
    ) -> str:
        key = f"types.{session_type}"
        fallback = (
            (blueprint.resolved_title() if blueprint is not None else None)
            or session_type.replace("_", " ").title()
        )
        return self._context.tr(key, fallback)

    def _create(self, session_type: str) -> None:
        picker_session = self._context.get_active_session()
        self._context.call_service("create_workspace_session", session_type, True)
        if picker_session is not None:
            self._context.call_service("close_workspace_session", picker_session.id)
