"""Multi-compare tab contract implementation."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QVBoxLayout, QWidget

from tabs.contract import TabContext, TabContract

_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp"}

class MultiCompareTab(TabContract):
    """Self-contained multi-image comparison tab."""

    def __init__(self):
        self._controller = None
        self._widget = None

    @property
    def session_type(self) -> str:
        return "multi_compare"

    @property
    def display_name(self) -> str:
        return "Multi Compare"

    @property
    def resources_dir(self) -> Path | None:
        return Path(__file__).parent / "resources"

    @property
    def i18n_namespace(self) -> str | None:
        return "multi_compare"

    def create_page(self, parent: QWidget, context: TabContext) -> QWidget:
        from tabs.multi_compare.controller import MultiCompareController
        from tabs.multi_compare.widget import MultiCompareWidget

        page = QWidget(parent)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._widget = MultiCompareWidget(
            page,
            add_images_text=context.tr("add_images", "Add images"),
            save_result_text=context.tr("save_result", "Save result"),
            translate=context.tr,
        )
        self._controller = MultiCompareController(
            self._widget,
            store=context.store,
            translate=context.tr,
            dialog_parent=context.main_window or page,
            open_export_dialog=lambda **kwargs: context.call_service(
                "open_image_export_dialog", **kwargs
            ),
        )
        layout.addWidget(self._widget)

        return page

    def on_activated(self, context: TabContext) -> None:
        if self._widget:
            self._widget.setFocus()

    def on_deactivated(self, context: TabContext) -> None:
        pass

    def accepts_drop(self, paths: list[Path]) -> bool:
        return any(p.suffix.lower() in _IMAGE_EXTENSIONS for p in paths)

    def handle_drop(self, paths: list[Path]) -> None:
        if self._controller:
            image_paths = [p for p in paths if p.suffix.lower() in _IMAGE_EXTENSIONS]
            self._controller.load_images(image_paths)

    def dispose(self) -> None:
        self._controller = None
        self._widget = None
