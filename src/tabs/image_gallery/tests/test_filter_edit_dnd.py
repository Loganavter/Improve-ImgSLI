"""Gallery toolbar filter field must not accept file drops (DnD routing).

Regression mirror of
``src/tabs/image_compare/tests/runtime/test_caption_edit_row_dnd.py``:
``QLineEdit`` accepts drags by default, so the toolbar's filter field
became the Qt drag target whenever the cursor crossed the toolbar, and
the gallery widget/grid/empty-state drop routing (all ``acceptDrops``)
never saw the files. The filter field is not a drop target, so it must
opt out of drag acceptance.
"""

from __future__ import annotations

from tabs.image_gallery.ui.toolbar import GalleryToolbar


def test_filter_edit_rejects_file_drags(qtbot):
    toolbar = GalleryToolbar()
    qtbot.addWidget(toolbar)

    assert toolbar.filter_edit.acceptDrops() is False, (
        "filter_edit must not accept drops: a default QLineEdit acceptDrops "
        "steals the drag target from the gallery drop routing chain"
    )
