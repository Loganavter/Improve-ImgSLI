"""The four live-mutation verbs, mixed into ``ControlHandlers``.

``open_file`` / ``ui_press`` / ``open_properties`` / ``set_setting`` plus the
helpers and constants only they use. Moved out of ``handlers.py`` unchanged
(bodies, signatures and return shapes are verbatim): ``handlers.py`` keeps the
frozen method table and the read/route verbs, this module owns the live-input
and live-dialog seams.

Two helpers, ``_pause`` and ``show_properties_dialog``, are resolved through
:mod:`core.control.handlers` at call time rather than called directly:
``tests/devtools/test_control_verbs.py`` monkeypatches them *on that module*
(the seam that existed before the move), and ``handlers`` re-exports both. One
patch point, no behaviour change.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, NamedTuple

from . import elements as element_inventory
from .discovery import MethodError
from .drop_routing import MEDIA_VIDEO, accepts_paths, media_kind, open_file_into

#: The only keys ``set_setting`` writes. A whitelist (not "anything QSettings
#: holds"): a control client must not be able to rewrite arbitrary app config.
#: ``theme``/``language`` keep their dedicated verbs (see
#: ``DEDICATED_SETTING_VERBS``) — one home per concern.
SETTING_WHITELIST: frozenset[str] = frozenset({"rhi_backend"})

#: Settings that already have a verb of their own; ``set_setting`` refuses them
#: by naming that verb instead of silently accepting a second write path.
DEDICATED_SETTING_VERBS: dict[str, str] = {
    "theme": "set_theme",
    "language": "set_language",
}

#: Render backends ``rhi_backend`` accepts (the app's own choice list).
VALID_RHI_BACKENDS: tuple[str, ...] = ("opengl", "vulkan")

#: Longest hold ``ui_press`` honours (ms) — a parked press never turns into a
#: multi-minute block inside one socket request.
MAX_HOLD_MS = 5000


class _HeldPress(NamedTuple):
    """A press parked by ``ui_press(release=false)``, awaiting its release."""

    element_id: str
    widget: Any
    pos: Any


def _clamp_hold_ms(value: Any) -> int:
    """``hold_ms`` as an int inside ``0..MAX_HOLD_MS`` (garbage reads as 0)."""
    try:
        number = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, min(MAX_HOLD_MS, number))


def _widget_alive(widget: Any) -> bool:
    """False when Qt already deleted *widget* (a HUD/button that went away)."""
    try:
        from shiboken6 import isValid

        return bool(isValid(widget))
    except Exception:
        return True


def _send_mouse(widget: Any, pos: Any, *, press: bool) -> None:
    """Deliver one real mouse press/release to *widget* at *pos* (in-process)."""
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    if press:
        QTest.mousePress(widget, Qt.MouseButton.LeftButton, pos=pos)
    else:
        QTest.mouseRelease(widget, Qt.MouseButton.LeftButton, pos=pos)


def _pause(milliseconds: int) -> None:
    """Pump the loop for a bounded hold (the same wait the resolver uses).

    ``QTest.qWait`` (not ``time.sleep``): the app has to stay live while a press
    is held, exactly as during ``resolve_element``'s retry budget. Split out so
    a test can observe the clamp without waiting it.
    """
    if milliseconds <= 0:
        return
    from PySide6.QtTest import QTest

    QTest.qWait(milliseconds)


def _handlers_module() -> Any:
    """The host module, resolved lazily (it imports this one at module level).

    Used for the two names that keep their historical patch point there — see
    the module docstring.
    """
    from . import handlers

    return handlers


def _open_file_hint(kind: str, wanted: str | None) -> str:
    """Actionable next step for a route that no tab accepted."""
    if kind == MEDIA_VIDEO:
        # Honest: there is no video intake in the app today (see
        # ``drop_routing.VIDEO_EXTENSIONS``) — naming a tab that takes videos
        # would pretend the file loaded.
        return (
            "this app has no video-file intake yet: the video editor edits "
            "recorded snapshots, it does not open a video file — pass an image "
            "file"
        )
    if wanted:
        return (
            "that tab did not accept the file; omit tab to let the router pick "
            "an accepting tab"
        )
    return (
        "open a tab that loads images (open_tab), then retry open_file"
    )


#: Live dialogs opened through ``open_properties``. A parentless top-level
#: widget is owned by Python, so without a reference the dialog would be
#: garbage-collected right after ``show()``; closed ones are pruned on the next
#: call (``WA_DeleteOnClose`` makes them invalid rather than lingering).
_property_dialogs: list[Any] = []


def show_properties_dialog(path: Path, parent: Any = None) -> str:
    """Show the app's own image-properties dialog for *path*; return its class.

    Uses the ``plugins.image_properties`` service + ``ImagePropertiesDialog``
    (the same objects the Image Compare context menu opens) but **shows** it
    instead of running ``open_image_properties_dialog``: that opener is modal
    (``exec()``), which on the control channel would hold the socket request —
    and its reply — open until a human closed the dialog. Non-modal keeps the
    verb answerable; the dialog is the app's, not a control-surface copy.
    """
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QWidget

    from plugins.image_properties.dialog import ImagePropertiesDialog
    from plugins.image_properties.service import build_image_properties
    from resources.translations import get_current_language
    from resources.translations import tr as app_tr

    global _property_dialogs
    _property_dialogs = [d for d in _property_dialogs if _widget_alive(d)]

    properties = build_image_properties(path=path, display_name=path.name)
    dialog = ImagePropertiesDialog(
        properties,
        # Parent only a real widget: the dialog's own ``parent`` is a
        # ``QWidget`` hand-off, and a duck-typed host must not be passed on.
        parent=parent if isinstance(parent, QWidget) else None,
        current_language=get_current_language() or "en",
        tr_func=app_tr,
    )
    dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
    dialog.show()
    dialog.raise_()
    if not dialog.isActiveWindow():
        # Guarded: a raw activateWindow() on an already-active window costs a
        # Wayland busy-cursor frame per call
        # (tests/contracts/test_no_unconditional_activation.py).
        dialog.activateWindow()
    _property_dialogs.append(dialog)
    return type(dialog).__name__


class LiveVerbMethodsMixin:
    """``open_file`` / ``ui_press`` / ``open_properties`` / ``set_setting``.

    ``self`` is a ``ControlHandlers`` (``_window`` / ``_store`` / ``_tabs`` /
    ``_tab_kinds`` / ``_run_action_id`` / ``_persist_setting`` come from there).
    """

    def open_file(self, params: dict[str, Any]) -> dict[str, Any]:
        """Load ONE file into a tab that accepts it; reject everything else.

        The receiving tab is discovered through its own
        ``accepts_drop``/``handle_drop`` (``drop_routing.open_file_into``) — the
        same path a drag-and-drop uses — so no concrete tab is named here
        (platform isolation, ``tests/contracts/test_platform_isolation.py``).
        Without a forced ``tab`` the candidate kinds are derived from the tabs
        themselves: the active tab first when it accepts the file, then every
        kind whose tab accepts it. A video names no receiver (the app has no
        video-file intake), so it fails by name instead of claiming a load that
        never happened.
        """
        raw = params.get("path")
        target = Path(str(raw)).expanduser() if raw else None
        if target is None or not target.is_file():
            raise MethodError(
                f"{target} is not an existing file",
                "pass an absolute (or ~-prefixed) path to an image file",
            )
        kind = media_kind(target)
        if not kind:
            raise MethodError(
                f"unsupported file type {target.suffix or target.name!r}",
                "pass an image or a video file "
                "(images: png, jpg, jpeg, bmp, tiff, tif, webp, jxl)",
            )
        wanted = str(params.get("tab") or "").strip() or None
        try:
            return open_file_into(
                target,
                wanted=wanted,
                candidates=self._file_candidates(target),
                tabs=self._tabs,
                kinds=self._tab_kinds(),
                run_action=self._run_action_id,
            )
        except ValueError as exc:
            raise MethodError(str(exc), _open_file_hint(kind, wanted)) from None

    def _file_candidates(self, path: Path) -> list[str]:
        """Tab kinds that accept *path*, the active one first (never a literal).

        Derived from the tabs' own ``accepts_drop`` (tab-agnostic host code):
        a tab that cannot take the file is never opened for it, which is also
        why a video opens nothing — no tab claims that intake.
        """
        accepting = [
            session_type
            for session_type, tab in self._tabs()
            if accepts_paths(tab, [path])
        ]
        active = self._active_kind()
        if active in accepting:
            accepting.remove(active)
            accepting.insert(0, active)
        return accepting

    def _active_kind(self) -> str | None:
        """The active workspace session's kind, or ``None`` (no live session)."""
        store = self._store()
        getter = getattr(store, "get_active_workspace_session", None)
        if not callable(getter):
            return None
        try:
            session = getter()
        except Exception:
            return None
        return getattr(session, "session_type", None)

    def open_properties(self, params: dict[str, Any]) -> dict[str, Any]:
        """Show the app's image-properties dialog for an existing file.

        Goes through ``plugins.image_properties`` (the service + dialog the
        Image Compare context menu uses, via ``show_properties_dialog``), never
        a control-surface re-implementation; the dialog is shown non-modally so
        this request can answer while it is on screen.
        """
        raw = params.get("path")
        target = Path(str(raw)).expanduser() if raw else None
        if target is None or not target.is_file():
            raise MethodError(
                f"{target} is not an existing file",
                "pass an absolute (or ~-prefixed) path to an existing image",
            )
        # Through the host module: its name is the historical patch point.
        dialog = _handlers_module().show_properties_dialog(target, self._window)
        return {"opened": True, "path": str(target), "dialog": dialog}

    def set_setting(self, params: dict[str, Any]) -> dict[str, Any]:
        """Write one whitelisted scalar setting and report what it replaced.

        Only ``SETTING_WHITELIST`` keys are reachable here; ``theme`` and
        ``language`` keep their dedicated verbs (the refusal names them), so
        there is exactly one write path per setting. The value is persisted
        through ``_persist_setting`` (the same QSettings scope the app reads)
        and pushed into the live store through its own dispatcher — ``applied``
        says whether the running app adopted it now (``rhi_backend`` only takes
        effect after a restart, so the store holds it and the app reports it
        next start), ``persisted`` whether the write landed.
        """
        key = str(params.get("key") or "").strip()
        if key in DEDICATED_SETTING_VERBS:
            verb = DEDICATED_SETTING_VERBS[key]
            raise MethodError(
                f"{key!r} has its own verb — set_setting does not write it",
                f"call {verb} instead; set_setting writes: "
                + ", ".join(sorted(SETTING_WHITELIST)),
            )
        if key not in SETTING_WHITELIST:
            raise MethodError(
                f"{key!r} is not a settable key",
                "settable keys: "
                + ", ".join(sorted(SETTING_WHITELIST))
                + " (theme/language use set_theme/set_language)",
            )
        value = str(params.get("value") or "").strip()
        if key == "rhi_backend":
            value = value.lower()
            if value not in VALID_RHI_BACKENDS:
                raise MethodError(
                    f"unknown rhi_backend {value!r}",
                    "use one of: " + ", ".join(VALID_RHI_BACKENDS),
                )
        previous = self._read_setting(key)
        self._persist_setting(key, value)
        return {
            "key": key,
            "value": value,
            "applied": self._apply_setting(key, value),
            "persisted": True,
            "previous": previous,
        }

    def _read_setting(self, key: str) -> str | None:
        """The persisted value of *key*, or ``None`` when unset/unreadable."""
        try:
            from PySide6.QtCore import QSettings

            raw = QSettings("improve-imgsli", "improve-imgsli").value(key)
        except Exception:
            return None
        text = str(raw).strip() if raw is not None else ""
        return text or None

    def _apply_setting(self, key: str, value: str) -> bool:
        """Push *key* into the live store through its own dispatcher.

        Redux dogma: state changes go through a dispatched action, never a
        store write. ``False`` means no live store/dispatcher could take it
        (headless test window, or a failed dispatch) — the value is still
        persisted, so the next start reads it.
        """
        store = self._store()
        getter = getattr(store, "get_dispatcher", None)
        dispatcher = getter() if callable(getter) else None
        if dispatcher is None or key != "rhi_backend":
            return False
        from core.state_management.settings_actions import SetRhiBackendAction

        try:
            dispatcher.dispatch(SetRhiBackendAction(value))
        except Exception:
            return False
        return True

    def _persist_setting(self, key: str, value: str) -> None:
        """Persist via the app's own QSettings scope (same keys Phase 1 wrote)."""
        try:
            from PySide6.QtCore import QSettings

            settings = QSettings("improve-imgsli", "improve-imgsli")
            settings.setValue(key, value)
            settings.sync()
        except Exception as exc:
            raise MethodError(
                f"could not persist {key}={value!r}: {exc}",
                "check that the app config directory is writable",
            )

    def ui_press(self, params: dict[str, Any]) -> dict[str, Any]:
        """Press an element's left mouse button, optionally leaving it down.

        ``release=False`` parks the press (a control that acts while held) and
        answers immediately; the next ``ui_press(id, release=True)`` releases
        **that** widget — the same instance, whatever id resolves — so a hold
        is never orphaned. Resolving an element on any other path releases a
        parked press first, and a widget Qt already deleted is simply forgotten
        (a destroyed widget has no pressed state left to clear). ``hold_ms`` is
        the wait applied *between* press and release of one press+release,
        clamped to ``0..MAX_HOLD_MS``; releasing an earlier hold reports ``0``
        because this call did not hold it. The wait pumps the loop with the same
        bounded ``QTest.qWait`` the element resolver uses, so a hold can never
        outlive its clamp.
        """
        request_release = params.get("release", True)
        if request_release is not None and not isinstance(request_release, bool):
            raise MethodError(
                "ui_press 'release' must be a boolean",
                "release=true presses and releases; release=false parks the press",
            )
        hold_ms = _clamp_hold_ms(params.get("hold_ms", 0))
        if request_release is False:
            target = element_inventory.resolve_element(
                self._registry(), params.get("id")
            )
            self._release_held_press()  # a second hold never leaks the first
            pos = target.rect.center()
            _send_mouse(target.widget, pos, press=True)
            self._held_press = _HeldPress(target.id, target.widget, pos)
            return {"pressed": target.id, "held_ms": 0, "released": False}
        return self._press_and_release(params, hold_ms)

    def _press_and_release(
        self, params: dict[str, Any], hold_ms: int
    ) -> dict[str, Any]:
        """The releasing half of :meth:`ui_press` (one press+release, or a hold)."""
        held, self._held_press = self._held_press, None
        try:
            target = element_inventory.resolve_element(
                self._registry(), params.get("id")
            )
        except MethodError:
            # An id that no longer resolves must not leave the parked press
            # down: release it, then report the resolution failure.
            self._release_held_press(held)
            raise
        if held is not None and _widget_alive(held.widget):
            _send_mouse(held.widget, held.pos, press=False)
            return {"pressed": held.element_id, "held_ms": 0, "released": True}
        pos = target.rect.center()
        _send_mouse(target.widget, pos, press=True)
        # Through the host module: its name is the historical patch point.
        _handlers_module()._pause(hold_ms)
        _send_mouse(target.widget, pos, press=False)
        return {"pressed": target.id, "held_ms": hold_ms, "released": True}

    def _release_held_press(self, held: _HeldPress | None = None) -> None:
        """Release a parked press (default: the current one) and forget it."""
        parked = self._held_press if held is None else held
        self._held_press = None
        if parked is None or not _widget_alive(parked.widget):
            return
        _send_mouse(parked.widget, parked.pos, press=False)


__all__ = ["LiveVerbMethodsMixin", "_pause", "show_properties_dialog"]
