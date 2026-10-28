from __future__ import annotations

import logging
import os
import time
import traceback

from PySide6.QtCore import QTimer
from PySide6.QtGui import QCursor, QFont
from PySide6.QtWidgets import QApplication

from core.constants import AppConstants
from core.log_names import APP_LOGGER_NAME
from sli_ui_toolkit.i18n import tr
from sli_ui_toolkit.managers import DecisionJournal

logger = logging.getLogger(APP_LOGGER_NAME)

_INTERP_LABEL_KEYS: dict[str, str] = {
    "NEAREST": "magnifier.nearest_neighbor",
    "BILINEAR": "magnifier.bilinear",
    "BICUBIC": "magnifier.bicubic",
    "LANCZOS": "magnifier.lanczos",
    "EWA_LANCZOS": "magnifier.ewa_lanczos",
}


def _apply_interpolation_method(store, method: str) -> bool:
    """Persist ``render_config.interpolation_method`` through the Dispatcher.

    ``SetInterpolationMethodAction`` → ``dispatch(scope="viewport")`` →
    ``ImageRenderConfigReducer`` is the only write that also takes the lock,
    records undo, notifies subscribers and emits ``viewport`` (that emit
    re-renders the loupe). The ``setattr`` fallback it replaces skipped all of
    it (``task-transient-interp-setattr-2026-10-28``); an unappliable pick now
    leaves the value as is and logs instead of writing in place.
    """
    get_dispatcher = getattr(store, "get_dispatcher", None)
    try:
        dispatcher = get_dispatcher() if callable(get_dispatcher) else None
    except Exception:
        logger.warning("interpolation: get_dispatcher() raised; %r not applied", method, exc_info=True)
        return False
    if dispatcher is None:
        logger.warning("interpolation: no dispatcher; %r not applied, Store left as is", method)
        return False

    from core.state_management.appearance_actions import SetInterpolationMethodAction

    last_error: BaseException | None = None
    # Pure action: one retry costs a reducer run; a 2nd failure is a real defect.
    for _ in range(2):
        try:
            dispatcher.dispatch(SetInterpolationMethodAction(method=method), scope="viewport")
            return True
        except Exception as exc:  # a reducer error must not take the menu down
            last_error = exc
    logger.error(
        "interpolation: %r not applied after 2 dispatches: %s", method, last_error, exc_info=last_error
    )
    return False


def _design_item_metrics(
    item_height: int, item_font: QFont, factor: float
) -> tuple[int, QFont]:
    """Convert live (scale-resolved) combo metrics back to design values.

    ``SimpleOptionsFlyout.set_row_height``/``set_row_font`` take design px /
    a design font and scale them exactly once; ``getItemHeight``/
    ``getItemFont`` return the combo's live (already scaled) metrics, so the
    factor is divided out here to keep the flyout rows ~factor, not
    ~factor^2.
    """
    height = max(1, round(int(item_height) / factor)) if factor else item_height
    font = QFont(item_font)
    if font.pixelSize() > 0:
        font.setPixelSize(max(1, round(font.pixelSize() / factor)))
    elif font.pointSizeF() > 0:
        font.setPointSizeF(font.pointSizeF() / factor)
    return height, font


class InterpolationFlyoutController:
    """Options list for ``combo_interpolation`` (the loupe's resampling pick).

    Decisions are journalled (``DecisionJournal("interp-flyout")``, flag-gated
    like every other flyout journal: ``SLI_FLYOUT_DEBUG`` /
    ``IMGSLI_FLYOUT_DEBUG`` / ``FLYOUT_DEBUG``). Why: this dropdown is a bare
    ``SimpleOptionsFlyout`` — it has no ``AnchoredFlyoutAutoHide``, so nothing
    in ``log.txt`` recorded when it opened or closed; the magnifier settings
    panel's journal only ever saw it as a *linked child* (``still-linked``).
    On 2026-10-27 a close-time question could not be answered from the log at
    all, and "it never opened" was inferred from the absence of lines — a
    wrong conclusion drawn from an instrument that could not see the event.
    ``show`` and ``closed`` (emitted by ``SimpleOptionsFlyout.hideEvent`` on
    every close path) now bracket the lifetime with ``after=<ms>``.
    """

    def __init__(self, manager, widget):
        self.manager = manager
        self.widget = widget
        self._journal = DecisionJournal("interp-flyout")
        #: ``time.monotonic()`` of the journalled show; None while closed.
        self._shown_at: float | None = None

    def _note(self, what: str, detail: str = "") -> None:
        try:
            pos = QCursor.pos()
            detail = f"{detail} cursor={pos.x()},{pos.y()}".strip()
        except Exception:
            pass
        self._journal.note(what, detail)

    def _note_shown(self, combo) -> None:
        """Journal the confirmed open (``show_below`` can toggle-close instead)."""
        flyout = getattr(self.manager.host, "_interp_flyout", None)
        try:
            visible = bool(flyout is not None and flyout.isVisible())
        except RuntimeError:
            visible = False
        if not visible:
            # Hidden right after show_below — the same-anchor toggle branch.
            # Worth a line of its own: a "show" followed by an unpaired
            # "closed" is exactly how this reads in a post-mortem otherwise.
            self._shown_at = None
            self._note("show:noop", "flyout not visible after show_below (toggle?)")
            return
        self._shown_at = time.monotonic()
        self._note("show", f"anchor={type(combo).__name__}")

    def _elapsed_detail(self) -> str:
        started = self._shown_at
        self._shown_at = None
        if started is None:
            return "unpaired"
        return f"after={int((time.monotonic() - started) * 1000)}ms"

    def _instrument_hide(self, flyout) -> None:
        """Journal who *asks* for the hide, not only where ``hideEvent`` lands.

        The flyout fades out: ``hide()`` starts the animation and
        ``hideEvent``/``closed`` arrive a frame later from
        ``animation.on_hide_fade_finished``. The stack at ``closed`` therefore
        ends in the fade completion and the real caller is already gone —
        measured 2026-10-27, a 198 ms lifetime whose recorded origin was
        ``on_closed <- hideEvent <- on_hide_fade_finished``, i.e. no cause at
        all. Wrapping ``hide`` at entry keeps the causal stack. Diagnostic
        only, and only with the journal flag on (a production close does no
        stack work).
        """
        if not self._debug_enabled():
            return
        if getattr(flyout, "_interp_journal_wrapped", False):
            return
        original_hide = flyout.hide

        def _hide_with_origin(*args, **kwargs):
            self._note("hide:requested", f"origin={self._close_origin()}")
            return original_hide(*args, **kwargs)

        flyout.hide = _hide_with_origin
        flyout._interp_journal_wrapped = True

    def _debug_enabled(self) -> bool:
        """Mirror of ``flyout_timer_service._timer_debug_enabled`` (journal gate)."""
        return any(
            os.environ.get(var, "").strip().lower()
            not in ("", "0", "false", "no", "off")
            for var in ("SLI_FLYOUT_DEBUG", "IMGSLI_FLYOUT_DEBUG", "FLYOUT_DEBUG")
        )

    def _close_origin(self) -> str:
        """App/toolkit frames that actually hid the flyout (innermost last).

        ``closed`` is emitted synchronously from ``SimpleOptionsFlyout.hideEvent``,
        so the live stack still carries the *cause*: a row pick
        (``_SimpleRow._on_row_clicked``), a ``FlyoutManager`` dismiss, a
        ``BaseFlyout`` focus/outside handler, or a host call. Without it a
        self-closing dropdown can only be blamed by correlating unrelated log
        lines after the fact (measured 2026-10-27: 177 ms lifetime, cursor
        stationary on the same pixel, no dispatch — cause unknown).
        Gated on the journal's own env flags; keep the names in sync with
        ``flyout_timer_service._timer_debug_enabled``.
        """
        if not self._debug_enabled():
            return ""
        frames: list[str] = []
        for frame in traceback.extract_stack()[:-1]:
            filename = frame.filename
            if "/sli_ui_toolkit/" in filename:
                frames.append(
                    f"toolkit:{os.path.basename(filename)}:{frame.lineno}:{frame.name}"
                )
            elif "/Improve-ImgSLI/src/" in filename:
                frames.append(
                    f"app:{os.path.basename(filename)}:{frame.lineno}:{frame.name}"
                )
        return " <- ".join(reversed(frames[-6:]))

    def _close_context(self) -> str:
        parts: list[str] = []
        try:
            focused = QApplication.focusWidget()
            parts.append(
                f"focus={type(focused).__name__ if focused is not None else 'None'}"
            )
        except Exception:
            pass
        try:
            under = QApplication.widgetAt(QCursor.pos())
            parts.append(
                f"under={type(under).__name__ if under is not None else 'None'}"
            )
        except Exception:
            pass
        origin = self._close_origin()
        if origin:
            parts.append(f"origin={origin}")
        return " ".join(parts)

    def toggle(self):
        host = self.manager.host
        if host._interp_popup_open:
            self.close()
            return
        self.show()

    def open(self):
        """Open the options list (never toggle-close). Find Action path."""
        self.show()

    def show(self):
        from sli_ui_toolkit.widgets import SimpleOptionsFlyout

        # Find Action / cold open: combo lives on magnifier_settings_panel,
        # which is hidden until the magnifier is on — same idea as
        # FontSettingsController._ensure_text_settings_chrome.
        self.ensure_panel_visible()

        host = self.manager.host
        if host._interp_flyout is None:
            host._interp_flyout = SimpleOptionsFlyout(host.parent_widget)
            host._interp_flyout.closed.connect(self.on_closed)
            host._interp_flyout.item_chosen.connect(self.apply_choice)
            self._instrument_hide(host._interp_flyout)
            # combo_interpolation lives inside magnifier_settings_flyout's
            # own content -- link them so AnchoredFlyoutAutoHide (see its
            # MagnifierSettingsHoverController) treats the cursor moving
            # onto this dropdown as still "inside", not a reason to
            # auto-hide the settings panel out from under an in-progress
            # pick. See sli_ui_toolkit's flyout_timer_service.py.
            settings_flyout = getattr(self.widget, "magnifier_settings_flyout", None)
            if settings_flyout is not None:
                from sli_ui_toolkit.managers import FlyoutManager

                FlyoutManager.get_instance().link(settings_flyout, host._interp_flyout)

        lang = host.store.settings.current_language
        method_keys = list(AppConstants.INTERPOLATION_METHODS_MAP.keys())
        labels = [
            tr(
                _INTERP_LABEL_KEYS.get(
                    key,
                    f"magnifier.{AppConstants.INTERPOLATION_METHODS_MAP[key].lower().replace(' ', '_')}",
                ),
                lang,
            )
            for key in method_keys
        ]

        try:
            target_key = getattr(
                host.store.viewport.render_config,
                "interpolation_method",
                AppConstants.DEFAULT_INTERPOLATION_METHOD,
            )
            if target_key not in method_keys:
                target_key = (
                    AppConstants.DEFAULT_INTERPOLATION_METHOD
                    if AppConstants.DEFAULT_INTERPOLATION_METHOD in method_keys
                    else method_keys[0]
                )
                # Repair of an out-of-map stored value (old settings file /
                # restored session); display-only when the write cannot land
                # -- see _apply_interpolation_method.
                _apply_interpolation_method(host.store, target_key)
            current_index = method_keys.index(target_key) if method_keys else 0
        except (AttributeError, ValueError, IndexError):
            current_index = 0

        item_height = 34
        from sli_ui_toolkit.managers import UiScale, ui_font

        item_font = ui_font()
        combo = getattr(self.widget, "combo_interpolation", None)
        if combo is not None:
            # getItemHeight/getItemFont return live (already scale-resolved)
            # metrics, while set_row_height/set_row_font below take design
            # values and scale them once — divide the factor back out, or the
            # rows end up ~factor^2 too big (same class of bug as
            # _SimpleRow._apply_label_style's double rebase).
            factor = UiScale.get_instance().factor()
            if hasattr(combo, "getItemHeight"):
                item_height = combo.getItemHeight()
            if hasattr(combo, "getItemFont"):
                item_font = combo.getItemFont()
            item_height, item_font = _design_item_metrics(
                item_height, item_font, factor
            )

        host._interp_flyout.set_row_height(item_height)
        host._interp_flyout.set_row_font(item_font)
        host._interp_flyout.populate(labels, current_index)

        if combo is not None:
            combo.setFlyoutOpen(True)

        # Already open (Find Action ensure_visible again): refresh rows only —
        # show_below would toggle-close on the same anchor.
        if (
            host._interp_popup_open
            and host._interp_flyout.isVisible()
            and getattr(host._interp_flyout, "_anchor_widget", None) is combo
        ):
            return

        def _do_show():
            if host._interp_flyout is not None and combo is not None:
                host._interp_flyout.show_below(combo)
                host._interp_popup_open = True
                self._note_shown(combo)

        QTimer.singleShot(0, _do_show)

    def index_for_data(self, data: object) -> int:
        method_keys = list(AppConstants.INTERPOLATION_METHODS_MAP.keys())
        try:
            return method_keys.index(data)
        except ValueError:
            return -1

    def choose_index(self, index: int) -> None:
        self.apply_choice(index)

    def choose_data(self, data: object) -> None:
        index = self.index_for_data(data)
        if index < 0:
            return
        self.apply_choice(index)

    def row_widget(self, index: int):
        host = self.manager.host
        flyout = getattr(host, "_interp_flyout", None)
        if flyout is None:
            return None
        getter = getattr(flyout, "row_widget", None)
        if callable(getter):
            return getter(index)
        layout = getattr(flyout, "_rows_layout", None)
        if layout is None:
            return None
        if not (0 <= index < max(0, layout.count() - 1)):
            return None
        item = layout.itemAt(index)
        return item.widget() if item is not None else None

    def apply_choice(self, idx: int):
        host = self.manager.host
        method_keys = list(AppConstants.INTERPOLATION_METHODS_MAP.keys())
        try:
            combo = getattr(self.widget, "combo_interpolation", None)
            if combo is not None and 0 <= idx < combo.count():
                combo.setCurrentIndex(idx)
                controller = getattr(host, "main_controller", None)
                if controller is not None:
                    if hasattr(controller, "on_interpolation_changed"):
                        controller.on_interpolation_changed(idx)
                    elif getattr(controller, "sessions", None) is not None:
                        controller.sessions.on_interpolation_changed(idx)
            elif 0 <= idx < len(method_keys) and getattr(host, "store", None) is not None:
                # No combo to drive (Find Action / headless host): the pick
                # lands in the Store only through the action, never in place.
                _apply_interpolation_method(host.store, method_keys[idx])
        finally:
            self.close()

    def close(self):
        host = self.manager.host
        if host._interp_flyout is not None:
            host._interp_flyout.hide()
        combo = getattr(self.widget, "combo_interpolation", None)
        if combo is not None:
            combo.setFlyoutOpen(False)
        host._interp_popup_open = False
        self._cancel_settings_auto_hide()

    def on_closed(self):
        host = self.manager.host
        combo = getattr(self.widget, "combo_interpolation", None)
        if combo is not None:
            combo.setFlyoutOpen(False)
        host._interp_popup_open = False
        self._cancel_settings_auto_hide()
        # ``closed`` fires from ``SimpleOptionsFlyout.hideEvent`` on EVERY close
        # path (item picked, outside click, Escape, host teardown), so this one
        # line brackets the dropdown's whole visible lifetime and names the
        # caller that ended it (``origin=``, when the journal flag is on).
        self._note("closed", f"{self._elapsed_detail()} {self._close_context()}".strip())

    def _cancel_settings_auto_hide(self) -> None:
        """Drop any pending hover-leave auto-hide on magnifier_settings_flyout.

        The dropdown opens well below the settings panel/toolbar, so by the
        time it closes (e.g. right after picking an item) the cursor is
        nowhere near either safe zone AnchoredFlyoutAutoHide checks -- its
        still-pending timer (scheduled by the earlier hover-leave onto the
        dropdown, deferred only while the dropdown itself stayed visible,
        see FlyoutManager.link() in show() above) would otherwise fire
        within its retry window and close the panel right out from under
        the selection. Cancelling here "pins" it open until the next real
        hover/click elsewhere re-establishes normal auto-hide.
        """
        hover = getattr(self.widget, "_magnifier_settings_hover", None)
        if hover is not None:  # always built with the widget (widget.py)
            hover.note_child_pick_closed()  # cancel + armed post-pick watch

    def has_focus_inside(self, new_widget) -> bool:
        if new_widget is None:
            return False
        host = self.manager.host
        for anchor in (getattr(self.widget, "combo_interpolation", None), host._interp_flyout):
            if anchor is None:
                continue
            parent = new_widget
            while parent is not None:
                if parent is anchor:
                    return True
                parent = parent.parent()
        # Focus moving *within the loupe unit* is not "focus left the dropdown".
        # ``closing.on_app_focus_changed`` sweeps transient UI through the
        # focus-aware owners registered here, and the magnifier button takes
        # focus on its own hover/lens cycle every ~150-200 ms (measured
        # 2026-10-27). With only combo+flyout known, that focus move read as a
        # departure and the sweep closed the just-opened list 10 ms after it
        # appeared:
        # ``hide:requested <- closing.py:_hide_transient_same_window_ui_now
        # <- transient_interpolation.close``, which is why the resampling list
        # lived ~180 ms (10 ms + the 160 ms fade) and could not be used.
        # Dismissal stays with the normal paths: outside press, Escape, row
        # pick, panel hide.
        unit_roots = tuple(
            root
            for root in (
                getattr(self.widget, "magnifier_group_container", None),
                getattr(self.widget, "magnifier_settings_panel", None),
                getattr(self.widget, "magnifier_settings_flyout", None),
                getattr(self.widget, "checkbox_widget", None),
            )
            if root is not None
        )
        for root in unit_roots:
            try:
                if new_widget is root or root.isAncestorOf(new_widget):
                    return True
            except RuntimeError:
                continue
        return False

    def ensure_panel_visible(self) -> None:
        """Show magnifier_settings_panel (sliders + ``combo_interpolation`` row).

        Shared by the interpolation flyout's cold-open path and by the
        magnifier slider Find Action rows, which anchor to the same panel.
        """
        widget = self.widget
        panel = getattr(widget, "magnifier_settings_panel", None)
        combo = getattr(widget, "combo_interpolation", None)
        if self._is_alive_and_visible(panel) and self._is_alive_and_visible(combo):
            return

        opener = getattr(widget, "open_magnifier_settings_flyout", None)
        if callable(opener):
            opener()

        app = QApplication.instance()
        if app is not None:
            app.processEvents()

    @staticmethod
    def _is_alive_and_visible(widget) -> bool:
        if widget is None:
            return False
        try:
            return bool(widget.isVisible())
        except RuntimeError:
            return False