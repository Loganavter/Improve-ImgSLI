"""Contribute functions and main registration for image_compare actions."""

from __future__ import annotations

from collections.abc import Callable

from core.actions.types import ActionDescriptor, ActionTarget
from tabs.image_compare.actions._common import (
    _BC_ANALYSIS,
    _BC_LABELS,
    _BC_MAGNIFIER,
    _BC_TOOLBAR,
    _CHANNEL_OPTION_SPECS,
    _DIFF_OPTION_SPECS,
    _INTERP_OPTION_SPECS,
    _MAGNIFIER_COLOR_BUTTON_ATTRS,
    _MAGNIFIER_COLOR_OPTION_SPECS,
    _MAGNIFIER_SLIDER_SPECS,
    _MAGNIFIER_VISIBILITY_SLOTS,
    _NAME_EDIT_SPECS,
    _PICKER_CYCLE,
    _SPECS,
    _WidgetAction,
    _click_button,
    _help_for,
    _short_click_button,
    _toggle_button,
    OWNER,
)
from ui.actions.registry import ActionRegistry, get_action_registry


def register_image_compare_actions(
    *,
    widget,
    presenter,
    registry: ActionRegistry | None = None,
    quick_save: Callable[[], None] | None = None,
) -> None:
    """Register IC toolbar actions with explicit widget targets.

    Call after toolbar signal wiring so clicks/toggles reuse live handlers.
    Replaces any previous ``image_compare`` contributions.
    ``quick_save`` is accepted for back-compat but ignored — the button's
    connected click handler is the source of truth.
    """
    _ = presenter
    _ = quick_save
    reg = registry if registry is not None else get_action_registry()
    reg.unregister_owner(OWNER)

    specs: list[ActionDescriptor] = []
    for spec in _SPECS:
        button = getattr(widget, spec.attr, None)
        if button is None:
            continue
        picker_attr = _PICKER_CYCLE.get(spec.attr)
        picker = getattr(widget, picker_attr, None) if picker_attr else None
        if picker is not None and hasattr(picker, "cycle_next"):
            run: Callable[[], None] = lambda p=picker: p.cycle_next()  # type: ignore[misc]  # picker is dynamic
        elif spec.kind == "toggle":
            run = lambda b=button: _toggle_button(b)  # type: ignore[misc]  # button is dynamic
        elif spec.kind == "short_click":
            run = lambda b=button: _short_click_button(b)  # type: ignore[misc]
        else:
            run = lambda b=button: _click_button(b)  # type: ignore[misc]

        specs.append(
            ActionDescriptor(
                action_id=spec.action_id,
                label_key=spec.label_key,
                description_key=spec.description_key,
                breadcrumb=spec.breadcrumb,
                owner_tab=OWNER,
                topic=spec.topic,
                shortcut=spec.shortcut,
                help_page=_help_for(spec.topic, spec.help_page),
                search_keys=spec.search_keys,
                search_terms=spec.search_terms,
                run=run,
                target=ActionTarget(widget=button),
            )
        )

    for action in specs:
        reg.register(action)

    _contribute_mode_picker_options(widget, reg)
    _contribute_interpolation_options(reg)
    _contribute_name_edit_actions(widget, reg)
    _contribute_font_settings_flyout(reg)
    _contribute_magnifier_sliders(widget, reg)
    _contribute_magnifier_visibility_flyout(reg)
    _contribute_magnifier_color_options(widget, reg)


def _contribute_mode_picker_options(widget, reg: ActionRegistry) -> None:
    from ui.actions.flyout_contribute import (
        SimpleOptionAction,
        contribute_simple_options_actions,
    )

    analysis_bc = (_BC_TOOLBAR, _BC_ANALYSIS)
    help_page = _help_for("analysis")

    diff_picker = getattr(widget, "btn_diff_mode_picker", None)
    if diff_picker is not None:
        contribute_simple_options_actions(
            diff_picker,
            options=tuple(
                SimpleOptionAction(oid, label, data, search_terms=terms)
                for oid, label, data, terms in _DIFF_OPTION_SPECS
            ),
            prefix="image_compare.diff_mode.",
            owner_tab=OWNER,
            topic="analysis",
            breadcrumb=analysis_bc,
            help_page=help_page,
            registry=reg,
            sort_base=(40,),
        )

    channel_picker = getattr(widget, "btn_channel_mode_picker", None)
    if channel_picker is not None:
        contribute_simple_options_actions(
            channel_picker,
            options=tuple(
                SimpleOptionAction(oid, label, data, search_terms=terms)
                for oid, label, data, terms in _CHANNEL_OPTION_SPECS
            ),
            prefix="image_compare.channel_mode.",
            owner_tab=OWNER,
            topic="analysis",
            breadcrumb=analysis_bc,
            help_page=help_page,
            registry=reg,
            sort_base=(41,),
        )


def _host_interpolation_controller():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        return None
    for top in app.topLevelWidgets():
        presenter = getattr(top, "presenter", None)
        ui = getattr(presenter, "ui_manager", None) if presenter else None
        transient = getattr(ui, "transient", None) if ui else None
        controller = getattr(transient, "interpolation", None) if transient else None
        if controller is not None:
            return controller
    return None


def _contribute_interpolation_options(reg: ActionRegistry) -> None:
    from ui.actions.flyout_contribute import (
        SimpleOptionAction,
        contribute_simple_options_actions,
    )

    controller = _host_interpolation_controller()
    if controller is None:
        return
    contribute_simple_options_actions(
        controller,
        options=tuple(
            SimpleOptionAction(oid, label, data, search_terms=terms)
            for oid, label, data, terms in _INTERP_OPTION_SPECS
        ),
        prefix="image_compare.interpolation.",
        owner_tab=OWNER,
        topic="magnifier",
        breadcrumb=(_BC_TOOLBAR, _BC_MAGNIFIER),
        help_page=_help_for("magnifier"),
        registry=reg,
        sort_base=(30,),
    )


def _host_font_settings_controller():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        return None
    for top in app.topLevelWidgets():
        presenter = getattr(top, "presenter", None)
        ui = getattr(presenter, "ui_manager", None) if presenter else None
        transient = getattr(ui, "transient", None) if ui else None
        controller = getattr(transient, "font_settings", None) if transient else None
        if controller is not None:
            return controller
    return None


def _ensure_name_edit_chrome(widget) -> None:
    """Show the bottom edit row (same chrome as text-settings Find Action)."""
    controller = _host_font_settings_controller()
    ensure = getattr(controller, "ensure_edit_row_visible", None) if controller else None
    if callable(ensure):
        ensure()
        return
    # Fallback when the transient controller is not wired yet.
    toggle = getattr(widget, "toggle_edit_layout_visibility", None)
    if callable(toggle):
        toggle(True)
    file_btn = getattr(widget, "btn_file_names", None)
    if file_btn is not None and hasattr(file_btn, "setChecked"):
        try:
            file_btn.setChecked(True, emit=False)
        except TypeError:
            try:
                file_btn.setChecked(True, emit_signal=False)
            except TypeError:
                if not bool(file_btn.isChecked()):
                    file_btn.setChecked(True)


def _focus_name_edit(edit) -> None:
    if edit is None:
        return
    focus = getattr(edit, "setFocus", None)
    if callable(focus):
        focus()
    select = getattr(edit, "selectAll", None)
    if callable(select):
        select()


def _contribute_name_edit_actions(widget, reg: ActionRegistry) -> None:
    labels_bc = (_BC_TOOLBAR, _BC_LABELS)
    help_page = _help_for("labels")

    def _ensure() -> None:
        _ensure_name_edit_chrome(widget)

    for order, (action_id, attr, label_key, terms) in enumerate(_NAME_EDIT_SPECS):
        edit = getattr(widget, attr, None)
        if edit is None:
            continue

        def _run(*, ensure=_ensure, field=edit) -> None:
            ensure()
            _focus_name_edit(field)

        def _resolve(*, field=edit):
            return field

        reg.register(
            ActionDescriptor(
                action_id=action_id,
                label_key=label_key,
                breadcrumb=labels_bc,
                owner_tab=OWNER,
                topic="labels",
                help_page=help_page,
                search_terms=terms,
                sort_key=(35, order),
                run=_run,
                target=ActionTarget(
                    ensure_visible=_ensure,
                    resolve_widget=_resolve,
                ),
            )
        )


def _focus_slider(slider) -> None:
    if slider is None:
        return
    focus = getattr(slider, "setFocus", None)
    if callable(focus):
        focus()


def _contribute_magnifier_sliders(widget, reg: ActionRegistry) -> None:
    """Size/capture/speed sliders have no button to click — Find Action can
    still reveal the panel (same chrome as the interpolation flyout) and
    focus the slider so arrow keys adjust it.
    """
    magnifier_bc = (_BC_TOOLBAR, _BC_MAGNIFIER)
    help_page = _help_for("magnifier")
    controller = _host_interpolation_controller()
    ensure = controller.ensure_panel_visible if controller is not None else None

    for order, (action_id, attr, label_key, terms) in enumerate(
        _MAGNIFIER_SLIDER_SPECS
    ):
        slider = getattr(widget, attr, None)
        if slider is None:
            continue

        def _run(*, ensure_fn=ensure, target=slider) -> None:
            if callable(ensure_fn):
                ensure_fn()
            _focus_slider(target)

        def _resolve(*, target=slider):
            return target

        reg.register(
            ActionDescriptor(
                action_id=action_id,
                label_key=label_key,
                breadcrumb=magnifier_bc,
                owner_tab=OWNER,
                topic="magnifier",
                help_page=help_page,
                search_terms=terms,
                sort_key=(42, order),
                run=_run,
                target=ActionTarget(
                    ensure_visible=ensure,
                    resolve_widget=_resolve,
                ),
            )
        )


def _host_magnifier_visibility_controller():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        return None
    for top in app.topLevelWidgets():
        presenter = getattr(top, "presenter", None)
        ui = getattr(presenter, "ui_manager", None) if presenter else None
        transient = getattr(ui, "transient", None) if ui else None
        controller = getattr(transient, "panel_visibility", None) if transient else None
        if controller is not None:
            return controller
    return None


def _host_magnifier_visibility_flyout():
    from tabs.registry import TabRegistry

    tab = TabRegistry().get_tab("image_compare")
    widget = getattr(tab, "_widget", None) if tab is not None else None
    return getattr(widget, "magnifier_visibility_flyout", None) if widget else None


def _contribute_magnifier_visibility_flyout(reg: ActionRegistry) -> None:
    """Per-instance show/hide popup (left/center/right) — previously only
    reachable by hovering the mouse over ``btn_magnifier``, with no catalog
    entry at all. Exposed the same way the color-settings flyout is, plus one
    row per toggle button so a specific instance can be hidden directly.
    """
    controller = _host_magnifier_visibility_controller()
    flyout = _host_magnifier_visibility_flyout()
    if controller is None or flyout is None:
        return

    magnifier_bc = (_BC_TOOLBAR, _BC_MAGNIFIER)
    help_page = _help_for("magnifier")

    def _ensure() -> None:
        controller.show(reason="find_action")

    reg.register(
        ActionDescriptor(
            action_id="image_compare.magnifier.visibility",
            label_key="image_compare.action.magnifier_visibility",
            description_key="tooltip.magnifier_visibility",
            breadcrumb=magnifier_bc,
            owner_tab=OWNER,
            topic="magnifier",
            help_page=help_page,
            search_terms=("visibility", "show", "hide", "left", "center", "right"),
            sort_key=(43, 0),
            run=_ensure,
            target=ActionTarget(
                ensure_visible=_ensure,
                resolve_widget=_host_magnifier_visibility_flyout,
            ),
        )
    )

    group_bc = magnifier_bc + ("image_compare.action.magnifier_visibility",)
    for order, (slot_id, attr, label_key, terms) in enumerate(
        _MAGNIFIER_VISIBILITY_SLOTS
    ):
        button = getattr(flyout, attr, None)
        if button is None:
            continue

        def _run(*, ensure_fn=_ensure, target=button) -> None:
            ensure_fn()
            _toggle_button(target)

        def _resolve(*, target=button):
            return target

        reg.register(
            ActionDescriptor(
                action_id=f"image_compare.magnifier.visibility.{slot_id}",
                label_key=label_key,
                breadcrumb=group_bc,
                owner_tab=OWNER,
                topic="magnifier",
                help_page=help_page,
                search_terms=terms,
                sort_key=(43, 1, order),
                run=_run,
                target=ActionTarget(
                    ensure_visible=_ensure,
                    resolve_widget=_resolve,
                ),
            )
        )


def _active_color_settings_button(widget):
    """Beginner/advanced toolbars each keep their own ``ColorSettingsButton``;
    only one is visible at a time. Resolve dynamically (not at contribute
    time) so this tracks live mode switches instead of registering one row
    per variant, which duplicated every entry in Find Action.
    """
    candidates = [
        getattr(widget, attr, None) for attr in _MAGNIFIER_COLOR_BUTTON_ATTRS
    ]
    candidates = [
        b for b in candidates if b is not None and getattr(b, "flyout", None) is not None
    ]
    for button in candidates:
        is_hidden = getattr(button, "isHidden", None)
        if not callable(is_hidden) or not bool(is_hidden()):
            return button
    return candidates[0] if candidates else None


def _ensure_color_flyout(widget) -> None:
    """Open the active button's flyout the same way
    ``ColorSettingsButton.enterEvent`` does — clicking the button itself only
    triggers smart-color, it does not open the picker swatches.
    """
    button = _active_color_settings_button(widget)
    flyout = getattr(button, "flyout", None) if button is not None else None
    if flyout is None:
        return
    update = getattr(flyout, "update_state", None)
    if callable(update):
        update()
    show = getattr(flyout, "show_aligned", None)
    if callable(show):
        show(button, "top-center", "bottom-center", toggle=False)


def _contribute_magnifier_color_options(widget, reg: ActionRegistry) -> None:
    """Border/divider/capture/laser color swatches inside the color-settings
    flyout — previously only reachable by hovering ``btn_magnifier_color_settings``
    then clicking a swatch, with no catalog entry for the individual pickers.
    """
    if _active_color_settings_button(widget) is None:
        return

    magnifier_bc = (_BC_TOOLBAR, _BC_MAGNIFIER)
    help_page = _help_for("magnifier")
    group_bc = magnifier_bc + ("image_compare.action.magnifier_colors",)

    def _ensure() -> None:
        _ensure_color_flyout(widget)

    def _resolve_option(option_id: str):
        button = _active_color_settings_button(widget)
        flyout = getattr(button, "flyout", None) if button is not None else None
        return flyout.action_button(option_id) if flyout is not None else None

    for order, (option_id, label_key, terms) in enumerate(
        _MAGNIFIER_COLOR_OPTION_SPECS
    ):

        def _run(*, ensure_fn=_ensure, oid=option_id) -> None:
            ensure_fn()
            _click_button(_resolve_option(oid))

        def _resolve(*, oid=option_id):
            return _resolve_option(oid)

        reg.register(
            ActionDescriptor(
                action_id=f"image_compare.magnifier.color_settings.{option_id}",
                label_key=label_key,
                breadcrumb=group_bc,
                owner_tab=OWNER,
                topic="magnifier",
                help_page=help_page,
                search_terms=terms,
                sort_key=(44, order),
                run=_run,
                target=ActionTarget(
                    ensure_visible=_ensure,
                    resolve_widget=_resolve,
                ),
            )
        )


def _host_font_settings_flyout():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        return None
    for top in app.topLevelWidgets():
        presenter = getattr(top, "presenter", None)
        flyout = getattr(presenter, "font_settings_flyout", None) if presenter else None
        if flyout is not None:
            return flyout
    return None


def _show_host_font_settings_flyout() -> None:
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if not isinstance(app, QApplication):
        return
    for top in app.topLevelWidgets():
        presenter = getattr(top, "presenter", None)
        ui = getattr(presenter, "ui_manager", None) if presenter else None
        show = getattr(ui, "show_font_settings_flyout", None) if ui else None
        if callable(show):
            show()
            return


def _contribute_font_settings_flyout(reg: ActionRegistry) -> None:
    from ui.actions.flyout_contribute import contribute_flyout_search_actions
    from ui.widgets.font_settings_search import font_settings_search

    flyout = _host_font_settings_flyout()
    if flyout is None:
        return
    title_key = "image_compare.action.text_settings"
    contribute_flyout_search_actions(
        flyout,
        index=font_settings_search(title_key, include_placement=True),
        prefix="image_compare.font_settings.",
        owner_tab=OWNER,
        topic="labels",
        breadcrumb=(_BC_TOOLBAR, _BC_LABELS),
        show_flyout=_show_host_font_settings_flyout,
        help_page=_help_for("labels"),
        registry=reg,
    )


def contribute_keymap_defaults(registry) -> None:
    """Metadata-only defaults for Settings → Keyboard (no live widgets)."""
    from ui.actions.keymap import KeymapDefaultEntry

    for spec in _SPECS:
        registry.register(
            KeymapDefaultEntry(
                action_id=spec.action_id,
                label_key=spec.label_key,
                default_shortcut=spec.shortcut,
                owner_tab=OWNER,
                breadcrumb=spec.breadcrumb,
                description_key=spec.description_key,
                search_keys=spec.search_keys,
                search_terms=spec.search_terms,
            )
        )
