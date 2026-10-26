from __future__ import annotations

import logging

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication, QLineEdit, QPlainTextEdit, QTextEdit

from sli_ui_toolkit.widgets import CustomLineEdit

from events.app_event.common import get_main_controller
from tabs.registry import get_shared_tab_registry
from core.log_names import APP_LOGGER_NAME

logger = logging.getLogger(APP_LOGGER_NAME)


def key_event_chord(event: QKeyEvent) -> str:
    """Portable-text chord for ``event``, or ``""`` when it has no chord.

    Modifier-only events (Shift/Ctrl/Alt/Meta) are deliberately empty: they
    carry press/release state the global handler must keep seeing, and no
    action is ever bound to a bare modifier.
    """
    try:
        key = event.key()
    except Exception:
        return ""
    if key in (
        Qt.Key.Key_Shift,
        Qt.Key.Key_Control,
        Qt.Key.Key_Alt,
        Qt.Key.Key_Meta,
    ):
        return ""
    try:
        from PySide6.QtGui import QKeySequence

        from ui.actions.keymap import normalize_sequence

        return normalize_sequence(
            QKeySequence(event.keyCombination()).toString(
                QKeySequence.SequenceFormat.PortableText
            )
        )
    except Exception:
        return ""


def focused_widget():
    """The live focus widget (seam for routing tests; never cached)."""
    return QApplication.focusWidget()


def widget_accepts_text_keys(widget) -> bool:
    """True when unmodified letter/space keys are input for ``widget``.

    The global handler routes W/A/S/D/Q/E and Space to the canvas overlay;
    that route must not fire when the focused widget consumes those keys as
    input. Native editors are matched by type; toolkit controls that paint
    themselves (``ComboBox`` — a ``Button``, not a ``QLineEdit``) opt in with
    the duck-typed ``acceptsTextKeys()`` protocol. Before it existed, typing
    ``deepseek`` into a focused model ComboBox delivered only ``p`` and ``k``:
    d/e/s are overlay-movement keys and were swallowed by this route
    (measured live 2026-10-22 through the control channel).
    """
    if widget is None:
        return False
    if isinstance(widget, (QLineEdit, CustomLineEdit, QTextEdit, QPlainTextEdit)):
        return True
    checker = getattr(widget, "acceptsTextKeys", None)
    if callable(checker):
        try:
            return bool(checker())
        except Exception:
            return False
    return False


def active_tab_shortcut_owns_event(event: QKeyEvent) -> bool:
    """True when the live shortcut binder claims this event's chord.

    ``ActionShortcutBinder`` is resynced for the ACTIVE tab (see
    ``ui.actions.binder.resync_action_shortcuts``), so its claimed chords are
    exactly the shortcuts a focused widget of that tab may receive. Whether a
    chord is globally routed and whether the tab binds it are independent
    questions: a letter can be both a tab's action chord and an
    overlay-movement key, so the global route used to swallow it before the
    shortcut map ever saw it (see ``events/router.py`` and the tab shell's
    ``keyPressEvent``). Which canvas keys an action may not take is gated
    statically by ``tests/contracts/test_canvas_key_reservation.py``.

    The chord index and its normalization live in
    ``ActionShortcutBinder.owns_chord`` — this helper only adapts a
    ``QKeyEvent`` to that method (there is no second normalizer here).
    """
    chord = key_event_chord(event)
    if not chord:
        return False
    try:
        from ui.actions.binder import get_action_shortcut_binder

        active_tab = getattr(
            get_shared_tab_registry().get_active_tab(), "session_type", None
        )
        return get_action_shortcut_binder().owns_chord(chord, active_tab=active_tab)
    except Exception:
        return False


def chord_claim_report(event: QKeyEvent) -> str:
    """Route-log diagnostic: which tab is active and who claims this chord.

    Printed only where a key is about to be routed globally despite the
    binder veto, because a live "the chord died" report cannot be told apart
    from "the binder had no claim at that instant" (a resync that ran for
    another tab, or one that has not run yet) without these three values.
    """
    chord = key_event_chord(event)
    try:
        tab = get_shared_tab_registry().get_active_tab()
    except Exception as exc:  # noqa: BLE001 - diagnostics must never raise
        return f"chord={chord!r} active_tab=<registry error {exc!r}>"
    active_tab = getattr(tab, "session_type", None) if tab is not None else None
    tab_desc = "none" if tab is None else f"{type(tab).__name__}({active_tab!r})"
    try:
        from ui.actions.binder import get_action_shortcut_binder

        claim = get_action_shortcut_binder().describe_claim(
            chord, active_tab=active_tab
        )
    except Exception as exc:  # noqa: BLE001 - diagnostics must never raise
        claim = f"<binder error {exc!r}>"
    return f"chord={chord!r} active_tab={tab_desc} {claim}"


def redispatch_unhandled_key_to_global_handler(widget, event: QKeyEvent) -> bool:
    """Hand a key a tab shell could not use back to the global handler.

    A tab that forwards keys to its canvas is a focus owner, not a key sink:
    once focus lands on it, ``should_route_globally`` no longer sends anything
    to the global handler for it, so a key the canvas ignores (loupe movement
    W/A/S/D/Q/E, Space preview) would die in the shell. Returns True when the
    event was re-dispatched (and accepted).

    Chord-owning keys are NOT re-dispatched: a chord the active tab's binder
    installed belongs to the shortcut map, never to the loupe handler.
    """
    event_type = event.type()
    if event_type == QEvent.Type.KeyPress:
        signal_name = "global_keyboard_press_event_signal"
    elif event_type == QEvent.Type.KeyRelease:
        signal_name = "global_keyboard_release_event_signal"
    else:
        return False
    try:
        event_handler = getattr(widget.window(), "event_handler", None)
    except Exception:
        return False
    keyboard_handler = getattr(event_handler, "keyboard_handler", None)
    if keyboard_handler is None:
        return False
    if active_tab_shortcut_owns_event(event):
        return False
    try:
        if not keyboard_handler.should_route_globally(event, widget):
            return False
    except Exception:
        return False
    emit = getattr(getattr(event_handler, signal_name, None), "emit", None)
    if emit is None:
        return False
    emit(event)
    event.accept()
    return True


class GlobalKeyboardHandler:
    OVERLAY_MOVEMENT_KEYS = {
        Qt.Key.Key_Q,
        Qt.Key.Key_E,
        Qt.Key.Key_W,
        Qt.Key.Key_A,
        Qt.Key.Key_S,
        Qt.Key.Key_D,
    }

    def __init__(self, store, presenter_provider, movement_controller, keyboard_state):
        self.store = store
        self._presenter_provider = presenter_provider
        self._movement_controller = movement_controller
        self.keyboard_state = keyboard_state

    @property
    def presenter(self):
        return self._presenter_provider()

    @staticmethod
    def _should_log_suppressed_reason(reason: str) -> bool:
        return reason not in {
            "ignored_untracked",
            "overlay_auto_repeat",
            "space_auto_repeat",
            "stray_release",
            "space_stray_release",
        }

    def should_route_globally(self, event: QKeyEvent, watched_obj: QObject) -> bool:
        """Decide whether a key event belongs to the global handler.

        Shift/Space ordering contract: Shift is deliberately NOT a managed
        key in ``KeyboardStateService`` — modifier state is sampled from
        ``event.modifiers()`` at gesture time (see magnifier
        ``_matches_side_preview``), never tracked as held state. Preview
        *begin* is owned solely by the magnifier gesture bindings
        (space + shift + click → ``preview.start_side_preview``); this
        handler never begins preview — it only tracks ``space_bar_pressed``
        and deactivates single-image mode on Space release. Pressing Shift
        before Space is therefore equivalent to pressing it after: the
        Shift press itself is untracked by design, and only the
        space-held + shift-modifier + click combination matters.
        The Shift branch below preserves press/release routing symmetry
        while space is held (so the global release path still sees the
        matching release), not because Shift carries state here.
        """
        active_tab = get_shared_tab_registry().get_active_tab()
        if active_tab is not None and active_tab.owns_widget(watched_obj):
            return False

        focus = focused_widget()
        if active_tab is not None and active_tab.owns_widget(focus):
            return False
        if widget_accepts_text_keys(focus):
            return False

        key = event.key()
        if key in self.OVERLAY_MOVEMENT_KEYS:
            return True
        if key == Qt.Key.Key_Space:
            return True
        if key == Qt.Key.Key_Shift and self.store.viewport.interaction_state.space_bar_pressed:
            return True
        return False

    def handle_key_press(self, event: QKeyEvent) -> None:
        key_code = event.key()
        is_overlay_key = key_code in self.OVERLAY_MOVEMENT_KEYS
        result = self.keyboard_state.press(key_code, is_auto_repeat=event.isAutoRepeat())
        if not result.applied:
            if not self._should_log_suppressed_reason(result.reason):
                return
            logger.warning(
                "Suppressed global key press: key=%s auto=%s reason=%s",
                int(key_code),
                bool(event.isAutoRepeat()),
                result.reason,
            )
            event.accept()
            return
        self.store.emit_viewport_change("interaction")

        self._movement_controller.start()

    def preview_controller(self):
        """The preview lifecycle owner, resolved through the image-canvas feature.

        ``self.presenter`` here is the active tab's presenter; the
        ``image_label_handler`` that owns the preview controller is attached to
        the tab's IMAGE-CANVAS presenter (the feature the tab builds its canvas
        lifecycle on), which the tab exposes as the ``image_canvas`` feature.
        Reading only the tab presenter made every global restore a no-op
        (``[preview] global release: no preview controller``, measured live
        2026-10-22 — the release path reported success while the preview stayed
        on screen).
        """
        owners = [self.presenter]
        try:
            from events.app_event.common import get_image_canvas_presenter

            owners.append(get_image_canvas_presenter(self.presenter))
        except Exception:  # noqa: BLE001 - resolution must never raise
            pass
        for owner in owners:
            if owner is None:
                continue
            handler = getattr(owner, "image_label_handler", None)
            preview = getattr(handler, "preview", None)
            if preview is not None:
                return preview
        return None

    def restore_preview_if_active(self, reason: str) -> bool:
        """End an active Shift+Space preview from the global release path.

        The gesture begins on a canvas click, but once the tab shell owns the
        keyboard focus the matching Space/Shift RELEASE is delivered here, not
        to the canvas handler that used to restore it — so the preview stayed
        on screen after the keys were let go (measured live 2026-10-22, owner
        report). The controller is feature-neutral and restores its own
        snapshot, so calling it from this path is the same contract as the
        canvas path's ``preview.restore()``.
        """
        preview = self.preview_controller()
        if preview is None:
            logger.debug("[preview] global release: no preview controller")
            return False
        if not bool(getattr(preview, "is_active", False)):
            logger.debug("[preview] global release: no active preview (%s)", reason)
            return False
        try:
            preview.restore()
        except Exception:
            logger.exception("global preview restore failed (%s)", reason)
            return False
        return True

    def handle_key_release(self, event: QKeyEvent) -> None:
        key_code = event.key()
        if key_code == Qt.Key.Key_Shift:
            # Shift is deliberately NOT a managed key (see
            # ``should_route_globally``); its release only has to end an
            # active preview.
            self.restore_preview_if_active("shift_released")
            return
        result = self.keyboard_state.release(key_code, is_auto_repeat=event.isAutoRepeat())
        if not result.applied:
            if not self._should_log_suppressed_reason(result.reason):
                return
            logger.warning(
                "Suppressed global key release: key=%s auto=%s reason=%s",
                int(key_code),
                bool(event.isAutoRepeat()),
                result.reason,
            )
            event.accept()
            return
        self.store.emit_viewport_change("interaction")

        if (
            key_code in self.OVERLAY_MOVEMENT_KEYS
            and not self.keyboard_state.has_active_overlay_keys()
        ):
            self._movement_controller.stop()

        if key_code != Qt.Key.Key_Space:
            return

        # Restore first and unconditionally: the preview mode is independent of
        # single-image mode, and the release must undo it on whichever path it
        # arrives.
        self.restore_preview_if_active("space_released")

        if self.store.viewport.view_state.showing_single_image_mode == 0:
            return

        sessions = getattr(get_main_controller(self.presenter), "sessions", None)
        if sessions is not None:
            sessions.deactivate_single_image_mode()