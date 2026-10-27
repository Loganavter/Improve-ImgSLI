import os

from PySide6.QtWidgets import QFileDialog

from core.events import CoreErrorOccurredEvent, CoreUpdateRequestedEvent
from shared.image_extensions import build_image_dialog_filter, is_loadable_image_path
from sli_ui_toolkit.i18n import tr
from tabs.image_compare.canvas.registry import registry
from tabs.image_compare.presenters.toolbar.state import _get_settings_presenter_from_window

def _canon_dialog_filter(lang: str) -> str:
    """QFileDialog filter built by the canon only (``shared.image_extensions``).

    Do NOT compose a glob list here. A local copy of the list made this dialog
    offer ``.gif`` while every other entry (DnD/chrome/carry, which gate on the
    same module) bounced it — one file accepted in one place and rejected in
    another, the drift class closed for ``.jxl`` in the 2026-08-25 C9 review.
    Only the "All files" label is localised; the suffix set is the canon's.
    """
    return build_image_dialog_filter(
        all_files_label=f"{tr('common.file_type.all_files', lang)} (*)"
    )


def _split_loadable_selection(paths) -> tuple[list[str], list[str]]:
    """Split a dialog selection into (loadable, refused) with the DnD predicate.

    ``is_loadable_image_path`` is the same admission rule the drop path applies
    (accepted suffix ∧ ``is_file``), so the dialog cannot hand the loader a file
    DnD would have dropped.
    """
    loadable: list[str] = []
    refused: list[str] = []
    for path in paths:
        (loadable if is_loadable_image_path(path) else refused).append(path)
    return loadable, refused


def _report_refused_selection(presenter, refused, lang: str) -> None:
    """Surface a refused dialog pick through the IC error path (no new UI).

    Same message shape as ``use_cases/slot._finalize_loaded_paths``: one header
    plus the offending names, so a dialog-confirmed file never disappears
    silently. Degrades to a no-op if no error channel is reachable — the
    refusal itself has already happened.
    """
    details = "\n - ".join(
        f"{os.path.basename(str(p)) or p}: "
        f"{tr('image_compare.msg.invalid_item_type_or_empty_path', lang)}"
        for p in refused
    )
    message = (
        tr("image_compare.msg.some_images_could_not_be_loaded", lang)
        + ":\n\n - "
        + details
    )
    try:
        bus = getattr(presenter, "event_bus", None)
    except Exception:  # dead QObject
        bus = None
    if bus is not None:
        try:
            bus.emit(CoreErrorOccurredEvent(message))
            return
        except Exception:
            pass
    try:
        main_controller = getattr(presenter, "main_controller", None)
        signal = (
            getattr(main_controller, "error_occurred", None)
            if main_controller is not None
            else None
        )
    except Exception:
        signal = None
    emit = getattr(signal, "emit", None)
    if callable(emit):
        try:
            emit(message)
        except Exception:
            pass


def open_image_dialog(presenter, image_number: int):
    start_dir = presenter.store.settings.export_default_dir or os.path.expanduser("~")
    lang = presenter.store.settings.current_language
    filters = _canon_dialog_filter(lang)
    paths, _ = QFileDialog.getOpenFileNames(
        presenter.main_window_app,
        tr("image_compare.button.select_images", lang),
        start_dir,
        filters,
    )

    if paths:
        # Validate the selection with the DnD predicate before any load is
        # scheduled: the "All files" filter section (and a typed filename)
        # still lets a non-image through, and this entry used to forward it
        # verbatim. Refused picks are reported, never loaded silently; the
        # rest of a multi-selection survives.
        pinned_paths, refused = _split_loadable_selection(paths)
        if refused:
            _report_refused_selection(presenter, refused, lang)
        if not pinned_paths:
            return

        delay = 100 if getattr(presenter, "_first_dialog_load_pending", True) else 0
        from PySide6.QtCore import QTimer

        # Pin the session object across the dialog defer: the lambda runs up
        # to 100ms later, by which time main_controller.sessions may have
        # been rebound (tab switch / session rebuild) — loading into the
        # live attribute then would target the wrong session or crash on
        # None. The pinned ref always targets the session that owned the
        # dialog; a dead session is a guarded no-op via load_images...
        # failure paths, never a misdirected load.
        main_controller = presenter.main_controller
        sessions = (
            getattr(main_controller, "sessions", None)
            if main_controller is not None
            else None
        )

        QTimer.singleShot(
            delay,
            lambda: (
                sessions.load_images_from_paths(pinned_paths, image_number)
                if sessions is not None
                else None
            ),
        )
        presenter._first_dialog_load_pending = False

def on_magnifier_guides_toggled(presenter, checked: bool):
    binding = registry().get_feature_toolbar_binding("guides.enabled")
    if binding is not None and binding.on_toggled is not None:
        binding.on_toggled(presenter, checked)

def on_magnifier_guides_thickness_changed(presenter, thickness: int):
    binding = registry().get_feature_toolbar_binding("guides.thickness")
    if binding is not None and binding.on_value_changed is not None:
        binding.on_value_changed(presenter, thickness)

def on_magnifier_element_hovered(presenter, element_name: str):
    if not presenter.store:
        return
    dispatcher = presenter.store.get_dispatcher()
    if dispatcher is not None:
        import importlib

        _magnifier_actions = importlib.import_module(
            "tabs.image_compare.canvas.features.magnifier.input.actions"
        )
        SetHighlightedMagnifierElementAction = _magnifier_actions.SetHighlightedMagnifierElementAction

        dispatcher.dispatch(SetHighlightedMagnifierElementAction(element_name), scope="viewport")
    if presenter.event_bus:
        presenter.event_bus.emit(CoreUpdateRequestedEvent())
    else:
        presenter.main_controller.update_requested.emit()

def on_magnifier_element_hover_ended(presenter):
    if not presenter.store:
        return
    dispatcher = presenter.store.get_dispatcher()
    if dispatcher is not None:
        import importlib

        _magnifier_actions = importlib.import_module(
            "tabs.image_compare.canvas.features.magnifier.input.actions"
        )
        SetHighlightedMagnifierElementAction = _magnifier_actions.SetHighlightedMagnifierElementAction

        dispatcher.dispatch(SetHighlightedMagnifierElementAction(None), scope="viewport")
    if presenter.event_bus:
        presenter.event_bus.emit(CoreUpdateRequestedEvent())
    else:
        presenter.main_controller.update_requested.emit()

def on_color_option_clicked(presenter, option: str):
    settings_presenter = _get_settings_presenter_from_window(presenter)
    if settings_presenter is None:
        return
    if option == "divider":
        settings_presenter.show_magnifier_divider_color_picker()
    elif option == "capture":
        settings_presenter.show_capture_ring_color_picker()
    elif option == "border":
        settings_presenter.show_magnifier_border_color_picker()
    elif option == "laser":
        settings_presenter.show_laser_color_picker()
