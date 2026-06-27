"""Image-compare tab contract implementation.

Stage 1 of the migration: skeleton only. ``create_page`` returns an empty
``ImageCompareWidget``; the real comparison page is still assembled inside
``MainWindow`` and ``sync_session_mode`` keeps falling back to it. See
``docs/MIGRATION_PLAN.md``.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QVBoxLayout, QWidget

from tabs.contract import TabContext, TabContract


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

        page = QWidget(parent)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._widget = ImageCompareWidget(page, context=context)
        layout.addWidget(self._widget)
        return page

    def dispose(self) -> None:
        self._widget = None
