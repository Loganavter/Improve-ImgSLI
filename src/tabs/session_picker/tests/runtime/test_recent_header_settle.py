"""The Recent header settles its own layout when control visibility changes.

Owner report (2026-10-23): the shelf header's sort/view chips were absent in
the first visible frames and appeared ~0.8 s later. Caught on a headless-sway
frame capture (X11 cannot see it — the window is mapped only after the deferred
batch), reproduced on the pre-fix tree and on `main`, fixed by settling the
header's `QHBoxLayout` in the same call that toggles the chips.

Mechanism 1 of `../improve-imgsli-internal-docs/docs/dev/QT_LAYOUT_PITFALLS.md`: a visibility toggle only POSTS
a layout re-run, so the frame committed right after it carries the
pre-layout arrangement (the chips have no geometry yet).
"""

from __future__ import annotations

import sli_ui_toolkit.ui.layout_settle as layout_settle
from tabs.session_picker.recent.header_bar import RecentHeaderBar


def _tr(key: str, default: str = "", *args, **kwargs) -> str:
    return default or key


def _header(qapp) -> RecentHeaderBar:
    header = RecentHeaderBar(translate=_tr)
    header.resize(420, 40)
    header.show()
    qapp.processEvents()
    return header


def test_set_controls_visible_settles_the_header_layout(qapp, monkeypatch):
    calls: list[tuple] = []
    monkeypatch.setattr(
        layout_settle, "settle_layout", lambda *a, **kw: calls.append((a, kw))
    )
    header = _header(qapp)

    header.set_controls_visible(True)

    assert calls, (
        "set_controls_visible must settle the header layout in the same call — "
        "a posted re-run paints the first frame without the chips"
    )
    assert calls[0][0][0] is header, "the header itself must be the settled widget"
    header.deleteLater()


def test_sync_settles_the_header_layout(qapp, monkeypatch):
    from PySide6.QtGui import QColor

    calls: list[tuple] = []
    monkeypatch.setattr(
        layout_settle, "settle_layout", lambda *a, **kw: calls.append((a, kw))
    )
    header = _header(qapp)

    header.sync(
        sort_mode="recent",
        sort_order="desc",
        view_mode="grid",
        has_items=True,
        chip_bg=QColor("#303030"),
    )

    assert calls, (
        "sync must settle the header layout — it toggles the chips' visibility "
        "on every refresh"
    )
    header.deleteLater()
