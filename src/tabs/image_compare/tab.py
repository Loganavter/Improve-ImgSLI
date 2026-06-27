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

from PySide6.QtWidgets import QWidget

from tabs.contract import TabContext, TabContract, TabTransitionHint

_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp", ".jxl"}


class ImageCompareTab(TabContract):
    def __init__(self):
        self._widget: "ImageCompareWidget | None" = None

    @property
    def session_type(self) -> str:
        return "image_compare"

    @property
    def display_name(self) -> str:
        return "Image Compare"

    @property
    def resources_dir(self) -> Path | None:
        return Path(__file__).parent / "resources"

    @property
    def i18n_namespace(self) -> str | None:
        return "image_compare"

    def create_page(self, parent: QWidget, context: TabContext) -> QWidget:
        from tabs.image_compare.widget import ImageCompareWidget

        self._widget = ImageCompareWidget(parent, context=context)
        return self._widget

    @property
    def widget(self) -> "ImageCompareWidget | None":
        return self._widget

    def transition_hint(self) -> TabTransitionHint:
        # QRhi warm-up can be long; widen the mask window vs the default 300 ms.
        return TabTransitionHint(
            cover_on_enter=True, min_duration_ms=50, max_duration_ms=400
        )

    def on_activated(self, context: TabContext) -> None:
        if self._widget is not None:
            self._widget.setFocus()
        # Release the transition mask once we are shown — the canvas does not
        # yet expose firstVisualFrameReady, so this is a best-effort signal.
        mask = (context.services or {}).get("workspace.transition_mask")
        if mask is not None:
            try:
                mask.release()
            except Exception:
                pass

    def accepts_drop(self, paths: list[Path]) -> bool:
        return any(p.suffix.lower() in _IMAGE_EXTENSIONS for p in paths)

    def handle_drop(self, paths: list[Path]) -> None:
        # The WindowEventHandler currently keeps the slot-aware drop fallback
        # for image_compare, so returning False from accepts_drop is also valid.
        # We accept the drop here so that the contract advertises the capability;
        # the actual slot routing is still done by the host until Stage 5 lands
        # full per-session state ownership in this tab.
        from PySide6.QtCore import QTimer

        widget = self._widget
        if widget is None:
            return
        main_window = getattr(widget._context, "main_window", None) if widget._context else None
        if main_window is None:
            return
        controller = getattr(main_window, "main_controller", None)
        sessions = getattr(controller, "sessions", None) if controller else None
        if sessions is None:
            return
        image_paths = [str(p) for p in paths if p.suffix.lower() in _IMAGE_EXTENSIONS]
        if not image_paths:
            return
        QTimer.singleShot(
            0, lambda: sessions.load_images_from_paths(image_paths, 1)
        )

    def contribute_settings(self, registry) -> None:
        # Stage 9 (full move of owner_tab='image_compare' sections into this
        # tab) is deferred — the existing plugins.settings discovery already
        # honors owner_tab='image_compare'. No-op here keeps the contract
        # surface complete without duplicating registration.
        return

    def dispose(self) -> None:
        self._widget = None
