"""ImageCompareTab.handle_drop falls back to the presenter's main_controller."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from PySide6.QtWidgets import QApplication

from tabs.image_compare.tab import ImageCompareTab


def test_image_compare_drop_uses_presenter_main_controller_when_window_has_no_direct_controller():
    QApplication.instance() or QApplication([])
    calls = []
    sessions = SimpleNamespace(
        load_images_from_paths=lambda paths, slot: calls.append((paths, slot))
    )
    main_window = SimpleNamespace(
        main_controller=None,
        presenter=SimpleNamespace(main_controller=SimpleNamespace(sessions=sessions)),
    )
    tab = ImageCompareTab()
    tab._widget = SimpleNamespace(_context=SimpleNamespace(main_window=main_window))

    drop_path = Path("/tmp/right.png")
    handled = tab.handle_drop([drop_path], hint={"slot": 2})
    QApplication.processEvents()

    assert handled is True
    assert len(calls) == 1
    paths, slot = calls[0]
    assert slot == 2
    # Windows stringifies absolute POSIX-looking Paths with backslashes.
    assert [Path(p) for p in paths] == [drop_path]
