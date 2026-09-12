import logging
import time

from PySide6.QtCore import QPointF

from ui.managers.transient_ui_parts import PopupClosingController
logger = logging.getLogger("ImproveImgSLI")

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

    def _get_service(self, attr: str):
        """Lazily resolve a tab-owned service."""
        cached = self._services.get(attr)
        if cached is not None:
            return cached
        from tabs.registry import TabRegistry

        registry = TabRegistry()
        active = registry._active_session_type
        tiers = frozenset(registry._discovered_tiers)
        miss_key = (active, tiers)
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
        logger.debug("[transient] resolving service '%s' (attr=%s)", service_id, attr)
        registry.discover()
        service = registry.create_startup_service(service_id, self)
        if service is not None:
            self._services[attr] = service
            self._service_miss_session.pop(attr, None)
            logger.debug("[transient] '%s' → resolved: %s", service_id, type(service).__name__)
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
            logger.debug("[transient] '%s' → None (deferred)", service_id)
        return service

    def invalidate_miss_cache(self) -> None:
        """Clear negative-cache so the next access re-probes the registry.

        Called implicitly via active-session change (handled in _get_service),
        but also exposed for TabRegistry deferred-load or manual invalidation.
        """
        self._service_miss_session.clear()

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
        self.closing.on_app_focus_changed(old_widget, new_widget)
