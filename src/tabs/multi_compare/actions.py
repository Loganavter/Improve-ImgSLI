"""Register multi_compare toolbar actions into the host action catalog."""

from __future__ import annotations

from dataclasses import dataclass

from core.actions.types import ActionDescriptor, ActionTarget
from ui.actions.keymap import KeymapDefaultEntry
from ui.actions.registry import ActionRegistry, get_action_registry

OWNER = "multi_compare"

_BC_TOOLBAR = "multi_compare.action.breadcrumb.toolbar"
_BC_DIVIDER = "multi_compare.action.breadcrumb.divider"
_BC_LABELS = "multi_compare.action.breadcrumb.labels"
_BC_EXPORT = "multi_compare.action.breadcrumb.export"
_BC_SESSION = "multi_compare.action.breadcrumb.session"

_TOPIC_HELP: dict[str, str] = {
    "session": "file_management",
    "labels": "multi_compare",
    "divider": "multi_compare",
    "export": "multi_compare",
}


@dataclass(frozen=True, slots=True)
class _McAction:
    action_id: str
    attr: str
    host: str  # toolbar | footer
    label_key: str
    description_key: str | None
    breadcrumb: tuple[str, ...]
    topic: str
    kind: str = "click"
    shortcut: str | None = None


_SPECS: tuple[_McAction, ...] = (
    _McAction(
        "multi_compare.add_images",
        "btn_add",
        "toolbar",
        "multi_compare.action.add_images",
        "multi_compare.action.add_images_desc",
        (_BC_TOOLBAR, _BC_SESSION),
        "session",
        shortcut="Ctrl+O",
    ),
    _McAction(
        "multi_compare.divider.visible",
        "btn_divider_visible",
        "toolbar",
        "multi_compare.action.divider_visible",
        "tooltip.toggle_divider_visibility",
        (_BC_TOOLBAR, _BC_DIVIDER),
        "divider",
        kind="toggle",
        shortcut="D",
    ),
    _McAction(
        "multi_compare.divider.color",
        "btn_divider_color",
        "toolbar",
        "multi_compare.action.divider_color",
        "tooltip.divider_color",
        (_BC_TOOLBAR, _BC_DIVIDER),
        "divider",
    ),
    _McAction(
        "multi_compare.divider.width",
        "btn_divider_width",
        "toolbar",
        "multi_compare.action.divider_width",
        "multi_compare.action.divider_width_desc",
        (_BC_TOOLBAR, _BC_DIVIDER),
        "divider",
    ),
    _McAction(
        "multi_compare.text_settings",
        "btn_text_settings",
        "toolbar",
        "multi_compare.action.text_settings",
        "multi_compare.action.text_settings_desc",
        (_BC_TOOLBAR, _BC_LABELS),
        "labels",
    ),
    _McAction(
        "multi_compare.quick_save",
        "btn_quick_save",
        "toolbar",
        "multi_compare.action.quick_save",
        "tooltip.quick_save_image",
        (_BC_TOOLBAR, _BC_EXPORT),
        "export",
        shortcut="Ctrl+S",
    ),
    _McAction(
        "multi_compare.save",
        "btn_save",
        "footer",
        "multi_compare.action.save",
        "tooltip.save_result",
        (_BC_TOOLBAR, _BC_EXPORT),
        "export",
        shortcut=None,
    ),
)


def _toggle_button(button) -> None:
    if button is None:
        return
    if hasattr(button, "isChecked") and hasattr(button, "setChecked"):
        button.setChecked(not bool(button.isChecked()))
        return
    _click_button(button)


def _click_button(button) -> None:
    if button is None:
        return
    click = getattr(button, "click", None)
    if callable(click):
        click()
        return
    activate = getattr(button, "_activate_via_keyboard", None)
    if callable(activate):
        activate()
        return
    clicked = getattr(button, "clicked", None)
    if clicked is not None and hasattr(clicked, "emit"):
        clicked.emit()


def register_multi_compare_actions(
    *,
    toolbar,
    registry: ActionRegistry | None = None,
    footer=None,
) -> None:
    """Register MC toolbar (and footer) actions with explicit widget targets."""
    reg = registry if registry is not None else get_action_registry()
    reg.unregister_owner(OWNER)
    if toolbar is None:
        return

    hosts = {"toolbar": toolbar, "footer": footer}
    for spec in _SPECS:
        host = hosts.get(spec.host)
        if host is None:
            continue
        button = getattr(host, spec.attr, None)
        if button is None:
            continue
        if spec.kind == "toggle":
            run = lambda b=button: _toggle_button(b)
        else:
            run = lambda b=button: _click_button(b)
        reg.register(
            ActionDescriptor(
                action_id=spec.action_id,
                label_key=spec.label_key,
                description_key=spec.description_key,
                breadcrumb=spec.breadcrumb,
                owner_tab=OWNER,
                topic=spec.topic,
                shortcut=spec.shortcut,
                help_page=_TOPIC_HELP.get(spec.topic),
                run=run,
                target=ActionTarget(widget=button),
            )
        )

    _contribute_font_settings_flyout(toolbar, reg)


def _contribute_font_settings_flyout(toolbar, reg: ActionRegistry) -> None:
    from ui.actions.flyout_contribute import contribute_flyout_search_actions
    from ui.widgets.font_settings_search import font_settings_search

    parent_widget = getattr(toolbar, "parentWidget", None)
    widget = parent_widget() if callable(parent_widget) else None
    flyout = getattr(widget, "font_settings_flyout", None) if widget is not None else None
    show = getattr(widget, "show_font_settings_flyout", None) if widget is not None else None
    if flyout is None or not callable(show):
        return
    title_key = "multi_compare.action.text_settings"
    contribute_flyout_search_actions(
        flyout,
        index=font_settings_search(title_key, include_placement=False),
        prefix="multi_compare.font_settings.",
        owner_tab=OWNER,
        topic="labels",
        breadcrumb=(_BC_TOOLBAR, _BC_LABELS),
        show_flyout=show,
        help_page=_TOPIC_HELP.get("labels"),
        registry=reg,
    )


def contribute_keymap_defaults(registry) -> None:
    for spec in _SPECS:
        registry.register(
            KeymapDefaultEntry(
                action_id=spec.action_id,
                label_key=spec.label_key,
                default_shortcut=spec.shortcut,
                owner_tab=OWNER,
                breadcrumb=spec.breadcrumb,
                description_key=spec.description_key,
            )
        )
