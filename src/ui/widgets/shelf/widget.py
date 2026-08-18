"""Self-assembling shelf widget, shared by the Session Picker Recent shelf
and the color picker's recent-colors shelf.

The shelf is chrome + structure; consumers only decide what goes in:

- the header host — a title (``set_title``) plus arbitrary control buttons
  (``add_header_widget``);
- the content host — arbitrary cards/buttons (``add_content_widget``).

Chrome (moved here from ``tabs.session_picker.recent.shelf_chrome``):

- the host surface fill (``surface_token`` — ``Window`` on the Session
  Picker page, ``dialog.background`` inside the color picker dialog) and
- a rounded shelf panel derived from that surface by the same lighten/darken
  ratios the Session Picker shelf uses.

Both layers repaint on theme changes; ``colors()`` exposes all derived
colors in one dict so consumers that fill content hosts opaquely (translucent
CSD windows must never show through) don't need to learn multiple accessors.
"""

from __future__ import annotations

from sli_ui_toolkit.ui.inspector.spec import InspectSpec, SpecField  # noqa: E402

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from sli_ui_toolkit.managers import scaled_px
from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.widgets import Label

from ui.theming import resolve_theme_color

# Rounded-corner radius (design px) of the shelf panel, same as the Session
# Picker shelf.
PANEL_RADIUS = 12.0

# Root layout margins/spacing (design px) — the tinted panel frame around the
# shelf content. Shared by every shelf consumer so the composition (frame
# width, header/content gap) stays identical everywhere.
SHELF_MARGIN_LEFT = 16
SHELF_MARGIN_TOP = 14
SHELF_MARGIN_RIGHT = 16
SHELF_MARGIN_BOTTOM = 14
SHELF_SPACING = 10


class OpaqueFillHost(QWidget):
    """Content well that paints its fill explicitly (not palette autofill).

    Bare ``setPalette`` + ``autoFillBackground`` is unreliable under
    translucent CSD parents (see ``docs/dev/KNOWN_BUGS.md``). Do **not** set
    ``WA_OpaquePaintEvent`` here — that flag plus a skipped/disabled update
    punches see-through holes through the window chrome.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._fill = QColor(255, 255, 255)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setAutoFillBackground(False)

    def set_fill_color(self, color: QColor) -> None:
        fill = QColor(color)
        fill.setAlpha(255)
        # QScrollArea.setWidget can flip autoFillBackground back on — pin it off.
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setAutoFillBackground(False)
        if self._fill == fill:
            self.update()
            return
        self._fill = fill
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(event.rect(), self._fill)
        painter.end()


def apply_opaque_widget_fill(widget: QWidget | None, color: QColor) -> None:
    """Opaque fill on a widget, preferring explicit paint hosts."""
    if widget is None:
        return
    fill = QColor(color)
    fill.setAlpha(255)
    set_fill = getattr(widget, "set_fill_color", None)
    if callable(set_fill):
        set_fill(fill)
        return
    widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
    widget.setAutoFillBackground(True)
    palette = widget.palette()
    palette.setColor(widget.backgroundRole(), fill)
    widget.setPalette(palette)


class ShelfWidget(QWidget):
    """Shelf chrome + header/content hosts; consumers assemble the contents.

    Paints, in order: the opaque host surface, then the rounded panel
    derived from it. The header host (title + trailing controls) and the
    content host (cards/buttons) are plain transparent children so the
    panel shows through everything inside the shelf.
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        surface_token: str = "Window",
        content_well: bool = False,
    ) -> None:
        """``content_well=True`` paints the content host opaquely with the
        host surface color — the "two backings" composition of the Session
        Picker shelf (tinted panel frame + surface-colored content well under
        the cards). The header stays on the tint, like the shelf title bar.
        """
        super().__init__(parent)
        self._surface_token = surface_token
        self._content_well = bool(content_well)
        self._theme_manager = ThemeManager.get_instance()
        self._theme_manager.theme_changed.connect(self._on_shelf_theme_changed)

        self._shelf_surface = QColor(255, 255, 255)
        self._shelf_panel = QColor(255, 255, 255)
        self._shelf_title_label: Label | None = None

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setAutoFillBackground(False)

        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(
            scaled_px(SHELF_MARGIN_LEFT),
            scaled_px(SHELF_MARGIN_TOP),
            scaled_px(SHELF_MARGIN_RIGHT),
            scaled_px(SHELF_MARGIN_BOTTOM),
        )
        self._root.setSpacing(scaled_px(SHELF_SPACING))

        self._header_host = QWidget(self)
        self._header_host.setAutoFillBackground(False)
        self._header_layout = QHBoxLayout(self._header_host)
        self._header_layout.setContentsMargins(0, 0, 0, 0)
        self._header_layout.setSpacing(scaled_px(6))
        self._header_stretch_added = False
        self._root.addWidget(self._header_host)

        self._content_host = QWidget(self)
        self._content_host.setAutoFillBackground(False)
        self._content_layout = QVBoxLayout(self._content_host)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(0)
        self._root.addWidget(self._content_host)

        self._update_shelf_chrome()
        self._apply_content_well_fill()

    # ----- structure -------------------------------------------------------

    def set_title(self, text: str) -> None:
        """Create or update the shelf title label (bold, 16 px)."""
        if self._shelf_title_label is None:
            self._shelf_title_label = Label(
                text, self._header_host, pixel_size=16, bold=True
            )
            self._header_layout.insertWidget(0, self._shelf_title_label)
        else:
            self._shelf_title_label.setText(text)

    def title_label(self) -> Label | None:
        return self._shelf_title_label

    def add_header_widget(self, widget: QWidget) -> None:
        """Append a control button (or control cluster) to the header row.

        Controls sit right-aligned after the title.
        """
        if not self._header_stretch_added:
            self._header_layout.addStretch(1)
            self._header_stretch_added = True
        self._header_layout.addWidget(widget)

    def add_content_widget(self, widget: QWidget) -> None:
        """Append a card/button (or content block) to the shelf content."""
        self._content_layout.addWidget(widget)

    def content_host(self) -> QWidget:
        return self._content_host

    # ----- chrome ----------------------------------------------------------

    def _surface_color(self) -> QColor:
        color = QColor(resolve_theme_color(self._theme_manager, self._surface_token))
        if not color.isValid() or color.alpha() == 0:
            color = QColor(255, 255, 255)
        color.setAlpha(255)
        return color

    def _update_shelf_chrome(self) -> None:
        """Re-derive the two backing layers from the current theme surface."""
        surface = self._surface_color()
        self._shelf_surface = QColor(surface)
        self._shelf_surface.setAlpha(255)
        panel = QColor(surface)
        if surface.lightness() > 140:
            panel = panel.darker(106)
        else:
            panel = panel.lighter(118)
        panel.setAlpha(255)
        self._shelf_panel = panel

    def colors(self) -> dict[str, object]:
        """All shelf-derived colors in one dict.

        Keys:

        - ``panel`` — opaque rounded-panel fill (QColor)
        - ``content`` — opaque host-surface fill (QColor)
        - ``header_button`` — opaque chip fill for header buttons (QColor)
        - ``empty_zone`` — dict with ``border``, ``title``, ``hint``, ``fill``
          (QColor each) for an empty-shelf drop zone
        """
        panel = QColor(self._shelf_panel)
        content = QColor(self._shelf_surface)

        header_button = QColor(panel)
        header_button.setAlpha(255)
        if panel.lightness() > 140:
            header_button = header_button.lighter(108)
        else:
            header_button = header_button.darker(118)
        header_button.setAlpha(255)

        title = QColor(resolve_theme_color(self._theme_manager, "WindowText"))
        hint = QColor(title)
        hint.setAlpha(170)
        if panel.lightness() > 140:
            border = panel.darker(130)
            fill = panel.darker(103)
        else:
            border = panel.lighter(150)
            fill = panel.lighter(108)
        fill.setAlpha(255)

        return {
            "panel": panel,
            "content": content,
            "header_button": header_button,
            "empty_zone": {"border": border, "title": title, "hint": hint, "fill": fill},
        }

    # ----- backward-compatible accessors (delegate to colors()) -------------

    def panel_bg(self) -> QColor:
        """Opaque rounded-panel fill. Prefer ``colors()["panel"]``."""
        return QColor(self._shelf_panel)

    def content_bg(self) -> QColor:
        """Opaque host-surface fill. Prefer ``colors()["content"]``."""
        return QColor(self._shelf_surface)

    def header_button_bg(self) -> QColor:
        """Opaque chip fill for header buttons. Prefer ``colors()["header_button"]``."""
        c = self.colors()
        return QColor(c["header_button"])

    def empty_zone_colors(self) -> dict[str, QColor]:
        """Empty-zone palette. Prefer ``colors()["empty_zone"]``."""
        return dict(self.colors()["empty_zone"])

    def update_shelf_chrome(self) -> None:
        """Re-derive chrome from theme. Prefer letting the shelf handle this
        automatically on theme changes."""
        self._update_shelf_chrome()

    def _apply_content_well_fill(self) -> None:
        """Opaque surface fill under the content (the "well" backing)."""
        if self._content_well:
            apply_opaque_widget_fill(self._content_host, self.content_bg())

    def _on_shelf_theme_changed(self) -> None:
        self._update_shelf_chrome()
        self._apply_content_well_fill()
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillRect(event.rect(), self._shelf_surface)
        path = QPainterPath()
        rect = QRectF(self.rect()).adjusted(0, 0, -1, -1)
        path.addRoundedRect(rect, PANEL_RADIUS, PANEL_RADIUS)
        painter.fillPath(path, self._shelf_panel)
        painter.end()


__all__ = [
    "OpaqueFillHost",
    "PANEL_RADIUS",
    "SHELF_MARGIN_BOTTOM",
    "SHELF_MARGIN_LEFT",
    "SHELF_MARGIN_RIGHT",
    "SHELF_MARGIN_TOP",
    "SHELF_SPACING",
    "ShelfWidget",
    "apply_opaque_widget_fill",
]

ShelfWidget.inspect_spec = InspectSpec(
    family="ShelfWidget",
    state=(
        SpecField(
            "title",
            lambda w: w.title_label().text() if w.title_label() else "",
        ),
        SpecField("content_well", "_content_well", private=True),
        SpecField("surface_token", "_surface_token", private=True),
    ),
    docs="docs/dev/widgets/shelf.md",
)

from sli_ui_toolkit.ui.widget_descriptor import InspectSection, WidgetDescriptor
ShelfWidget.widget_descriptor = WidgetDescriptor(
    family=ShelfWidget.inspect_spec.family,
    inspect=InspectSection(
        config=getattr(ShelfWidget.inspect_spec, 'config', ()),
        state=ShelfWidget.inspect_spec.state,
        token_family=getattr(ShelfWidget.inspect_spec, 'token_family', ()),
        regions=getattr(ShelfWidget.inspect_spec, 'regions', False),
        layers=getattr(ShelfWidget.inspect_spec, 'layers', False),
        docs=getattr(ShelfWidget.inspect_spec, 'docs', ''),
        preview_seed=getattr(ShelfWidget.inspect_spec, 'preview_seed', None),
        apply_config_refresh=getattr(ShelfWidget.inspect_spec, 'apply_config_refresh', None),
    ),
)