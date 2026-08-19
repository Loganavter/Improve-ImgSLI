"""Image-compare tab contract implementation.

Stages 1-10 of MIGRATION_PLAN.md.

The tab owns the page widget (``ImageCompareWidget``) and exposes the
tab-contract lifecycle. The host (``ui.main_window``) still creates
the primitive widgets (buttons, sliders, canvas) and calls
``widget.assemble(ui)`` once those primitives exist; long-term the
intent is to move primitive ownership into this tab as well.
"""

from __future__ import annotations

from pathlib import Path
import logging
from typing import TYPE_CHECKING

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QWidget

from tabs.contract import TabContext, TabContract, TabTransitionHint
from tabs.image_compare.use_cases import drag_drop, host_callbacks, persistence, registration

if TYPE_CHECKING:
    from tabs.image_compare.widget import ImageCompareWidget

logger = logging.getLogger("ImproveImgSLI")


class ImageCompareTab(TabContract):
    startup_tier = "bootstrap"

    def __init__(self):
        self._widget: "ImageCompareWidget | None" = None
        self._active_session_id: str | None = None

    @property
    def session_type(self) -> str:
        return "image_compare"

    @property
    def is_bootstrap_default(self) -> bool:
        # Not the bootstrap default — that role is reserved exclusively for
        # session_picker (core.store.INITIAL_WORKSPACE_SESSION_TYPE).
        # Legacy main-window shell services route by capability (the tab that
        # implements them answers), so image_compare needs no declared role.
        return False

    def create_default_session_data(self):
        from core.store_viewport import SessionData
        from tabs.image_compare.state.models import ImageSessionState, RenderCacheState

        return SessionData(image_state=ImageSessionState(), render_cache=RenderCacheState())

    @property
    def display_name(self) -> str:
        return "Image Compare"

    @property
    def icon(self) -> QIcon | None:
        from tabs.image_compare.icons import Icon, get_icon

        return get_icon(Icon.PHOTO)

    @property
    def resources_dir(self) -> Path | None:
        return Path(__file__).parent / "resources"

    @property
    def i18n_namespace(self) -> str | None:
        return "image_compare"

    def extra_i18n_roots(self) -> list[Path]:
        return [Path(__file__).parent / "plugins" / "video_editor" / "resources" / "i18n"]

    def localized_display_name(self, language: str) -> str:
        from sli_ui_toolkit.i18n import tr

        key = "image_compare.session_type"
        translated = tr(key, language)
        return translated if translated != key else self.display_name

    def create_page(self, parent: QWidget, context: TabContext) -> QWidget:
        from tabs.image_compare.widget import ImageCompareWidget
        from tabs.image_compare.first_frame_debug import ic_first_frame_debug_enabled

        self._widget = ImageCompareWidget(parent, context=context)
        if ic_first_frame_debug_enabled():
            logger.info(
                "[ic-page] create_page widget=%s",
                str(hex(id(self._widget)))[-6:],
            )
        return self._widget

    @property
    def widget(self) -> "ImageCompareWidget | None":
        return self._widget

    def assemble_host_page(self, ui) -> bool:
        if self._widget is None:
            return False
        widgets = getattr(ui, "legacy_tab_widgets", None)
        if widgets is None:
            widgets = {}
            ui.legacy_tab_widgets = widgets
        widgets[self.session_type] = self._widget
        from tabs.image_compare.first_frame_debug import ic_first_frame_debug_enabled
        from tabs.image_compare.ui.primitives import ImageComparePrimitivesFactory

        if ic_first_frame_debug_enabled():
            logger.info(
                "[ic-page] assemble_host_page widget=%s",
                str(hex(id(self._widget)))[-6:],
            )
        parent = getattr(ui, "main_window", None) or self._widget
        ImageComparePrimitivesFactory(self._widget, ui).build(parent)
        self._widget.image_label._ffd_primary = True
        if ic_first_frame_debug_enabled():
            logger.info(
                "[ic-page] canvas built widget=%s canvas=%s",
                str(hex(id(self._widget.image_label)))[-6:],
                str(hex(id(self._widget.image_label)))[-6:],
            )
        self._widget.assemble(ui)
        self._widget.image_label.set_drag_overlay_state(False)
        self._widget.drag_overlay.hide()
        self._widget.install_rating_wheel_handlers()
        self._create_magnifier_flyout(ui)
        return True

    def _create_magnifier_flyout(self, ui) -> None:
        """Create the magnifier visibility flyout — tab-owned, stored on host ui."""
        if getattr(ui, "magnifier_visibility_flyout", None) is not None:
            return  # already created
        from ui.widgets.magnifier_visibility_flyout import MagnifierVisibilityFlyout

        parent = getattr(ui, "main_window", None) or self._widget
        flyout = MagnifierVisibilityFlyout(parent)
        ui.magnifier_visibility_flyout = flyout
        self._connect_magnifier_flyout_buttons(flyout, ui)

    def _connect_magnifier_flyout_buttons(self, flyout, ui) -> None:
        """Connect magnifier visibility buttons to the store."""
        from ui.canvas_infra.scene.feature_state_api import (
            execute_feature_command,
            query_feature_state,
        )

        store = getattr(ui, "store", None) or (
            self._widget._context.store if self._widget else None
        )
        if store is None:
            return

        def _query(part: str) -> bool:
            state = query_feature_state(store, "magnifier", "active_state")
            if state is None:
                return True
            return bool(state.get(f"visible_{part}", True))

        flyout.btn_left.toggled.connect(
            lambda checked: execute_feature_command(
                store, "magnifier", "set_active_visibility_parts",
                left=not checked, center=_query("center"), right=_query("right"),
            )
        )
        flyout.btn_right.toggled.connect(
            lambda checked: execute_feature_command(
                store, "magnifier", "set_active_visibility_parts",
                left=_query("left"), center=_query("center"), right=not checked,
            )
        )
        flyout.btn_center.toggled.connect(
            lambda checked: execute_feature_command(
                store, "magnifier", "set_active_visibility_parts",
                left=_query("left"), center=not checked, right=_query("right"),
            )
        )

    def finalize_host_page(self, ui) -> None:
        if self._widget is None:
            return
        self._widget.toggle_edit_layout_visibility(False)
        self._widget.apply_icon_sizes()

    def apply_host_session_mode(self, ui, session_title: str | None = None) -> bool:
        if self._widget is None:
            return False
        self._widget.toggle_edit_layout_visibility(
            bool(self._widget.btn_file_names.isChecked())
        )
        return True

    def transition_hint(self) -> TabTransitionHint:
        # No cover mask: unified with multi_compare, both tabs rely on the
        # canvas's own startup placeholder for first-frame coverage. The mask
        # was dropped because on Wayland it blocks the QRhiWidget's first
        # expose/initialize while covering the stack (measured on multi_compare:
        # initialize delayed ~400ms until the mask force-released). First-frame
        # readiness is instead gated on the genuinely compositor-visible
        # present (see shared/rendering/first_frame_gate.py), and the
        # placeholder hides only after that frame is on screen.
        return TabTransitionHint(cover_on_enter=False)

    def on_activated(self, context: TabContext) -> None:
        session_id = self._resolve_active_session_id(context)
        if session_id is not None:
            self.on_active_session_changed(session_id, context)
        if self._widget is not None:
            self._widget.setFocus()
        from ui.actions.registry import get_action_registry

        self._register_actions(get_action_registry())

    def on_active_session_changed(self, session_id: str, context: TabContext) -> None:
        if session_id == self._active_session_id:
            return
        self._snapshot_into(context, self._active_session_id)
        self._active_session_id = session_id
        self._restore_from(context, session_id)

    def on_deactivated(self, context: TabContext) -> None:
        self._snapshot_into(context, self._active_session_id)

    def on_session_created(self, session_id: str, context: TabContext) -> None:
        # Slot is auto-allocated by SessionBlueprint.state_slots; nothing to do.
        return

    def on_session_closed(self, session_id: str, context: TabContext) -> None:
        if self._active_session_id == session_id:
            self._active_session_id = None

    def _resolve_active_session_id(self, context: TabContext) -> str | None:
        store = getattr(context, "store", None)
        if store is None:
            return None
        try:
            session = store.get_active_workspace_session()
        except Exception:
            return None
        if session is None or getattr(session, "session_type", None) != self.session_type:
            return None
        return getattr(session, "id", None)

    def _snapshot_into(self, context: TabContext, session_id: str | None) -> None:
        persistence.snapshot_into(self, context, session_id)

    def _restore_from(self, context: TabContext, session_id: str | None) -> None:
        persistence.restore_from(self, context, session_id)

    def serialize_session(self, session_id: str, context: TabContext) -> dict | None:
        return persistence.serialize_session(self, session_id, context)

    def collect_pixel_cache_sources(self, session_id: str, context: TabContext) -> dict:
        return persistence.collect_pixel_cache_sources(self, session_id, context)

    def deserialize_session(self, session_id: str, data: dict, context: TabContext) -> None:
        persistence.deserialize_session(self, session_id, data, context)

    def rehydrate_session(self, session_id: str, context: TabContext) -> None:
        persistence.rehydrate_session(self, session_id, context)

    def accepts_drop(self, paths: list[Path]) -> bool:
        return drag_drop.accepts_drop(paths)

    def handle_drop(self, paths: list[Path], hint: dict | None = None) -> bool:
        return drag_drop.handle_drop(self, paths, hint)

    def _register_settings(self, registry) -> None:
        registration.register_settings(self, registry)

    def _register_actions(self, registry) -> None:
        registration.register_actions(self, registry)

    def _resync_action_shortcuts(self) -> None:
        registration.resync_action_shortcuts(self)

    def create_main_window_feature(self, feature_id: str, **kwargs):
        if feature_id != "image_canvas":
            return None
        from tabs.image_compare.presenters.image_canvas.presenter import (
            ImageCanvasPresenter,
        )

        return ImageCanvasPresenter(
            kwargs["store"],
            kwargs["main_controller"],
            self._widget,
            kwargs["main_window_app"],
        )

    def create_service(self, service_id: str, *args, **kwargs):
        from tabs.image_compare.service_factory import create_service as _create

        return _create(self, service_id, *args, **kwargs)

    def get_canvas_geometry_provider(self):
        if self._widget is None:
            return None
        from tabs.image_compare.canvas_geometry_provider import (
            ImageCompareCanvasGeometryProvider,
        )

        return ImageCompareCanvasGeometryProvider(self._canvas_label)

    def _canvas_label(self):
        return host_callbacks.canvas_label(self)

    def _clear_transient_text_focus(self, focused_widget) -> bool:
        return host_callbacks.clear_transient_text_focus(self, focused_widget)

    def _sync_interpolation_combo_state(
        self, count: int, current_index: int, text: str, items: list[str]
    ) -> bool:
        return host_callbacks.sync_interpolation_combo_state(
            self, count, current_index, text, items
        )

    def _setup_view_mode_buttons(
        self,
        diff_actions: list[tuple[str, str]],
        diff_mode: str,
        channel_actions: list[tuple[str, str]],
        channel_mode: str,
    ) -> bool:
        return host_callbacks.setup_view_mode_buttons(
            self, diff_actions, diff_mode, channel_actions, channel_mode
        )

    def _is_canvas_content_ready(self) -> bool:
        return host_callbacks.is_canvas_content_ready(self)

    def register_canvas_features(self) -> None:
        import tabs.image_compare.canvas.features as features_pkg
        from ui.canvas_infra.scene.registry import register_canvas_feature_package

        register_canvas_feature_package("image_compare", features_pkg)

    def apply_appearance(self, host_window) -> None:
        from tabs.image_compare.ui.appearance import apply_image_canvas_appearance

        apply_image_canvas_appearance(host_window)
        if self._widget is not None and self._widget.isVisible():
            self._widget.reapply_button_styles()

    def dispose(self) -> None:
        self._widget = None