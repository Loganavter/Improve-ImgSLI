"""Video editor export tabs use toolkit TopTabHost (not QTabWidget)."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QLabel

from sli_ui_toolkit.widgets import TopTabHost


def test_top_tab_host_api_matches_video_editor_usage(qapp):
    host = TopTabHost()
    host.setObjectName("VideoEditorTabs")

    pages = [QLabel(name) for name in ("standard", "manual", "output", "log")]
    for page, title in zip(pages, ("Standard", "Manual", "Output", "Log"), strict=True):
        host.addTab(page, title)

    assert host.objectName() == "VideoEditorTabs"
    assert host.count() == 4
    assert host.currentIndex() == 0
    assert host.indexOf(pages[3]) == 3

    host.setCurrentWidget(pages[3])
    assert host.currentIndex() == 3
    assert host.currentWidget() is pages[3]

    host.setTabText(1, "CLI")
    assert host.tabText(1) == "CLI"
    host.deleteLater()
