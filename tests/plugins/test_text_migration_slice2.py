"""Export / Help / Image-Properties display labels use the unified ``Text``.

P3 text unification, slice 2. Every ``Label`` display construction in these
three plugins is migrated to ``Text(..., mode="plain")`` — plain mode is the
``Label`` parity mode (same variant registry, same typography surface), so the
mapping is mechanical:

=====================================  =======================================
old                                    new
=====================================  =======================================
``Label(text)``                        ``Text(text, mode="plain")``
``Label(text, pixel_size=N, ...)``     ``Text(text, mode="plain",
                                       pixel_size=N, ...)``
=====================================  =======================================

Effective sizes were unchanged at migration time because ``Text`` shares
``Label``'s variant registry (``body`` = 12 px, ``dialog.text`` color): an
explicit ``pixel_size`` overrides the preset exactly as it did for ``Label``.

Typing note (post-migration): the export row labels/readouts were later raised
from ``body`` (12 px) to the app-registered ``group-title`` (14 px, regular —
``ui/icon_manager.py``), because 12 px painted them visibly smaller than the
value text, checkbox captions and buttons beside them. They are still plain
``Text``; only the variant/size assertion below reflects that.

Call sites (all explicit text displays, no factory funnel in these plugins):

- ``plugins/export/dialog_sections.py`` — preview title, format / resolution /
  quality / PNG-compression / comment row labels, quality and compression
  value readouts.
- ``plugins/help/hub_page.py`` — hub title (22 px bold) and subtitle (13 px,
  wrapped, ``list_item.text.rating`` colour).
- ``plugins/help/back_bar.py`` — breadcrumb ``/`` separators (12 px).
- ``plugins/image_properties/`` — no ``Label`` call site: rows render through
  the ``Text(mode="document")`` document surface (``plugins/image_properties/
  render.py``), which is the plan's separate document-surface slice.

Out of scope (deliberately NOT migrated, documented here instead of an
allowlist entry because the source scan below only matches the toolkit
``Label`` name):

- ``export/dialog_sections.py::_ExportPreviewLabel`` — a ``QLabel`` subclass
  that hosts the preview pixmap and overrides ``sizeHint``; it is a pixmap
  surface, not a text display, and the P3 rules exclude ``Label``
  subclasses / widgets relied on as a ``Label`` type.
- The document surface itself — ``Text(mode="document")`` in the external
  toolkit; the app hosts its chrome (TOC / lightbox / scroll area) around it.

Falsification story: pre-migration each replaced attribute was a
``sli_ui_toolkit.widgets.Label`` (``QLabel``-based), so the behavioural assert
``isinstance(widget, Text)`` failed for every sample below; the source scan
failed on the seven ``Label`` imports/constructions it now forbids.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QSizePolicy

from plugins.export.dialog import ExportDialog
from plugins.export.models import ExportDialogState
from plugins.help.dialog import HelpDialog
from plugins.image_properties.dialog import ImagePropertiesDialog
from plugins.image_properties.service import (
    ImageProperties,
    ImagePropertyRow,
    ImagePropertySection,
)
from resources.translations import add_i18n_root
from sli_ui_toolkit.managers import UiScale, scaled_px
from sli_ui_toolkit.ui.widgets.atomic.text_labels import Label  # internal: documented Label exception (queue task-text-unification-retirement-2026-10-21)
from sli_ui_toolkit.widgets import Text

_PLUGINS_ROOT = Path(__file__).resolve().parents[2] / "src" / "plugins"
_SCANNED_PLUGINS = ("export", "help", "image_properties")

#: File relative to ``src/plugins`` -> reason it may still use ``Label``.
#: No entry: the only Label-family leftovers are a ``QLabel`` pixmap preview
#: (not the toolkit ``Label``) and the toolkit's document canvas — both
#: documented in the module docstring and asserted by
#: ``test_out_of_scope_surfaces_are_not_the_toolkit_label`` below.
_ALLOWED_LABEL_USES: dict[str, str] = {}


def _label_uses(path: Path) -> list[str]:
    """Imports/constructions of ``Label`` recorded as ``<kind>:<name>``."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    uses: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == "Label":
                    uses.append(f"import:{alias.asname or alias.name}")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "Label" or alias.name.endswith(".Label"):
                    uses.append(f"import:{alias.asname or alias.name}")
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == "Label":
                uses.append(f"call:{func.id}")
            elif isinstance(func, ast.Attribute) and func.attr == "Label":
                uses.append(f"call:{func.attr}")
    return uses


def test_slice2_plugin_sources_have_no_label_construction_or_import():
    offenders: list[str] = []
    for plugin in _SCANNED_PLUGINS:
        plugin_root = _PLUGINS_ROOT / plugin
        sources = sorted(plugin_root.rglob("*.py"))
        assert sources, f"{plugin} plugin sources must exist"
        for path in sources:
            rel = str(path.relative_to(_PLUGINS_ROOT))
            if rel in _ALLOWED_LABEL_USES:
                continue
            for use in _label_uses(path):
                offenders.append(f"{rel}: {use}")
    assert not offenders, (
        "export/help/image_properties display labels must use the unified "
        f"Text widget; found remaining Label usage: {offenders}"
    )


def test_out_of_scope_surfaces_are_not_the_toolkit_label():
    """Pin the two documented non-migrations to their real types."""
    from plugins.export import dialog_sections

    # Preview surface: a QLabel subclass owning a pixmap, never a Label.
    assert issubclass(dialog_sections._ExportPreviewLabel, dialog_sections.QLabel)
    assert not issubclass(dialog_sections._ExportPreviewLabel, Label)

    # Image properties render through the document surface, not per-row Label.
    props_root = _PLUGINS_ROOT / "image_properties"
    uses = [use for path in props_root.rglob("*.py") for use in _label_uses(path)]
    assert uses == []


@pytest.fixture(autouse=True)
def _scale_one():
    UiScale.get_instance().set_factor(1.0)
    yield
    UiScale.get_instance().set_factor(1.0)


@pytest.fixture(autouse=True)
def _help_tabs_discovered():
    from plugins.help.tree import clear_help_tree_cache
    from tabs.registry import TabRegistry

    TabRegistry().discover()
    TabRegistry().contribute_all_help()
    yield
    clear_help_tree_cache()


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _export_dialog() -> ExportDialog:
    from domain.types import Color

    add_i18n_root(Path("src/plugins/export/resources/i18n"))
    state = ExportDialogState(
        current_language="en",
        output_dir="/tmp",
        favorite_dir=None,
        last_format="PNG",
        quality=95,
        png_compress_level=9,
        fill_background=True,
        background_color=Color(255, 255, 255, 255),
        comment_text="",
        comment_keep_default=False,
        resolution_scale=1.0,
    )
    return ExportDialog(dialog_state=state, suggested_filename="out")


def _assert_plain_text(widget, *, pixel_size: int, variant: str = "body") -> Text:
    assert isinstance(widget, Text), type(widget)
    assert not isinstance(widget, Label)
    assert widget.mode() == "plain"
    assert widget.variant() == variant
    assert widget.font().pixelSize() == scaled_px(pixel_size)
    return widget


def test_export_dialog_labels_are_plain_text(qapp: QApplication):
    """Export row labels / readouts: 14 px plain ``Text`` (app group-title)."""
    dialog = _export_dialog()
    try:
        for widget in (
            dialog.export_preview_title,
            dialog.fmt_label,
            dialog.resolution_label,
            dialog.quality_label,
            dialog.label_quality_value,
            dialog.label_png_compress,
            dialog.label_png_compress_value,
            dialog.comment_label,
        ):
            _assert_plain_text(widget, pixel_size=14, variant="group-title")

        # Preserved non-typography state: centred preview caption, live
        # readouts still track their sliders through ``setText``.
        assert dialog.export_preview_title.alignment() & Qt.AlignmentFlag.AlignHCenter
        dialog.slider_quality.setValue(42)
        qapp.processEvents()
        assert dialog.label_quality_value.text() == "42"
    finally:
        dialog.close()


def _help_dialog(qapp: QApplication) -> HelpDialog:
    dialog = HelpDialog(current_language="en", app_name="Improve-ImgSLI")
    dialog.show()
    qapp.processEvents()
    return dialog


def test_help_hub_title_and_subtitle_are_plain_text(qapp: QApplication):
    """Hub title (22 px bold) / subtitle (13 px wrapped) keep sizes + wrap."""
    dialog = _help_dialog(qapp)
    try:
        title = _assert_plain_text(dialog._hub_page._title, pixel_size=22)
        assert title.font().bold() is True

        subtitle = _assert_plain_text(dialog._hub_page._subtitle, pixel_size=13)
        assert subtitle.wordWrap() is True
    finally:
        dialog.close()


def test_help_breadcrumb_separators_are_plain_text(qapp: QApplication):
    """Breadcrumb ``/`` separators: 12 px plain ``Text``, fixed policy kept."""
    dialog = _help_dialog(qapp)
    try:
        dialog._back_bar.set_breadcrumb((("ui", "UI"), ("ui.help", "Help")))
        qapp.processEvents()

        separators = [
            dialog._back_bar._crumbs_layout.itemAt(i).widget()
            for i in range(dialog._back_bar._crumbs_layout.count())
        ]
        separators = [
            widget
            for widget in separators
            if isinstance(widget, Text) and widget.get_original_text() == "/"
        ]
        assert len(separators) == 1
        separator = _assert_plain_text(separators[0], pixel_size=12)
        assert (
            separator.sizePolicy().horizontalPolicy()
            == QSizePolicy.Policy.Fixed
        )
    finally:
        dialog.close()


def _sample_properties() -> ImageProperties:
    return ImageProperties(
        title="Properties",
        sections=tuple(
            ImagePropertySection(
                f"section_{index}",
                f"Section {index}",
                (ImagePropertyRow(f"row_{index}", "Name", f"value_{index}.png"),),
            )
            for index in range(2)
        ),
    )


def test_image_properties_has_no_label_migration_target(qapp: QApplication):
    """Rows render on the painted document surface, so the dialog builds with
    no per-row ``Label``/``Text`` widgets to migrate in this slice."""
    dialog = ImagePropertiesDialog(
        _sample_properties(), parent=None, current_language="en"
    )
    try:
        dialog.show()
        qapp.processEvents()
        document = dialog.properties_document
        assert isinstance(document, Text)
        assert document.mode() == "document"
        assert document.panel_fill is True
        assert document.plain_text() != ""
    finally:
        dialog.close()
