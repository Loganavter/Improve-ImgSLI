"""Settings typography — three font groups for the settings dialog.

Every settings page (built-in ``plugins/settings/pages/*`` and tab-owned
extras/sections) sizes its text through these groups instead of hardcoded
``pixel_size=`` literals, so the whole dialog scales as one system:

- ``TITLE`` (18px) — group/fieldset titles (``CustomGroupWidget`` captions).
- ``BODY`` (16px) — primary content: checkboxes, radios, combos, line edits,
  spins, sliders' labels and primary row labels.
- ``CAPTION`` (14px) — secondary text: restart hints, warnings, footnotes.

Toolkit-owned chrome (sidebar rows, search field, ``Button`` family, dialog
action bar) is intentionally out of scope — those widgets own their sizing
via the painter pipeline.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sli_ui_toolkit.ui.managers.ui_font import apply_ui_font
from sli_ui_toolkit.widgets import CustomGroupWidget, Label
from ui.actions.search_index import PROP_GROUP

if TYPE_CHECKING:
    from PySide6.QtGui import QFont

#: Group/fieldset titles.
SETTINGS_TITLE_PX = 18
#: Primary content: checkboxes, radios, combos, edits, spins, row labels.
SETTINGS_BODY_PX = 16
#: Secondary text: hints, warnings, footnotes.
SETTINGS_CAPTION_PX = 14


def apply_settings_title(widget: CustomGroupWidget) -> QFont:
    """Pin a group widget's title to the ``TITLE`` group.

    ``CustomGroupWidget`` paints its caption from ``widget.font()``, so
    setting the widget font sizes the title (the painter already forces
    bold).
    """
    return apply_ui_font(widget, pixel_size=SETTINGS_TITLE_PX)


def apply_settings_body(widget) -> QFont:
    """Pin a primary control to the ``BODY`` group."""
    return apply_ui_font(widget, pixel_size=SETTINGS_BODY_PX)


def apply_settings_caption(widget) -> QFont:
    """Pin a secondary control to the ``CAPTION`` group."""
    return apply_ui_font(widget, pixel_size=SETTINGS_CAPTION_PX)


def settings_group(dialog, search_group: object) -> SettingsGroupWidget:
    """Build a settings-styled group widget from a settings ``SearchGroup``.

    Same title + Find Action ``PROP_GROUP`` tag as
    ``search_group.widget(dialog)``, but as a :class:`SettingsGroupWidget`
    — the single entry point every settings page uses for its fieldsets.
    """
    widget = SettingsGroupWidget(search_group.title(dialog))  # type: ignore[attr-defined]
    widget.setProperty(PROP_GROUP, search_group.title_key)  # type: ignore[attr-defined]
    return widget


class SettingsGroupWidget(CustomGroupWidget):
    """Settings fieldset: ``TITLE`` caption, near-flush side insets.

    The toolkit group keeps 12px left/right content insets; settings rows
    manage their own horizontal rhythm, so the group keeps only a 2px
    guard — exactly enough that opaque children (``QLineEdit`` background,
    ``Button`` washes) never paint over the 1px border, close enough to
    read as edge-aligned. Vertical insets (title clearance, bottom) are
    untouched. The trim re-runs inside the toolkit's own metrics pass, so
    it survives UiScale and title changes.
    """

    #: Side guard kept so opaque children clear the 1px group border.
    SIDE_GUARD_PX = 10

    def __init__(self, title_text: str = "", parent=None, **kwargs) -> None:
        super().__init__(title_text, parent, **kwargs)
        apply_settings_title(self)

    def _apply_layout_metrics(self) -> None:
        super()._apply_layout_metrics()
        lay = self.layout()
        if lay is not None:
            margins = lay.contentsMargins()
            lay.setContentsMargins(
                self.SIDE_GUARD_PX, margins.top(),
                self.SIDE_GUARD_PX, margins.bottom(),
            )


def settings_body_label(text: str, parent=None, **kwargs) -> Label:
    """Primary row label in the ``BODY`` group."""
    return Label(text, pixel_size=SETTINGS_BODY_PX, parent=parent, **kwargs)


def settings_caption_label(text: str, parent=None, **kwargs) -> Label:
    """Secondary hint/warning/footnote label in the ``CAPTION`` group."""
    return Label(text, pixel_size=SETTINGS_CAPTION_PX, parent=parent, **kwargs)
