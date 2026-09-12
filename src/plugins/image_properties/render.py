"""Render ImageProperties as HelpDocumentView blocks (unified text canvas).

Mirrors the help viewer's approach (``plugins/help/dialog.py``): one
``HelpDocumentBodyCanvas`` renders the whole page and owns text selection
across sections, instead of one independently-selectable ``QLabel`` per row.
Rows render as a ``TableBlock`` — a real bordered table on the canvas, not
just tab-aligned columns.
"""

from __future__ import annotations

from collections.abc import Callable

from sli_ui_toolkit.ui.widgets.composite.text_view.markdown import (
    HeadingBlock,
    HelpBlock,
    InlineKind,
    InlineSpan,
    TableBlock,
)

from .service import ImageProperties, ImagePropertyRow

Translate = Callable[[str, str], str]


def build_property_blocks(
    properties: ImageProperties, translate: Translate
) -> tuple[HelpBlock, ...]:
    """Convert properties sections/rows into typed blocks for ``HelpDocumentView``.

    Row values are carried as plain ``InlineSpan`` text, never re-parsed as
    markdown — file paths / EXIF strings containing ``*``, ``[``, `` ` `` etc.
    must render verbatim instead of being misread as formatting.
    """
    blocks: list[HelpBlock] = []
    for section in properties.sections:
        if not section.rows:
            continue
        blocks.append(
            HeadingBlock(
                level=3, text=translate(section.title_key, section.fallback_title)
            )
        )
        blocks.append(
            TableBlock(
                rows=tuple(_row_cells(row, translate) for row in section.rows)
            )
        )
    return tuple(blocks)


def _row_cells(
    row: ImagePropertyRow, translate: Translate
) -> tuple[tuple[InlineSpan, ...], tuple[InlineSpan, ...]]:
    label = translate(row.label_key, row.fallback_label)
    value = _row_value(row, translate)
    return (
        (InlineSpan(InlineKind.BOLD, label),),
        (InlineSpan(InlineKind.TEXT, value),),
    )


def _row_value(row: ImagePropertyRow, translate: Translate) -> str:
    if row.value_key:
        return translate(row.value_key, row.fallback_value or row.value)
    return row.value or "-"