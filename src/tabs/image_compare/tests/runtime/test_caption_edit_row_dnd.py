"""Caption edit row must not accept file drops (DnD tiles routing).

Regression: ``QLineEdit`` accepts drags by default (``acceptDrops()`` is
True out of the box, and file drags carry ``text/plain``), so with the
bottom caption edit row visible the two name LineEdits became the Qt drag
target. The main window received ``DragLeave``, the 80ms deferred-leave
timer hid the DnD tiles, and no routed ``DragEnter`` ever restored them —
the zone vanished exactly while the row was shown. The caption fields are
not drop targets, so the factory must opt them out of drag acceptance.
"""

from __future__ import annotations

import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QWidget

from tabs.image_compare.ui.primitives import ImageComparePrimitivesFactory


def test_caption_name_edits_reject_file_drags(qtbot):
    host = QWidget()
    qtbot.addWidget(host)

    factory = ImageComparePrimitivesFactory(SimpleNamespace(), host)
    factory._create_text_and_status_widgets(host)

    for name in ("edit_name1", "edit_name2"):
        edit = getattr(factory.target, name)
        assert edit.acceptDrops() is False, (
            f"{name} must not accept drops: a default QLineEdit acceptDrops "
            "steals the drag target from the main-window routing chain and "
            "hides the DnD tiles while the caption edit row is visible"
        )
