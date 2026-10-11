# Audit-Meta: pattern=state-machine reason="single toolbar connections wiring — action->presenter bindings"
import logging

from tabs.host_helpers import MessageKind

from tabs.image_compare.events import (
    AnalysisSetChannelViewModeEvent,
    AnalysisSetDiffModeEvent,
)
from plugins.export.events import (
    ExportOpenVideoEditorEvent,
    ExportTogglePauseRecordingEvent,
    ExportToggleRecordingEvent,
)
from tabs.image_compare.canvas.registry import registry
from tabs.image_compare.debug import ic_video_debug_enabled as _video_dbg_enabled
from tabs.image_compare.presenters.toolbar.orientation import (
    on_interpolation_combo_clicked,
    on_orientation_right_clicked,
)
from tabs.image_compare.presenters.toolbar.state import check_name_lengths

logger = logging.getLogger("ImproveImgSLI")
_WARNED_UNAVAILABLE_TOOLBAR_CONTROLS: set[str] = set()

# Connection ownership for the disconnect mirror below: every widget-signal
# connect in this module routes via _track (enforced by
# test_toolbar_connections_pairing), which records the QMetaObject.Connection
# on the presenter. disconnect_signals drops exactly those — the video-editor
# precedent (PRESENTER_TO_DIALOG_SLOTS + disconnect_presenter_signals):
# table-driven pairing, guarded lookups, idempotent, safe to call twice.
_CONNS_ATTR = "_ic_toolbar_conns"


def _track(presenter, signal, slot):
    """Connect ``slot`` to ``signal`` and record it for :func:`disconnect_signals`.

    Returns the ``QMetaObject.Connection`` (or ``None`` when the connect
    itself failed). Only bookkeeping lives here — failures to record never
    break the connect.
    """
    try:
        conn = signal.connect(slot)
    except Exception:
        return None
    try:
        conns = getattr(presenter, _CONNS_ATTR, None)
        if conns is None:
            conns = []
            setattr(presenter, _CONNS_ATTR, conns)
        conns.append(conn)
    except Exception:
        pass
    return conn


def disconnect_signals(presenter) -> int:
    """Exact mirror of :func:`connect_signals` (video-presenter precedent).

    Drops every toolbar widget→presenter/controller slot recorded by
    ``_track`` so no late queued signal (deferred editor attach, flyout
    close, color-button hover) reaches a torn-down presenter. Called from
    presenter teardown (and safe before ``connect_signals`` re-wire:
    disconnecting twice is a no-op). Returns the number disconnected.
    """
    try:
        conns = getattr(presenter, _CONNS_ATTR, None)
    except Exception:
        return 0
    if not conns:
        return 0
    try:
        setattr(presenter, _CONNS_ATTR, [])
    except Exception:
        pass
    try:
        from PySide6.QtCore import QObject
    except Exception:
        return 0
    dropped = 0
    for conn in list(conns):
        try:
            if QObject.disconnect(conn):
                dropped += 1
        except Exception:
            continue
    return dropped

def _show_unavailable_toolbar_capability(presenter, control_id: str) -> None:
    if control_id in _WARNED_UNAVAILABLE_TOOLBAR_CONTROLS:
        return
    _WARNED_UNAVAILABLE_TOOLBAR_CONTROLS.add(control_id)
    logger.warning("Toolbar capability '%s' is unavailable", control_id)
    ui_manager = getattr(presenter, "ui_manager", None)
    if ui_manager is None or getattr(ui_manager, "messages", None) is None:
        return
    ui_manager.messages.show_non_modal_message(
        kind=MessageKind.WARNING,
        title="Feature unavailable",
        text=f"The '{control_id}' capability is not available in this build.",
    )

def _invoke_toolbar_binding(control_id: str, hook_name: str, presenter, *args):
    binding = registry().get_feature_toolbar_binding(control_id)
    if binding is None:
        _show_unavailable_toolbar_capability(presenter, control_id)
        return
    hook = getattr(binding, hook_name, None)
    if hook is None:
        _show_unavailable_toolbar_capability(presenter, control_id)
        return
    hook(presenter, *args)

def _resolve_session_handler(controller):
    if controller is None:
        return None
    sessions = getattr(controller, "sessions", None)
    if sessions is not None:
        return sessions
    return controller if hasattr(controller, "on_combobox_changed") else None

def _resolve_interpolation_handler(controller):
    if controller is None:
        return None
    if hasattr(controller, "on_interpolation_changed"):
        return controller.on_interpolation_changed
    sessions = getattr(controller, "sessions", None)
    if sessions is not None and hasattr(sessions, "on_interpolation_changed"):
        return sessions.on_interpolation_changed
    return None

def connect_signals(presenter):
    # Idempotent re-wire: drop any previously tracked connections FIRST.
    # connect_signals can run twice (feature on_resolved + the explicit
    # presenters/connections.py call); without this the reset below orphaned
    # the first call's connections (still firing), so e.g. the font flyout's
    # settings_changed was connected twice and every slider tick applied the
    # font settings twice.
    disconnect_signals(presenter)
    # Fresh ownership ledger: a re-wire after disconnect_signals starts
    # clean instead of accumulating dead connections.
    try:
        setattr(presenter, _CONNS_ATTR, [])
    except Exception:
        pass
    _connect_session_actions(presenter)
    _connect_name_editing(presenter)
    _connect_viewport_controls(presenter)
    _connect_orientation_controls(presenter)
    _connect_mode_specific_controls(presenter)
    _connect_ui_manager_controls(presenter)
    _connect_topic_palette_entry_points(presenter)
    _connect_session_comboboxes(presenter)
    _connect_image_load_buttons(presenter)
    _connect_text_settings_button(presenter)
    _connect_save_buttons(presenter)
    _connect_font_flyout(presenter)
    _connect_magnifier_color_controls(presenter)

def _connect_session_actions(presenter):
    controller = presenter.main_controller
    if controller is None or controller.sessions is None:
        return

    ui = presenter.widget
    _track(presenter, ui.btn_swap.shortClicked, controller.sessions.swap_current_images)
    _track(presenter, ui.btn_swap.longPressed, controller.sessions.swap_entire_lists)
    _track(presenter, ui.btn_clear_list1.shortClicked,
        lambda: controller.sessions.remove_current_image_from_list(1)
    )
    _track(presenter, ui.btn_clear_list1.longPressed,
        lambda: controller.sessions.clear_image_list(1)
    )
    _track(presenter, ui.btn_clear_list2.shortClicked,
        lambda: controller.sessions.remove_current_image_from_list(2)
    )
    _track(presenter, ui.btn_clear_list2.longPressed,
        lambda: controller.sessions.clear_image_list(2)
    )

def _connect_name_editing(presenter):
    controller = presenter.main_controller
    ui = presenter.widget
    if controller is not None and controller.sessions is not None:
        _track(presenter, ui.edit_name1.editingFinished,
            lambda: controller.sessions.on_edit_name_changed(1, ui.edit_name1.text())
        )
        _track(presenter, ui.edit_name2.editingFinished,
            lambda: controller.sessions.on_edit_name_changed(2, ui.edit_name2.text())
        )
        _track(presenter, ui.edit_name1.textEdited,
            lambda text: controller.sessions.on_edit_name_changed(1, text)
        )
        _track(presenter, ui.edit_name2.textEdited,
            lambda text: controller.sessions.on_edit_name_changed(2, text)
        )

    _track(presenter, ui.edit_name1.textChanged, lambda: check_name_lengths(presenter))
    _track(presenter, ui.edit_name2.textChanged, lambda: check_name_lengths(presenter))

def _connect_viewport_controls(presenter):
    controller = presenter.main_controller
    ui = presenter.widget
    event_bus = presenter.event_bus
    interpolation_handler = _resolve_interpolation_handler(controller)

    if controller:
        _track(presenter, ui.btn_orientation.toggled,
            lambda checked: _invoke_toolbar_binding(
                "divider.orientation",
                "on_toggled",
                presenter,
                checked,
            )
        )
        _track(presenter, ui.btn_orientation.valueChanged,
            lambda value: _invoke_toolbar_binding(
                "divider.orientation",
                "on_value_changed",
                presenter,
                value,
            )
        )
        _track(presenter, ui.btn_magnifier_orientation.toggled,
            lambda checked: _invoke_toolbar_binding(
                "magnifier.orientation",
                "on_toggled",
                presenter,
                checked,
            )
        )
        _track(presenter, ui.btn_magnifier_orientation.valueChanged,
            lambda value: _invoke_toolbar_binding(
                "magnifier.divider.thickness",
                "on_value_changed",
                presenter,
                value,
            )
        )
        _track(presenter, ui.btn_magnifier.toggled,
            lambda checked: _invoke_toolbar_binding(
                "magnifier.enabled",
                "on_toggled",
                presenter,
                checked,
            )
        )
        if hasattr(ui, "btn_magnifier_instances"):
            _track(presenter, ui.btn_magnifier_instances.addClicked,
                lambda: _invoke_toolbar_binding(
                    "magnifier.instances.add",
                    "on_toggled",
                    presenter,
                    True,
                )
            )
            _track(presenter, ui.btn_magnifier_instances.removeClicked,
                lambda: _invoke_toolbar_binding(
                    "magnifier.instances.remove",
                    "on_toggled",
                    presenter,
                    True,
                )
            )
        _track(presenter, ui.btn_file_names.toggled,
            lambda checked: _invoke_toolbar_binding(
                "filename_overlay.visible",
                "on_toggled",
                presenter,
                checked,
            )
        )
        _track(presenter, ui.btn_freeze.toggled,
            lambda checked: _invoke_toolbar_binding(
                "magnifier.freeze",
                "on_toggled",
                presenter,
                checked,
            )
        )
        _track(presenter, ui.slider_size.valueChanged,
            lambda value: _invoke_toolbar_binding(
                "magnifier.size",
                "on_value_changed",
                presenter,
                value,
            )
        )
        _track(presenter, ui.slider_capture.valueChanged,
            lambda value: _invoke_toolbar_binding(
                "capture.size",
                "on_value_changed",
                presenter,
                value,
            )
        )
        _track(presenter, ui.slider_size.sliderPressed,
            lambda: _invoke_toolbar_binding(
                "magnifier.size",
                "on_pressed",
                presenter,
            )
        )
        _track(presenter, ui.slider_size.sliderReleased,
            lambda: _invoke_toolbar_binding(
                "magnifier.size",
                "on_released",
                presenter,
            )
        )
        _track(presenter, ui.slider_capture.sliderPressed,
            lambda: _invoke_toolbar_binding(
                "capture.size",
                "on_pressed",
                presenter,
            )
        )
        _track(presenter, ui.slider_capture.sliderReleased,
            lambda: _invoke_toolbar_binding(
                "capture.size",
                "on_released",
                presenter,
            )
        )
        store = presenter.store
        if store is not None:

            def on_speed_changed(value: int):
                from core.state_management.actions import SetMovementSpeedAction

                speed = value / 100.0
                dispatcher = store.get_dispatcher() if hasattr(store, "get_dispatcher") else None
                if dispatcher is not None:
                    dispatcher.dispatch(SetMovementSpeedAction(speed), scope="viewport")
                settings_manager = getattr(controller, "settings_manager", None) if controller is not None else None
                if settings_manager is not None:
                    settings_manager._save_setting("movement_speed_per_sec", speed)
            _track(presenter, ui.slider_speed.valueChanged, on_speed_changed)

        if interpolation_handler is not None:
            _track(presenter, ui.combo_interpolation.currentIndexChanged, interpolation_handler)

def _connect_orientation_controls(presenter):
    ui = presenter.widget
    _track(presenter, ui.btn_orientation.rightClicked,
        lambda: on_orientation_right_clicked(presenter)
    )
    _track(presenter, ui.btn_magnifier_orientation.rightClicked,
        lambda: _invoke_toolbar_binding(
            "magnifier.orientation",
            "on_right_clicked",
            presenter,
        )
    )

    if hasattr(ui.btn_orientation, "middleClicked"):
        _track(presenter, ui.btn_orientation.middleClicked,
            lambda: _invoke_toolbar_binding(
                "divider.orientation",
                "on_middle_clicked",
                presenter,
            )
        )
    if hasattr(ui.btn_magnifier_orientation, "middleClicked"):
        _track(presenter, ui.btn_magnifier_orientation.middleClicked,
            lambda: _invoke_toolbar_binding(
                "magnifier.orientation",
                "on_middle_clicked",
                presenter,
            )
        )
    if hasattr(ui.btn_magnifier, "rightClicked"):
        _track(presenter, ui.btn_magnifier.rightClicked,
            lambda: _invoke_toolbar_binding(
                "magnifier.enabled",
                "on_right_clicked",
                presenter,
            )
        )

def _connect_mode_specific_controls(presenter):
    controller = presenter.main_controller
    ui = presenter.widget

    if not controller:
        return

    if hasattr(ui, "btn_orientation_simple"):
        _track(presenter, ui.btn_orientation_simple.toggled,
            lambda checked: _invoke_toolbar_binding(
                "divider.orientation_simple",
                "on_toggled",
                presenter,
                checked,
            )
        )
    if hasattr(ui, "btn_divider_visible"):
        _track(presenter, ui.btn_divider_visible.toggled,
            lambda checked: _invoke_toolbar_binding(
                "divider.visible",
                "on_toggled",
                presenter,
                checked,
            )
        )
    if hasattr(ui, "btn_divider_color"):
        _track(presenter, ui.btn_divider_color.clicked,
            lambda: _invoke_toolbar_binding(
                "divider.color",
                "on_right_clicked",
                presenter,
            )
        )
    if hasattr(ui, "btn_divider_width"):
        _track(presenter, ui.btn_divider_width.valueChanged,
            lambda value: _invoke_toolbar_binding(
                "divider.width",
                "on_value_changed",
                presenter,
                value,
            )
        )
    if hasattr(ui, "btn_magnifier_orientation_simple"):
        _track(presenter, ui.btn_magnifier_orientation_simple.toggled,
            lambda checked: _invoke_toolbar_binding(
                "magnifier.orientation",
                "on_toggled",
                presenter,
                checked,
            )
        )
    if hasattr(ui, "btn_magnifier_divider_visible"):
        _track(presenter, ui.btn_magnifier_divider_visible.toggled,
            lambda checked: _invoke_toolbar_binding(
                "magnifier.divider.visibility",
                "on_toggled",
                presenter,
                checked,
            )
        )
    if hasattr(ui, "btn_magnifier_divider_width"):
        _track(presenter, ui.btn_magnifier_divider_width.valueChanged,
            lambda value: _invoke_toolbar_binding(
                "magnifier.divider.thickness",
                "on_value_changed",
                presenter,
                value,
            )
        )
    if hasattr(ui, "btn_magnifier_guides_simple"):
        _track(presenter, ui.btn_magnifier_guides_simple.toggled,
            lambda checked: _invoke_toolbar_binding(
                "guides.enabled_simple",
                "on_toggled",
                presenter,
                checked,
            )
        )
    if hasattr(ui, "btn_magnifier_guides_width"):
        _track(presenter, ui.btn_magnifier_guides_width.valueChanged,
            lambda value: _invoke_toolbar_binding(
                "guides.thickness",
                "on_value_changed",
                presenter,
                value,
            )
        )


def _connect_ui_manager_controls(presenter):
    ui = presenter.widget
    ui_manager = presenter.ui_manager

    if (
        ui_manager is not None
        and hasattr(ui, "btn_file_names")
        and ui.btn_file_names is not None
        and hasattr(ui.btn_file_names, "rightClicked")
    ):
        _track(presenter, ui.btn_file_names.rightClicked,
            lambda: ui_manager.transient.toggle_font_settings_flyout(anchor_widget=ui.btn_file_names)
        )

    _track(presenter, ui.combo_interpolation.clicked,
        lambda: on_interpolation_combo_clicked(presenter)
    )

    if ui_manager:
        _track(presenter, ui.combo_image1.clicked, lambda: ui_manager.show_flyout(1))
        _track(presenter, ui.combo_image2.clicked, lambda: ui_manager.show_flyout(2))
    else:
        logger.warning("ToolbarPresenter: ui_manager not set, flyout connections skipped")


def _open_topic_palette(presenter, topic: str) -> None:
    from ui.actions.palette import show_command_palette

    parent = getattr(presenter, "main_window_app", None)
    if parent is None:
        widget = getattr(presenter, "widget", None)
        parent = widget.window() if widget is not None else None
    show_command_palette(topic=topic, parent=parent)


def _connect_topic_palette_entry_points(presenter):
    """Middle-click toolbar chrome → Find Action filtered by topic."""
    ui = presenter.widget

    def _bind(button, topic: str) -> None:
        if button is None or not hasattr(button, "middleClicked"):
            return
        _track(presenter, button.middleClicked, lambda t=topic: _open_topic_palette(presenter, t))

    _bind(getattr(ui, "btn_freeze", None), "magnifier")
    _bind(getattr(ui, "btn_save", None), "export")
    _bind(getattr(ui, "btn_quick_save", None), "export")
    _bind(getattr(ui, "btn_record", None), "video")
    _bind(getattr(ui, "btn_divider_visible", None), "divider")
    _bind(getattr(ui, "btn_file_names", None), "labels")


def _connect_session_comboboxes(presenter):
    controller = presenter.main_controller
    ui = presenter.widget
    session_handler = _resolve_session_handler(controller)
    interpolation_handler = _resolve_interpolation_handler(controller)
    if controller is None or session_handler is None:
        return

    _track(presenter, ui.combo_image1.wheelScrolledToIndex,
        lambda index: session_handler.on_combobox_changed(1, index)
    )
    _track(presenter, ui.combo_image2.wheelScrolledToIndex,
        lambda index: session_handler.on_combobox_changed(2, index)
    )
    if interpolation_handler is not None:
        _track(presenter, ui.combo_interpolation.wheelScrolledToIndex, interpolation_handler)

    event_bus = presenter.event_bus or getattr(controller, "event_bus", None)
    if event_bus is None:
        return

    _track(presenter, ui.btn_diff_mode_picker.selected,
        lambda data: event_bus.emit(AnalysisSetDiffModeEvent(data))
    )
    _track(presenter, ui.btn_channel_mode_picker.selected,
        lambda data: event_bus.emit(AnalysisSetChannelViewModeEvent(data))
    )
    def _ensure_deferred():
        # Editor-zone gate: canonical predicate (umbrella retained; frozen).
        _dbg = _video_dbg_enabled()
        try:
            ctx = getattr(presenter.main_controller, "context", None)
            if ctx is not None and hasattr(ctx, "ensure_deferred_plugins_loaded"):
                loaded = ctx.ensure_deferred_plugins_loaded()
                if _dbg:
                    logger.warning("[video-editor-debug] ensure_deferred_plugins_loaded -> %s", loaded)
                try:
                    mc = presenter.main_controller
                    window_shell = getattr(mc, "window_shell", None) or getattr(presenter, "main_window_app", None)
                    if window_shell is None:
                        w = getattr(presenter, "widget", None)
                        try:
                            import shiboken6
                            if w is not None and not shiboken6.Shiboken.isValid(w):
                                w = None
                        except Exception:
                            pass
                        window_shell = w.window() if w is not None and hasattr(w, "window") else None
                    if window_shell is not None and hasattr(mc, "attach_deferred_plugins"):
                        mc.attach_deferred_plugins(window_shell)
                except Exception as exc2:
                    logger.warning("[video-editor-debug] attach_deferred failed: %s", exc2) if _dbg else logger.debug("[video-editor-debug] attach_deferred failed: %s", exc2)
        except Exception as exc:
            if _dbg:
                logger.warning("[video-editor-debug] ensure_deferred failed: %s", exc)

    def _emit_with_ensure(event_factory, name: str):
        from PySide6.QtCore import QTimer
        # Editor-zone gate: canonical predicate (umbrella retained; frozen).
        _dbg = _video_dbg_enabled()
        subs = len(getattr(event_bus, "_subscribers", {}).get(event_factory, [])) if event_bus else 0
        if _dbg:
            logger.warning("[video-editor-debug] CLICK %s subscribers=%s", name, subs)
        if subs == 0:
            def _do():
                _ensure_deferred()
                if _dbg:
                    new_subs = len(getattr(event_bus, "_subscribers", {}).get(event_factory, [])) if event_bus else 0
                    logger.warning("[video-editor-debug] AFTER ensure %s subscribers=%s", name, new_subs)
                event_bus.emit(event_factory())
            QTimer.singleShot(0, _do)
            return
        event_bus.emit(event_factory())

    _track(presenter, ui.btn_record.toggled, lambda checked: _emit_with_ensure(ExportToggleRecordingEvent, "ExportToggleRecordingEvent"))
    _track(presenter, ui.btn_pause.toggled, lambda checked: _emit_with_ensure(ExportTogglePauseRecordingEvent, "ExportTogglePauseRecordingEvent"))
    def _emit_open_editor():
        from PySide6.QtCore import QTimer
        try:
            from core.tracing.tracer import Tracer
            if Tracer.enabled():
                Tracer.instance().record("video.editor.toolbar_click", "btn_video_editor clicked", {})
        except Exception:
            pass
        _has_subs = len(getattr(event_bus, "_subscribers", {}).get(ExportOpenVideoEditorEvent, [])) if event_bus else 0
        # Editor-zone gate: canonical predicate (umbrella retained; frozen).
        _dbg = _video_dbg_enabled()
        if _dbg:
            logger.warning("[video-editor-debug] CLICK btn_video_editor -> ExportOpenVideoEditorEvent bus=%s subscribers=%s has_recorder=%s", event_bus, _has_subs, getattr(getattr(presenter, "main_controller", None), "_recorder", None) is not None)
        else:
            logger.debug("[video-editor-debug] CLICK btn_video_editor subscribers=%s", _has_subs)

        def _do_emit():
            if _dbg:
                logger.warning("[video-editor-debug] EMIT ExportOpenVideoEditorEvent (deferred)")
            event_bus.emit(ExportOpenVideoEditorEvent())

        # Deferred host plugins (export/video_editor) may not be loaded yet when
        # bootstrap tab is active — ensure they are before emitting, otherwise
        # the event would be lost (0 subscribers) and button appears to do nothing.
        # Do ensure+attach async to avoid re-entrancy segfault (plugin init
        # creates QObjects while Qt is processing the click).
        if _has_subs == 0:
            def _ensure_and_emit():
                _ensure_deferred()
                if _dbg:
                    new_subs = len(getattr(event_bus, "_subscribers", {}).get(ExportOpenVideoEditorEvent, [])) if event_bus else 0
                    subs_map = list(getattr(event_bus, "_subscribers", {}).keys()) if event_bus and hasattr(event_bus, "_subscribers") else []
                    logger.warning("[video-editor-debug] AFTER ensure+attach subscribers=%s all_events=%s", new_subs, [c.__name__ for c in subs_map])
                    if new_subs == 0:
                        logger.warning("[video-editor-debug] REJECT: still 0 subscribers after deferred load — export plugin not subscribed, check ExportPlugin.configure_controller")
                _do_emit()
            QTimer.singleShot(0, _ensure_and_emit)
            return
        _do_emit()

    _track(presenter, ui.btn_video_editor.clicked, _emit_open_editor)

def _connect_image_load_buttons(presenter):
    from tabs.image_compare.presenters.toolbar.actions import open_image_dialog
    _track(presenter, presenter.widget.btn_image1.clicked, lambda: open_image_dialog(presenter, 1))
    _track(presenter, presenter.widget.btn_image2.clicked, lambda: open_image_dialog(presenter, 2))

def _connect_text_settings_button(presenter):
    _track(presenter, presenter.widget.btn_text_settings.clicked,
        lambda: presenter.ui_manager.transient.toggle_font_settings_flyout(
            anchor_widget=presenter.widget.btn_text_settings
        )
    )

def _connect_save_buttons(presenter):
    from tabs.image_compare.presenters.toolbar.state import _get_window_presenter

    def _export_presenter():
        window_presenter = _get_window_presenter(presenter)
        if window_presenter is not None and hasattr(window_presenter, "get_feature"):
            return window_presenter.get_feature("export")
        return None

    def _on_quick_save():
        export_presenter = _export_presenter()
        if export_presenter is None:
            return
        export_presenter.quick_save()

    def _on_save():
        export_presenter = _export_presenter()
        if export_presenter is not None:
            export_presenter.save_result()

    _track(presenter, presenter.widget.btn_quick_save.clicked, _on_quick_save)
    _track(presenter, presenter.widget.btn_save.clicked, _on_save)

def _connect_font_flyout(presenter):
    from domain.qt_adapters import qcolor_to_color
    from plugins.settings.events import SettingsApplyFontSettingsEvent
    transient = getattr(presenter.ui_manager, "transient", None) if presenter.ui_manager else None
    flyout = getattr(transient, "font_settings_flyout", None)
    if flyout is None:
        return
    _track(presenter, flyout.closed, lambda: _on_font_flyout_closed(presenter))

    def _emit_font_settings(size, weight, color, bg_color, draw_bg, placement, alpha):
        args = (
            size, weight,
            qcolor_to_color(color), qcolor_to_color(bg_color),
            draw_bg, placement, alpha,
        )
        if presenter.event_bus:
            presenter.event_bus.emit(SettingsApplyFontSettingsEvent(*args))
        elif presenter.main_controller is not None:
            presenter.main_controller.apply_font_settings(*args)

    # The font-settings flyout is a single main-window-level instance shared by
    # every presenter that wires it. A per-presenter connection ledger can't
    # drop another presenter's connection, so ``settings_changed`` ended up
    # connected once per presenter -> every slider tick applied the font
    # settings 2x. Keep exactly one connection on the flyout itself.
    prev = getattr(flyout, "_ic_settings_changed_conn", None)
    if prev is not None:
        try:
            from PySide6.QtCore import QObject

            QObject.disconnect(prev)
        except Exception:
            pass
    conn = _track(presenter, flyout.settings_changed, _emit_font_settings)
    try:
        flyout._ic_settings_changed_conn = conn
    except Exception:
        pass

def _on_font_flyout_closed(presenter):
    presenter.ui_manager.transient.mark_font_popup_closed()
    presenter.widget.btn_text_settings.setFlyoutOpen(False)

def _connect_magnifier_color_controls(presenter):
    from tabs.image_compare.presenters.toolbar.actions import (
        on_color_option_clicked,
        on_magnifier_element_hover_ended,
        on_magnifier_element_hovered,
        on_magnifier_guides_thickness_changed,
        on_magnifier_guides_toggled,
    )
    from tabs.image_compare.presenters.toolbar.state import _get_settings_presenter_from_window
    widget = presenter.widget

    def _wire(button):
        if button is None:
            return
        if hasattr(button, "set_store"):
            button.set_store(presenter.store)

        def _apply_smart_colors():
            settings_presenter = _get_settings_presenter_from_window(presenter)
            if settings_presenter is not None:
                settings_presenter.apply_smart_magnifier_colors()

        _track(presenter, button.smartColorSetRequested, _apply_smart_colors)
        _track(presenter, button.colorOptionClicked,
            lambda option: on_color_option_clicked(presenter, option)
        )
        _track(presenter, button.elementHovered,
            lambda element_name: on_magnifier_element_hovered(presenter, element_name)
        )
        _track(presenter, button.elementHoverEnded,
            lambda: on_magnifier_element_hover_ended(presenter)
        )

    _wire(getattr(widget, "btn_magnifier_color_settings", None))
    _wire(getattr(widget, "btn_magnifier_color_settings_beginner", None))

    _track(presenter, widget.btn_magnifier_guides.toggled,
        lambda checked: on_magnifier_guides_toggled(presenter, not checked)
    )
    _track(presenter, widget.btn_magnifier_guides.valueChanged,
        lambda value: on_magnifier_guides_thickness_changed(presenter, value)
    )
