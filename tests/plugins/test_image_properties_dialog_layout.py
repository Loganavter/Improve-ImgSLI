"""Image properties dialog renders as a unified text canvas (like Help)."""

from __future__ import annotations

from plugins.image_properties.dialog import ImagePropertiesDialog
from plugins.image_properties.layout_geometry import (
    apply_image_properties_dialog_geometry,
)
from plugins.image_properties.render import build_property_blocks
from plugins.image_properties.service import (
    ImageProperties,
    ImagePropertyRow,
    ImagePropertySection,
)


def _sample_properties() -> ImageProperties:
    return ImageProperties(
        title="Properties",
        sections=tuple(
            ImagePropertySection(
                f"section_{index}",
                f"Section {index}",
                (
                    ImagePropertyRow(f"row_{index}", "Name", f"value_{index}.png"),
                    ImagePropertyRow(f"meta_{index}", "Size", "1920 x 1080 px"),
                ),
            )
            for index in range(3)
        ),
    )


def test_image_properties_document_stretches_after_geometry_while_visible(qapp):
    """Deferred geometry used to call adjustSize on live frames and freeze
    them at sizeHint width; the document canvas must still fill the scroll
    content after re-applying geometry while visible.
    """
    dialog = ImagePropertiesDialog(
        _sample_properties(),
        parent=None,
        current_language="en",
    )
    dialog.show()
    qapp.processEvents()

    # Re-apply while visible — the old path broke stretch here.
    apply_image_properties_dialog_geometry(dialog)
    qapp.processEvents()

    content_width = dialog.properties_scroll_content.width()
    assert content_width > 0
    assert dialog.properties_document.width() >= content_width - 4
    assert dialog.properties_document.height() > 0

    dialog.close()


def test_image_properties_blocks_cover_all_sections_and_rows():
    properties = _sample_properties()
    blocks = build_property_blocks(properties, lambda key, default: default)

    # One heading + one table per section; the table carries all its rows.
    from sli_ui_toolkit.ui.widgets.composite.text_view.markdown import (
        HeadingBlock,
        TableBlock,
    )

    assert len(blocks) == 2 * len(properties.sections)
    assert all(isinstance(b, (HeadingBlock, TableBlock)) for b in blocks)
    tables = [b for b in blocks if isinstance(b, TableBlock)]
    for table, section in zip(tables, properties.sections):
        assert len(table.rows) == len(section.rows)


def test_image_properties_row_is_a_bordered_table_row():
    """Label/value land in separate TableBlock cells — real grid, not tabs."""
    from sli_ui_toolkit.ui.widgets.composite.text_view.markdown import (
        InlineKind,
        TableBlock,
    )

    properties = _sample_properties()
    blocks = build_property_blocks(properties, lambda key, default: default)
    tables = [b for b in blocks if isinstance(b, TableBlock)]
    assert tables
    for table in tables:
        for label_spans, value_spans in table.rows:
            assert label_spans[0].kind == InlineKind.BOLD
            assert value_spans


def test_image_properties_table_renders_with_border_geometry(qapp):
    """The canvas layout must produce real border lines, not just aligned text."""
    dialog = ImagePropertiesDialog(
        _sample_properties(),
        parent=None,
        current_language="en",
    )
    dialog.show()
    qapp.processEvents()

    canvas = dialog.properties_document._canvas
    tables = canvas._layout.tables
    assert len(tables) == 3  # one per section
    for table, section in zip(tables, _sample_properties().sections):
        assert table.rect.width() > 0
        assert table.rect.height() > 0
        # Two-column label/value grid: one vertical divider per table.
        assert len(table.col_xs) == 1
        assert table.col_xs[0] > 0
        assert len(table.row_ys) == len(section.rows) - 1

    dialog.close()


def test_image_properties_selection_spans_the_whole_document(qapp):
    """Unlike per-row QLabel selection, the canvas selects across rows/sections."""
    dialog = ImagePropertiesDialog(
        _sample_properties(),
        parent=None,
        current_language="en",
    )
    dialog.show()
    qapp.processEvents()

    document = dialog.properties_document
    document.select_all_text()
    selected = document.selected_plain_text()
    assert "value_0.png" in selected
    assert "value_2.png" in selected

    dialog.close()