import logging
import time

from PySide6.QtCore import QPointF

from ui.host_debug import transient_debug
from ui.managers.transient_ui_parts import PopupClosingController
from core.log_names import APP_LOGGER_NAME
logger = logging.getLogger(APP_LOGGER_NAME)

# How long a negative lookup stays cached for the same (active, tiers) key.
# Suppresses focusChanged flood (10ms) while staying on the bootstrap-
# default session, but still retries after a few seconds if a tab's widget
# becomes available later while staying on the same session (lazy page
# creation).  # ALLOWED
_NEGATIVE_CACHE_TTL_S = 5.0

class TransientUIManager:
    def __init__(self, host):
        self.host = host
        self._services: dict[str, object | None] = {}
        self._service_ids = {
            "flyouts": "unified_flyout_controller",
            "interpolation": "interpolation_flyout_controller",
            "font_settings": "font_settings_flyout_controller",
            "panel_visibility": "panel_visibility_controller",
            "panel_instances": "panel_instances_controller",
        }
        # Negative lookup cache: (active, tiers) -> timestamp of last miss.
        # Repeated focusChanged / eventFilter polls while staying on the same
        # session (e.g. the bootstrap-default session) don't re-probe the
        # registry and spam DEBUG logs on every tick. Cleared automatically
        # when the active session type or discovered tiers change, and expires
        # after _NEGATIVE_CACHE_TTL_S so a widget that becomes available later
        # while staying on the same session is retried.  # ALLOWED
        self._service_miss_session: dict[str, tuple[tuple[str | None, frozenset[str]], float]] = {}
        self.closing = PopupClosingController(self)
        self._transient_shutdown_latched = False

    def shutdown(self) -> None:
        """Latch the transient controllers off and tear their wiring down.

        Called from the host window close path (``MarkShuttingDownStep`` ->
        ``UIManager.shutdown``) *before* the steps that hide/close windows,
        because those steps still emit one last burst of focus events. While
        the controllers stayed live, each burst event ran the full reaction
        chain — ``hide()`` on FocusOut, focus back to the button, a FocusIn
        that re-armed the hover timer, the flyout re-opening — one round trip
        per loop turn, i.e. the owner's post-close
        ``[magnifier-visibility] btn_magnifier event=9`` spam (2026-10-26).

        Latched first, so a controller built from a late lookup is inert too;
        then each service gets its own ``shutdown`` (or a bare ``teardown``
        if it has none).
        """
        if getattr(self, "_transient_shutdown_latched", False):
            return
        self._transient_shutdown_latched = True
        for attr, service in list(self._services.items()):
            shutdown = getattr(service, "shutdown", None)
            teardown = getattr(service, "teardown", None)
            try:
                if callable(shutdown):
                    shutdown()
                elif callable(teardown):
                    teardown()
            except Exception:
                logger.debug(
                    "transient service %s failed to shut down", attr, exc_info=True
                )
        self._services.clear()

    def _miss_key(self, registry) -> tuple[str | None, frozenset[str]]:
        """Cache key for negative service lookups (public API first).

        Active session type comes from the public ``get_active_tab()``;
        discovery tiers have no public accessor, so they are read via a
        guarded ``getattr`` with a fail-open empty default (see
        ``tests/.../test_chrome_lifetime.py``).
        """
        try:
            tab = registry.get_active_tab()
            active = getattr(tab, "session_type", None) if tab is not None else None
        except Exception:
            active = None
        try:
            tiers = frozenset(getattr(registry, "_discovered_tiers", None) or ())
        except Exception:
            tiers = frozenset()
        return (active, tiers)

    def _get_service(self, attr: str):
        """Lazily resolve a tab-owned service."""
        if getattr(self, "_transient_shutdown_latched", False):
            # The window is closing: never resurrect a controller (it would be
            # born un-wired but its registry probe can re-discover tabs).
            return None
        cached = self._services.get(attr)
        if cached is not None:
            return cached
        from tabs.registry import TabRegistry

        registry = TabRegistry()
        miss_key = self._miss_key(registry)
        # If we already probed and found nothing for this exact active
        # session + discovery state, return cached miss without re-discovering
        # or logging — but expire after TTL so a later widget creation while
        # staying on the same session is retried.
        cached_miss = self._service_miss_session.get(attr)
        if cached_miss is not None and cached_miss[0] == miss_key:
            if (time.monotonic() - cached_miss[1]) < _NEGATIVE_CACHE_TTL_S:
                return None
            # TTL expired — fall through to re-probe
            self._service_miss_session.pop(attr, None)
        service_id = self._service_ids[attr]
        transient_debug("resolving service '%s' (attr=%s)", service_id, attr)
        registry.discover()
        service = registry.create_startup_service(service_id, self)
        if service is not None:
            self._services[attr] = service
            self._service_miss_session.pop(attr, None)
            transient_debug("'%s' → resolved: %s", service_id, type(service).__name__)
            # panel_visibility (btn_magnifier) and panel_instances
            # (btn_magnifier_instances) are one toolbar group -- both
            # controllers install event filters on their own button in
            # __init__, so whichever one never gets touched never wires its
            # button at all (no hover, no focus, nothing). panel_visibility
            # happens to get warmed up incidentally via the magnifier Find
            # Action registration (actions.py:_contribute_magnifier_visibility_flyout),
            # but panel_instances has no equivalent warmup path and stays
            # unconstructed -- and thus its button stays completely inert --
            # until the magnifier is toggled on at least once. Resolve the
            # sibling eagerly so both are always wired together.
            _SIBLING = {"panel_visibility": "panel_instances", "panel_instances": "panel_visibility"}
            sibling = _SIBLING.get(attr)
            if sibling is not None and self._services.get(sibling) is None:
                self._get_service(sibling)
        else:
            self._service_miss_session[attr] = (miss_key, time.monotonic())
            transient_debug("'%s' → None (deferred)", service_id)
        return service

    def __getattr__(self, name: str):
        if name in self._service_ids:
            return self._get_service(name)
        raise AttributeError(name)

    @property
    def unified_flyout(self):
        return self.host.unified_flyout

    @property
    def font_settings_flyout(self):
        return self.host.font_settings_flyout

    @font_settings_flyout.setter
    def font_settings_flyout(self, value):
        self.host.font_settings_flyout = value

    def mark_font_popup_closed(self):
        self.host._font_popup_open = False

    def show_flyout(self, image_number: int):
        flyouts = self.flyouts
        if flyouts is not None:
            flyouts.show_flyout(image_number)

    def sync_flyout_combo_status(self):
        flyouts = self.flyouts
        if flyouts is not None:
            flyouts.sync_flyout_combo_status()

    def toggle_interpolation_flyout(self):
        interpolation = self.interpolation
        if interpolation is not None:
            interpolation.toggle()

    def show_interpolation_flyout(self):
        interpolation = self.interpolation
        if interpolation is not None:
            interpolation.show()

    def apply_interpolation_choice(self, idx: int):
        interpolation = self.interpolation
        if interpolation is not None:
            interpolation.apply_choice(idx)

    def close_interpolation_flyout(self):
        interpolation = self.interpolation
        if interpolation is not None:
            interpolation.close()

    def on_interpolation_flyout_closed_event(self):
        interpolation = self.interpolation
        if interpolation is not None:
            interpolation.on_closed()

    def toggle_font_settings_flyout(self, anchor_widget=None):
        font_settings = self.font_settings
        if font_settings is not None:
            font_settings.toggle(anchor_widget=anchor_widget)

    def show_font_settings_flyout(self, anchor_widget=None):
        font_settings = self.font_settings
        if font_settings is not None:
            font_settings.show(anchor_widget=anchor_widget)

    def hide_font_settings_flyout(self):
        font_settings = self.font_settings
        if font_settings is not None:
            font_settings.hide()

    def repopulate_flyouts(self):
        flyouts = self.flyouts
        if flyouts is not None:
            flyouts.repopulate_flyouts()

    def on_font_changed(self):
        font_settings = self.font_settings
        if font_settings is not None:
            font_settings.on_font_changed()

    def on_flyout_closed(self, image_number: int):
        flyouts = self.flyouts
        if flyouts is not None:
            flyouts.on_flyout_closed(image_number)

    def on_unified_flyout_closed(self):
        flyouts = self.flyouts
        if flyouts is not None:
            flyouts.on_unified_flyout_closed()

    def event_filter(self, watched, event):
        panel_visibility = self._services.get("panel_visibility")
        if panel_visibility is not None and panel_visibility.event_filter(watched, event):
            return True
        panel_instances = self._services.get("panel_instances")
        if panel_instances is not None:
            return panel_instances.event_filter(watched, event)
        return False

    def close_all_flyouts_if_needed(self, global_pos: QPointF):
        self.closing.close_all_flyouts_if_needed(global_pos)

    def hide_transient_same_window_ui(self, *, reason: str = "transient_ui_manager"):
        self.closing.hide_transient_same_window_ui(reason=reason)

    def on_app_focus_changed(self, old_widget, new_widget):
        # Per-instance latch, same shape as UIManager._in_focus_changed: the
        # process-global guard (``begin_transient_sweep``, claimed by the
        # QApplication.focusChanged slot) already drops a sweep started
        # anywhere else in the process; this one drops a direct re-entry into
        # the same manager before any logging happens.
        if getattr(self, "_in_focus_changed", False):
            return
        self._in_focus_changed = True
        try:
            self.closing.on_app_focus_changed(old_widget, new_widget)
        finally:
            self._in_focus_changed = False
