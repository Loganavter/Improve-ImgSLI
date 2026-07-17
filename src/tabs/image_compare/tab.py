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

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QWidget

from tabs.contract import TabContext, TabContract, TabTransitionHint

_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp", ".jxl"}
_STATE_SLOT = "image_compare.state"
logger = logging.getLogger("ImproveImgSLI")


def _resolve_image_compare_sessions(context: TabContext):
    main_window = context.main_window
    if main_window is None:
        return None
    controller = getattr(main_window, "main_controller", None)
    if controller is None:
        presenter = getattr(main_window, "presenter", None)
        controller = getattr(presenter, "main_controller", None)
    if controller is None:
        return None
    return getattr(controller, "sessions", None)


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
        return True

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

        self._widget = ImageCompareWidget(parent, context=context)
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
        from tabs.image_compare.ui.primitives import ImageComparePrimitivesFactory

        parent = getattr(ui, "main_window", None) or self._widget
        ImageComparePrimitivesFactory(self._widget, ui).build(parent)
        self._widget.assemble(ui)
        self._widget.image_label.set_drag_overlay_state(False)
        self._widget.drag_overlay.hide()
        self._widget.install_rating_wheel_handlers()
        return True

    def finalize_host_page(self, ui) -> None:
        if self._widget is None:
            return
        self._widget.toggle_edit_layout_visibility(False)
        self._widget.magnifier_settings_panel.setVisible(False)
        self._widget.apply_icon_sizes()

    def apply_host_session_mode(self, ui, session_title: str | None = None) -> bool:
        if self._widget is None:
            return False
        self._widget.toggle_edit_layout_visibility(
            bool(self._widget.btn_file_names.isChecked())
        )
        return True

    def transition_hint(self) -> TabTransitionHint:
        # QRhi warm-up can be long; widen the mask window vs the default 300 ms.
        return TabTransitionHint(
            cover_on_enter=True, min_duration_ms=50, max_duration_ms=400
        )

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
        if session_id is None or self._widget is None:
            return
        store = getattr(context, "store", None)
        if store is None or not hasattr(store, "set_session_state_slot"):
            return
        from tabs.image_compare.models import ImageCompareState

        widget = self._widget
        state = ImageCompareState(
            show_file_names=bool(getattr(getattr(widget, "btn_file_names", None), "isChecked", lambda: False)()),
            edit_name_1=getattr(getattr(widget, "edit_name1", None), "text", lambda: "")(),
            edit_name_2=getattr(getattr(widget, "edit_name2", None), "text", lambda: "")(),
        )
        try:
            store.set_session_state_slot(
                _STATE_SLOT, state, session_id=session_id, emit_scope=None,
            )
        except Exception:
            pass

    def _restore_from(self, context: TabContext, session_id: str | None) -> None:
        if session_id is None or self._widget is None:
            return
        store = getattr(context, "store", None)
        if store is None or not hasattr(store, "ensure_session_state_slot"):
            return
        from tabs.image_compare.models import ImageCompareState

        try:
            state = store.ensure_session_state_slot(
                _STATE_SLOT, session_id=session_id, factory=ImageCompareState,
            )
        except Exception:
            return
        if state is None:
            return
        widget = self._widget
        btn = getattr(widget, "btn_file_names", None)
        if btn is not None and hasattr(btn, "setChecked"):
            btn.setChecked(bool(state.show_file_names))
        for attr, value in (("edit_name1", state.edit_name_1), ("edit_name2", state.edit_name_2)):
            edit = getattr(widget, attr, None)
            if edit is not None and hasattr(edit, "setText"):
                edit.setText(value or "")

    def serialize_session(self, session_id: str, context: TabContext) -> dict | None:
        store = getattr(context, "store", None)
        if store is None:
            return None
        session = store.get_workspace_session(session_id)
        if session is None or session.session_type != self.session_type:
            return None
        doc = session.document
        ui_state = session.state_slots.get(_STATE_SLOT)

        def _items(items):
            return [
                {"path": it.path, "display_name": it.display_name, "rating": it.rating}
                for it in items
            ]

        return {
            "version": 1,
            "image_list1": _items(doc.image_list1) if doc else [],
            "image_list2": _items(doc.image_list2) if doc else [],
            "current_index1": doc.current_index1 if doc else -1,
            "current_index2": doc.current_index2 if doc else -1,
            "image1_path": doc.image1_path if doc else None,
            "image2_path": doc.image2_path if doc else None,
            "show_file_names": bool(ui_state.show_file_names) if ui_state else False,
            "edit_name_1": ui_state.edit_name_1 if ui_state else "",
            "edit_name_2": ui_state.edit_name_2 if ui_state else "",
        }

    def deserialize_session(self, session_id: str, data: dict, context: TabContext) -> None:
        store = getattr(context, "store", None)
        if store is None or not data:
            return
        session = store.get_workspace_session(session_id)
        if session is None:
            return
        from tabs.image_compare.state.document import DocumentModel, ImageItem
        from tabs.image_compare.models import ImageCompareState

        def _items(entries):
            # `image=None` — pixel data is not persisted, only the source
            # path; the existing load pipeline decodes it from disk lazily,
            # the same way `ImageSessionState.loaded_image*_paths` already
            # tracks history without holding pixels.
            return [
                ImageItem(
                    path=e.get("path", ""),
                    display_name=e.get("display_name", ""),
                    rating=e.get("rating", 0),
                )
                for e in entries or []
            ]

        session.document = DocumentModel(
            image_list1=_items(data.get("image_list1")),
            image_list2=_items(data.get("image_list2")),
            current_index1=data.get("current_index1", -1),
            current_index2=data.get("current_index2", -1),
            image1_path=data.get("image1_path"),
            image2_path=data.get("image2_path"),
        )
        store.set_session_state_slot(
            _STATE_SLOT,
            ImageCompareState(
                show_file_names=bool(data.get("show_file_names", False)),
                edit_name_1=data.get("edit_name_1", ""),
                edit_name_2=data.get("edit_name_2", ""),
            ),
            session_id=session_id,
            emit_scope=None,
        )

    def rehydrate_session(self, session_id: str, context: TabContext) -> None:
        store = getattr(context, "store", None)
        if store is None:
            return
        session = store.get_workspace_session(session_id)
        if session is None or session.session_type != self.session_type:
            return
        doc = session.document
        if doc is None:
            return

        paths1 = [item.path for item in doc.image_list1 if getattr(item, "path", None)]
        paths2 = [item.path for item in doc.image_list2 if getattr(item, "path", None)]
        if doc.image1_path and doc.image1_path not in paths1:
            paths1.append(doc.image1_path)
        if doc.image2_path and doc.image2_path not in paths2:
            paths2.append(doc.image2_path)
        if not paths1 and not paths2:
            return

        sessions = _resolve_image_compare_sessions(context)
        if sessions is None:
            return

        with store.using_workspace_session(session_id):
            if paths1:
                sessions.load_images_from_paths(paths1, 1)
            if paths2:
                sessions.load_images_from_paths(paths2, 2)

    def accepts_drop(self, paths: list[Path]) -> bool:
        return any(p.suffix.lower() in _IMAGE_EXTENSIONS for p in paths)

    def handle_drop(self, paths: list[Path], hint: dict | None = None) -> bool:
        from PySide6.QtCore import QTimer

        widget = self._widget
        if widget is None:
            logger.warning("ImageCompareTab.handle_drop: widget is not initialized")
            return False
        main_window = getattr(widget._context, "main_window", None) if widget._context else None
        if main_window is None:
            logger.warning("ImageCompareTab.handle_drop: main_window is unavailable")
            return False
        controller = getattr(main_window, "main_controller", None)
        if controller is None:
            presenter = getattr(main_window, "presenter", None)
            controller = getattr(presenter, "main_controller", None)
        sessions = getattr(controller, "sessions", None) if controller else None
        if sessions is None:
            logger.warning(
                "ImageCompareTab.handle_drop: sessions controller unavailable "
                "(main_controller=%r presenter=%r)",
                getattr(main_window, "main_controller", None),
                getattr(main_window, "presenter", None),
            )
            return False
        image_paths = [str(p) for p in paths if p.suffix.lower() in _IMAGE_EXTENSIONS]
        if not image_paths:
            logger.warning(
                "ImageCompareTab.handle_drop: no supported image paths in %s",
                paths,
            )
            return False
        slot = 1
        if hint is not None:
            if "slot" in hint:
                slot = 1 if int(hint.get("slot") or 1) == 1 else 2
            elif "is_left_area" in hint:
                slot = 1 if bool(hint.get("is_left_area")) else 2
        QTimer.singleShot(
            0, lambda: sessions.load_images_from_paths(image_paths, slot)
        )
        return True

    def _register_settings(self, registry) -> None:
        from plugins.settings.pages.analysis import build as build_analysis
        from plugins.settings.registry import SettingsSection
        from tabs.image_compare.ui.settings_performance import build_image_perf_extras
        from tabs.image_compare.icons import Icon, get_icon

        from plugins.settings.pages.analysis import SEARCH as ANALYSIS_SEARCH
        from tabs.image_compare.ui.settings_performance import SEARCH as PERF_EXTRA_SEARCH

        registry.add(
            SettingsSection(
                section_id="image_compare.analysis",
                title_key="label.details",
                icon=get_icon(Icon.HIGHLIGHT_DIFFERENCES),
                build=build_analysis,
                owner_tab=self.session_type,
                order=40,
                action_description_key="action.settings.analysis_desc",
                search=ANALYSIS_SEARCH,
            )
        )
        registry.add_section_extra(
            "builtin.performance",
            build_image_perf_extras,
            owner_tab=self.session_type,
            order=10,
            search=PERF_EXTRA_SEARCH,
        )

    def _register_actions(self, registry) -> None:
        if self._widget is None:
            return
        from tabs.image_compare.actions import register_image_compare_actions

        register_image_compare_actions(
            widget=self._widget,
            presenter=None,
            registry=registry,
        )
        self._resync_action_shortcuts()

    def _resync_action_shortcuts(self) -> None:
        from PySide6.QtWidgets import QApplication

        from ui.actions.binder import resync_action_shortcuts

        for widget in QApplication.topLevelWidgets():
            if getattr(widget, "presenter", None) is not None:
                resync_action_shortcuts(widget, active_tab=self.session_type)
                return

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
        if self._widget is None:
            return None
        return self._widget.image_label

    def _clear_transient_text_focus(self, focused_widget) -> bool:
        if self._widget is None:
            return False
        if focused_widget in (self._widget.edit_name1, self._widget.edit_name2):
            focused_widget.clearFocus()
            return True
        return False

    def _sync_interpolation_combo_state(
        self, count: int, current_index: int, text: str, items: list[str]
    ) -> bool:
        if self._widget is None:
            return False
        self._widget.combo_interpolation.updateState(
            count=count, current_index=current_index, text=text, items=items
        )
        return True

    def _setup_view_mode_buttons(
        self,
        diff_actions: list[tuple[str, str]],
        diff_mode: str,
        channel_actions: list[tuple[str, str]],
        channel_mode: str,
    ) -> bool:
        if self._widget is None:
            return False
        self._widget.btn_diff_mode_picker.set_actions(diff_actions)
        self._widget.btn_diff_mode_picker.set_current(diff_mode)
        self._widget.btn_channel_mode_picker.set_actions(channel_actions)
        self._widget.btn_channel_mode_picker.set_current(channel_mode)
        return True

    def _is_canvas_content_ready(self) -> bool:
        image_label = self._canvas_label()
        if image_label is None:
            return False

        source_ready = bool(getattr(image_label, "_source_images_ready", False))
        if source_ready:
            return True

        uploaded = getattr(image_label, "_images_uploaded", None)
        if isinstance(uploaded, (list, tuple)) and any(bool(item) for item in uploaded):
            return True

        runtime_state = getattr(image_label, "runtime_state", None)
        if runtime_state is not None:
            uploaded = getattr(runtime_state, "_images_uploaded", None)
            if isinstance(uploaded, (list, tuple)) and any(bool(item) for item in uploaded):
                return True
            background = getattr(runtime_state, "_background_pixmap", None)
            if background is not None and not background.isNull():
                return True

        stored_qimages = getattr(image_label, "_stored_qimages", None)
        if isinstance(stored_qimages, (list, tuple)):
            for image in stored_qimages:
                if image is not None and not image.isNull():
                    return True

        return False

    def register_canvas_features(self) -> None:
        import tabs.image_compare.canvas.features as features_pkg
        from ui.canvas_infra.scene.registry import register_canvas_feature_package

        register_canvas_feature_package("image_compare", features_pkg)

    def apply_appearance(self, host_window) -> None:
        from tabs.image_compare.ui.appearance import apply_image_canvas_appearance

        apply_image_canvas_appearance(host_window)
        if self._widget is not None:
            self._widget.reapply_button_styles()

    def dispose(self) -> None:
        self._widget = None

