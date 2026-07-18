"""Hub page: Session Picker-style cards for help children."""

from __future__ import annotations

from PySide6.QtCore import QLineF, QRectF, Qt, Signal
from PySide6.QtWidgets import QSizePolicy, QVBoxLayout, QWidget

from plugins.help.icons import resolve_help_icon
from plugins.help.labels import node_description, node_title
from plugins.help.tree import HelpNode
from sli_ui_toolkit.ui.widgets.buttons import ButtonRow
from sli_ui_toolkit.ui.widgets.helpers import unregister_hover_widget
from sli_ui_toolkit.widgets import Button, ButtonRegion, HorizontalSplit, Label


class _SeamlessHorizontalSplit(HorizontalSplit):
    def compute(self, rect: QRectF, regions: list[ButtonRegion]) -> list[QRectF]:
        rects = super().compute(rect, regions)
        for region_rect in rects[1:]:
            region_rect.setLeft(region_rect.left() - 1.0)
        return rects

    def dividers(self, rects: list[QRectF]) -> list[QLineF]:
        return []


def _dispose_hover_widget(widget: QWidget) -> None:
    """Detach a hover-tracked control before ``deleteLater`` to avoid UAF."""
    try:
        unregister_hover_widget(widget)
    except Exception:
        pass
    widget.hide()
    widget.setParent(None)
    widget.deleteLater()


class HelpHubPage(QWidget):
    """Card grid for hub children."""

    childActivated = Signal(str)  # node_id

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("HelpHubPage")
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        self._language = "en"
        self._open_topic_label = "Open topic"
        self._icon_resolvers: tuple = ()
        self._hub_id: str | None = None
        self._child_ids: tuple[str, ...] = ()
        self._cards_by_id: dict[str, Button] = {}
        self._icon_by_id: dict[str, str | None] = {}
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(16, 12, 16, 16)
        self._layout.setSpacing(12)
        self._title = Label("", pixel_size=22, bold=True, parent=self)
        self._subtitle = Label(
            "",
            pixel_size=13,
            word_wrap=True,
            color_token="list_item.text.rating",
            parent=self,
        )
        self._layout.addWidget(self._title)
        self._layout.addWidget(self._subtitle)
        self._cards = QVBoxLayout()
        self._cards.setSpacing(10)
        self._layout.addLayout(self._cards)
        self._layout.addStretch(1)

    def set_language(self, language: str, *, open_topic_label: str) -> None:
        if language != self._language or open_topic_label != self._open_topic_label:
            # Force card rebuild so region text picks up the new locale.
            self._hub_id = None
        self._language = language
        self._open_topic_label = open_topic_label

    def set_icon_resolvers(self, resolvers: tuple) -> None:
        if resolvers != self._icon_resolvers:
            self._hub_id = None
        self._icon_resolvers = resolvers

    def set_hub(self, hub: HelpNode, children: tuple[HelpNode, ...]) -> None:
        child_ids = tuple(child.node_id for child in children)
        same_structure = (
            self._hub_id == hub.node_id and self._child_ids == child_ids
        )
        self._title.setText(node_title(hub, self._language))
        self._subtitle.setText(node_description(hub, self._language))
        if same_structure and self._cards.count() == len(children):
            # Titles/descriptions already refreshed; keep live Buttons so a
            # hover/click rebuild cannot delete the button under the cursor.
            return
        self._hub_id = hub.node_id
        self._child_ids = child_ids
        self._clear_cards()
        for child in children:
            card = self._build_card(child)
            self._cards_by_id[child.node_id] = card
            self._icon_by_id[child.node_id] = child.icon
            self._cards.addWidget(card)

    def sync_icons(self) -> None:
        """Re-resolve card icons after theme change (eager QIcons freeze theme)."""
        for node_id, card in self._cards_by_id.items():
            icon = resolve_help_icon(
                self._icon_by_id.get(node_id),
                resolvers=self._icon_resolvers,
            )
            card.update_region("icon", icon=icon)

    def _clear_cards(self) -> None:
        self._cards_by_id.clear()
        self._icon_by_id.clear()
        while self._cards.count():
            item = self._cards.takeAt(0)
            widget = item.widget()
            if widget is not None:
                _dispose_hover_widget(widget)

    def _build_card(self, node: HelpNode) -> Button:
        title = node_title(node, self._language)
        description = node_description(node, self._language)
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
        elif node.kind == "page":
            rows.append(
                ButtonRow(
                    text=self._open_topic_label,
                    size=12,
                    h_align=Qt.AlignmentFlag.AlignLeft,
                )
            )

        icon = resolve_help_icon(node.icon, resolvers=self._icon_resolvers)
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
            parent=self,
        )
        card.regionClicked.connect(
            lambda _id, nid=node.node_id: self.childActivated.emit(nid)
        )
        return card
