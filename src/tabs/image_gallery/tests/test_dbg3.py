import shiboken6
from PySide6.QtWidgets import QWidget
from tabs.image_gallery.ui.quick_look import QuickLookOverlay, _SourceInsetHost, _source_dimensions


class GalleryItem:  # placeholder import stand-in
    pass


def test_dbg(qtbot):
    parent = QWidget()
    qtbot.addWidget(parent)
    ov = QuickLookOverlay(parent)
    print("after ctor content valid:", shiboken6.isValid(ov._content))
    import gc
    gc.collect()
    print("after gc:", shiboken6.isValid(ov._content))
