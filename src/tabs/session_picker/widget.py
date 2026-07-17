"""Home-page style new-session picker."""

from __future__ import annotations

from PySide6.QtCore import QLineF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from sli_ui_toolkit.i18n import translatable_callback
from sli_ui_toolkit.ui.widgets.buttons import ButtonRow
from sli_ui_toolkit.widgets import (
    Button,
    ButtonRegion,
    DropZoneLabel,
    HorizontalSplit,
    Label,
    OverlayScrollArea,
    ThemedWidget,
)

from core.plugin_system.discovery_scan import iter_tab_entry_points
from core.session_blueprints import SessionBlueprint
from tabs.session_picker.icons import Icon as SessionPickerIcon, get_icon as get_session_picker_icon
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
        self._drop_zone: DropZoneLabel | None = None
        self._recent_title_label: Label | None = None
        self._recent_badge_label: Label | None = None
        self._recent_placeholder_label: Label | None = None
        self._populated = False
        self._cards_by_type: dict[str, Button] = {}
        self.setObjectName("SessionPickerPage")
        self._build()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), self._bg_color)
        painter.end()

    def on_theme_changed(self) -> None:
        self._bg_color = QColor(resolve_theme_color(self._theme_manager, "Window"))
        # Cards store eager QIcons from build time; re-resolve light/dark SVGs.
        # ThemedWidget calls this from __init__ before _populated exists.
        if getattr(self, "_populated", False):
            self.sync_icons()
        super().on_theme_changed()

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = OverlayScrollArea(self)
        outer.addWidget(scroll)

        content = QWidget()
        scroll.setWidget(content)

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

        self._drop_zone = DropZoneLabel(
            self._context.tr(
                "drop_zone",
                "Drop image files here to start a comparison",
            )
        )
        self._drop_zone.file_dropped.connect(self._on_file_dropped)
        layout.addWidget(self._drop_zone)

        layout.addLayout(self._build_recent_section())
        layout.addStretch(1)
        translatable_callback(self, lambda _lang: self._retranslate())

    def _build_recent_section(self) -> QVBoxLayout:
        col = QVBoxLayout()
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(4)

        header = QHBoxLayout()
        header.setSpacing(10)
        self._recent_title_label = Label(
            self._context.tr("recent.title", "Continue"),
            pixel_size=16,
            bold=True,
        )
        header.addWidget(self._recent_title_label)
        self._recent_badge_label = Label(
            self._context.tr("recent.badge", "In development"),
            pixel_size=11,
            bold=True,
            color_token="accent",
        )
        header.addWidget(self._recent_badge_label)
        header.addStretch(1)
        col.addLayout(header)

        self._recent_placeholder_label = Label(
            self._context.tr(
                "recent.placeholder",
                "Recent workspaces will appear here once this feature lands.",
            ),
            pixel_size=12,
            color_token="dialog.text",
        )
        col.addWidget(self._recent_placeholder_label)
        return col

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self.refresh()

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
        if self._drop_zone is not None:
            self._drop_zone.setText(
                self._context.tr(
                    "drop_zone",
                    "Drop image files here to start a comparison",
                )
            )
        if self._recent_title_label is not None:
            self._recent_title_label.setText(
                self._context.tr("recent.title", "Continue")
            )
        if self._recent_badge_label is not None:
            self._recent_badge_label.setText(
                self._context.tr("recent.badge", "In development")
            )
        if self._recent_placeholder_label is not None:
            self._recent_placeholder_label.setText(
                self._context.tr(
                    "recent.placeholder",
                    "Recent workspaces will appear here once this feature lands.",
                )
            )
        if self._populated:
            self._clear_cards()
            self._populated = False
            self.refresh()

    def card_for(self, session_type: str) -> Button | None:
        """Return the live create-card for ``session_type``, building cards if needed."""
        if not self._populated:
            self.refresh()
        return self._cards_by_type.get(session_type)

    def _clear_cards(self) -> None:
        if self._cards_layout is None:
            return
        self._cards_by_type.clear()
        while self._cards_layout.count():
            item = self._cards_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
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

    def _on_file_dropped(self, _path: str) -> None:
        self._create("image_compare")
